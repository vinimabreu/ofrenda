"""Which files at the revision get blamed.

A file is kept when it is a regular file in the tree at the revision and none of
these rules skips it, checked in this order:

1. ``not-a-file``: symlinks (mode 120000) and submodules (160000).
2. ``vendored``: a directory on its path is one of ``VENDOR_DIRS`` (vendored
   packages or build output), or the revision's ``.gitattributes`` marks it
   ``linguist-vendored``.
3. ``generated``: a lockfile (``LOCKFILES``), a minified or bundled asset, a
   source map, protobuf output or a gettext catalog (``GENERATED_SUFFIXES``;
   extraction tools write a catalog's ``msgid`` lines, copied from the source
   text), or marked ``linguist-generated``.
4. ``large``: more than ``MAX_BYTES`` bytes.
5. ``binary``: marked ``binary`` or ``-diff`` in ``.gitattributes``, or a NUL
   byte in its first 8,000 bytes (the test git itself uses).
6. ``empty``: no lines.
7. ``long-lines``: lines longer than ``MAX_AVERAGE_LINE`` characters on average
   (minified code, or data kept on one line).

Attributes are read from the tree at the revision with ``git check-attr
--source``, never from a working tree.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .gitread import Git, TreeEntry

MAX_BYTES = 1_000_000
MAX_AVERAGE_LINE = 300
BINARY_PROBE = 8000
RULES_VERSION = "files-v1"

VENDOR_DIRS = frozenset({
    "node_modules", "bower_components", "jspm_packages", "vendor", "vendored", "third_party", "third-party",
    "thirdparty", "site-packages", "dist-packages", "__pycache__", ".yarn", ".pnpm-store", "dist",
})
LOCKFILES = frozenset({
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
    "poetry.lock", "pipfile.lock", "pdm.lock", "uv.lock", "cargo.lock", "composer.lock", "gemfile.lock",
    "go.sum", "mix.lock", "flake.lock", "packages.lock.json", "podfile.lock",
})
GENERATED_SUFFIXES = (".min.js", ".min.mjs", ".min.css", "-min.js", ".bundle.js", ".js.map", ".css.map", ".po", ".pot",
                      "_pb2.py", "_pb2_grpc.py", ".pb.go")
ATTRIBUTES = ("linguist-vendored", "linguist-generated", "binary", "diff")


@dataclass(frozen=True)
class Kept:
    path: str
    oid: str
    lines: int


@dataclass
class Selection:
    kept: list[Kept] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)

    @property
    def files_seen(self) -> int:
        return len(self.kept) + sum(self.skipped.values())


def path_rule(path: str) -> str | None:
    """The reason the path alone skips a file, or None."""
    parts = PurePosixPath(path).parts
    if any(part.casefold() in VENDOR_DIRS for part in parts[:-1]):
        return "vendored"
    name = parts[-1].casefold() if parts else ""
    if name in LOCKFILES or name.endswith(GENERATED_SUFFIXES):
        return "generated"
    return None


def attribute_rule(attrs: dict[str, str]) -> str | None:
    if attrs.get("linguist-vendored") in ("set", "true"):
        return "vendored"
    if attrs.get("linguist-generated") in ("set", "true"):
        return "generated"
    if attrs.get("binary") == "set" or attrs.get("diff") == "unset":
        return "binary"
    return None


def content_rule(data: bytes) -> str | None:
    if b"\0" in data[:BINARY_PROBE]:
        return "binary"
    lines = count_lines(data)
    if lines == 0:
        return "empty"
    if len(data) / lines > MAX_AVERAGE_LINE:
        return "long-lines"
    return None


def count_lines(data: bytes) -> int:
    """Lines as git blame counts them: a last line without a newline still counts."""
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def select(git: Git, commit: str, entries: Sequence[TreeEntry] | None = None) -> Selection:
    selection = Selection()
    entries = list(entries) if entries is not None else git.ls_tree(commit)
    candidates: list[TreeEntry] = []
    for entry in entries:
        if entry.kind != "blob" or entry.mode not in ("100644", "100755"):
            selection.skipped["not-a-file"] += 1
            continue
        reason = path_rule(entry.path)
        if reason:
            selection.skipped[reason] += 1
            continue
        candidates.append(entry)
    attrs = git.check_attr(commit, [e.path for e in candidates], ATTRIBUTES)
    sized: list[TreeEntry] = []
    for entry in candidates:
        reason = attribute_rule(attrs.get(entry.path, {}))
        if reason in ("vendored", "generated"):
            selection.skipped[reason] += 1
        elif entry.size > MAX_BYTES:
            selection.skipped["large"] += 1
        elif reason:
            selection.skipped[reason] += 1
        else:
            sized.append(entry)
    blobs = git.read_blobs(e.oid for e in sized)
    for entry in sized:
        data = blobs.get(entry.oid)
        if data is None:
            selection.skipped["unreadable"] += 1
            continue
        reason = content_rule(data)
        if reason:
            selection.skipped[reason] += 1
            continue
        selection.kept.append(Kept(entry.path, entry.oid, count_lines(data)))
    selection.kept.sort(key=lambda k: k.path)
    return selection
