"""Every git call ofrenda makes goes through ``Git``.

ofrenda reads git objects and nothing else. It never checks out, never touches
the working tree or the index, and never runs a program the repository asks for.

The repository is read through a shadow repository. ``Git`` asks the real one a
few plumbing questions (where its objects are, their hash format, where its
``shallow`` file is, which commit a revision names), then builds an empty bare
repository in a private temporary folder whose ``objects/info/alternates``
points at the real objects. Everything else (the tree, the blobs, blame, log,
attributes) runs against the shadow, so git never reads the repository's own
``config``: none of its keys can start a program (``core.fsmonitor``, a textconv
driver, ``gpg.program`` with ``log.showSignature``, a pager, a promisor remote
to fetch from) or change the result (``blame.ignoreRevsFile``,
``mailmap.file``). The shadow is deleted on
close. A shallow clone's ``shallow`` file is copied in so blame stops where the
history stops.

On top of that, every call:

- runs with ``GIT_WORK_TREE`` set to an empty private folder and
  ``GIT_INDEX_FILE`` pointing at a file that does not exist, so a working tree,
  an index, or a ``.mailmap`` or ``.gitattributes`` on disk is never read;
- ignores the system and global git config (``GIT_CONFIG_NOSYSTEM``,
  ``GIT_CONFIG_GLOBAL``, ``HOME``), so the result does not depend on who runs it;
- carries ``-c`` overrides for the keys that can start a program (``HARDENING``),
  as a second layer for the calls made against the real repository;
- turns off lazy fetching and every transport (``GIT_NO_LAZY_FETCH``,
  ``GIT_ALLOW_PROTOCOL``), and replace refs (``GIT_NO_REPLACE_OBJECTS``);
- maps identities with the ``.mailmap`` blob of the revision being read
  (``mailmap.blob=<commit>:.mailmap``), the same way in a bare clone and in a
  normal one.

Running ofrenda on the output of ``git clone --bare`` is still the recommended
setup for a repository you did not write: a fresh bare clone has no working tree
and a config written by git itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

NOT_A_PROTOCOL = "ofrenda-reads-local-objects-only"

# -c overrides placed before every subcommand.
HARDENING: tuple[str, ...] = (
    "-c", "core.fsmonitor=false",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.pager=cat",
    "-c", "log.showSignature=false",
    "-c", "gpg.program=false",
    "-c", "gpg.ssh.program=false",
    "-c", "gpg.x509.program=false",
    "-c", "protocol.allow=never",
    "-c", "i18n.logOutputEncoding=UTF-8",
    "-c", "mailmap.file=",
    "-c", "color.ui=false",
)


class GitError(RuntimeError):
    """git failed, or the path is not a repository ofrenda can read."""


def _environment(home: Path, git_dir: Path | None, work: Path | None = None) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_ALLOW_PROTOCOL": NOT_A_PROTOCOL,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "GIT_ASKPASS": "false",
        "SSH_ASKPASS": "false",
        "GIT_EDITOR": "false",
    }
    if os.environ.get("SYSTEMROOT"):  # Windows needs it to start any process
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    if git_dir is not None:
        env["GIT_DIR"] = str(git_dir)
        env["GIT_WORK_TREE"] = str(work or home)
        env["GIT_INDEX_FILE"] = str((work or home) / "no-index")
    return env


def _first_line(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace").strip()
    return text.splitlines()[0] if text else "no message"


def _command_name(args: Sequence[str]) -> str:
    return next((a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or args[i - 1] != "-c")),
                "command")


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    kind: str
    oid: str
    size: int  # -1 when git did not report one (submodules)
    path: str  # decoded with surrogateescape, so it round-trips to git unchanged


class Git:
    """A repository opened for reading. Use as a context manager, or call ``close``."""

    def __init__(self, repo: str | os.PathLike[str]) -> None:
        self._scratch = Path(tempfile.mkdtemp(prefix="ofrenda-"))
        os.chmod(self._scratch, 0o700)
        self.work = self._scratch / "work"
        self.tmp = self._scratch / "tmp"
        self.shadow = self._scratch / "shadow.git"
        try:
            self.work.mkdir()
            self.tmp.mkdir()
            # git runs from the private folder, so a relative path is made absolute against the caller's
            # working directory first
            self.git_dir = self._discover(Path(repo).expanduser().absolute())
            self.bare = self._read_bare()
            self._build_shadow()
        except BaseException:
            self.close()
            raise

    # -- the real repository: plumbing questions only --------------------------------------------

    def _real(self, args: Sequence[str], *, check: bool = True, start: Path | None = None) -> bytes:
        if start is not None:
            command = ["git", *HARDENING, "-C", str(start), *args]
            env = _environment(self.tmp, None)
        else:
            command = ["git", *HARDENING, *args]
            env = _environment(self.tmp, self.git_dir, self.work)
        result = subprocess.run(command, capture_output=True, env=env, cwd=self.work, check=False)
        if check and result.returncode != 0:
            raise GitError(f"git {_command_name(args)} failed: {_first_line(result.stderr)}")
        return result.stdout

    def _discover(self, repo: Path) -> Path:
        if not repo.exists():
            raise GitError(f"{repo} does not exist")
        start = repo if repo.is_dir() else repo.parent
        try:
            out = self._real(["rev-parse", "--absolute-git-dir"], start=start)
        except GitError as error:
            raise GitError(f"{repo} is not a git repository ({str(error).split(': ', 1)[-1]})") from None
        return Path(os.fsdecode(out.strip()))

    def _read_bare(self) -> bool:
        """True when the repository has no working tree of its own (``core.bare`` in its config,
        read as a plain file, nothing run)."""
        out = subprocess.run(["git", "config", "--file", str(self.git_dir / "config"), "--bool", "core.bare"],
                             capture_output=True, env=_environment(self.tmp, None), cwd=self.work, check=False)
        return out.stdout.strip() == b"true"

    def _build_shadow(self) -> None:
        objects = self._real(["rev-parse", "--path-format=absolute", "--git-path", "objects"]).decode().strip()
        object_format = self._real(["rev-parse", "--show-object-format"], check=False).decode().strip() or "sha1"
        if not Path(objects).is_dir():
            raise GitError(f"{self.git_dir} has no object store")
        (self.shadow / "objects" / "info").mkdir(parents=True)
        (self.shadow / "refs" / "heads").mkdir(parents=True)
        (self.shadow / "refs" / "tags").mkdir()
        (self.shadow / "HEAD").write_text("ref: refs/heads/ofrenda-reads-objects-only\n", encoding="ascii")
        config = "[core]\n\trepositoryformatversion = {}\n\tbare = true\n".format(
            0 if object_format == "sha1" else 1)
        if object_format != "sha1":
            config += f"[extensions]\n\tobjectFormat = {object_format}\n"
        (self.shadow / "config").write_text(config, encoding="ascii")
        (self.shadow / "objects" / "info" / "alternates").write_text(objects + "\n", encoding="utf-8")
        shallow = Path(self._real(["rev-parse", "--path-format=absolute", "--git-path", "shallow"]).decode().strip())
        if shallow.is_file():
            shutil.copyfile(shallow, self.shadow / "shallow")

    def resolve(self, rev: str) -> str:
        """The commit id ``rev`` names in the real repository. ``--end-of-options`` keeps a
        revision that starts with a dash from being read as an option."""
        out = self._real(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"], check=False)
        oid = out.decode().strip()
        if not oid:
            raise GitError(f"{rev!r} is not a commit in this repository")
        return oid

    # -- the shadow: every other read --------------------------------------------------------------

    def run(self, args: Sequence[str], *, stdin: bytes | None = None, check: bool = True) -> bytes:
        """Run one git subcommand against the shadow repository and return its stdout."""
        result = subprocess.run(["git", *HARDENING, *args], input=stdin, capture_output=True,
                                env=_environment(self.tmp, self.shadow, self.work), cwd=self.work, check=False)
        if check and result.returncode != 0:
            raise GitError(f"git {_command_name(args)} failed: {_first_line(result.stderr)}")
        return result.stdout

    def close(self) -> None:
        shutil.rmtree(self._scratch, ignore_errors=True)

    def __enter__(self) -> Git:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def scratch(self) -> Path:
        """The private folder that holds the shadow, the empty work tree and temp files."""
        return self._scratch

    # -- reads ------------------------------------------------------------------------------------

    def is_shallow(self) -> bool:
        return self.run(["rev-parse", "--is-shallow-repository"]).strip() == b"true"

    def shallow_marker(self) -> str:
        """The contents of the ``shallow`` file: blame results depend on it, so caches key on it."""
        try:
            return (self.shadow / "shallow").read_text(encoding="ascii", errors="replace")
        except OSError:
            return ""

    def ls_tree(self, oid: str) -> list[TreeEntry]:
        out = self.run(["ls-tree", "-r", "-z", "--long", "--full-tree", oid])
        entries = []
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, _, raw_path = record.partition(b"\t")
            mode, kind, obj, size = meta.split(None, 3)
            entries.append(TreeEntry(mode.decode(), kind.decode(), obj.decode(),
                                     int(size) if size.strip().isdigit() else -1,
                                     os.fsdecode(raw_path)))
        return entries

    def read_blobs(self, oids: Iterable[str]) -> dict[str, bytes]:
        """Contents of each blob, from one ``git cat-file --batch``. Missing objects are left out."""
        wanted = list(dict.fromkeys(oids))
        if not wanted:
            return {}
        out = self.run(["cat-file", "--batch"], stdin=("\n".join(wanted) + "\n").encode())
        blobs: dict[str, bytes] = {}
        position = 0
        for oid in wanted:
            end = out.index(b"\n", position)
            header = out[position:end].split()
            position = end + 1
            if len(header) < 3 or header[1] == b"missing":
                continue
            size = int(header[2])
            blobs[oid] = out[position:position + size]
            position += size + 1
        return blobs

    def read_path(self, oid: str, path: str) -> bytes | None:
        """The blob at ``path`` in commit ``oid``, or None when there is none."""
        spec = f"{oid}:{path}"
        out = self.run(["cat-file", "--batch"], stdin=(spec + "\n").encode())
        header, _, rest = out.partition(b"\n")
        fields = header.split()
        if len(fields) < 3 or fields[1] != b"blob":
            return None
        return rest[:int(fields[2])]

    def commits_that_exist(self, names: Iterable[str]) -> list[str]:
        """Full ids of the names that resolve to a commit, in order, without duplicates."""
        asked = [n for n in names if n and not n.startswith("-")]
        if not asked:
            return []
        out = self.run(["cat-file", "--batch-check=%(objectname) %(objecttype)"],
                       stdin=("".join(f"{n}^{{commit}}\n" for n in asked)).encode())
        found: list[str] = []
        for line in out.decode(errors="replace").splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] == "commit" and fields[0] not in found:
                found.append(fields[0])
        return found

    def check_attr(self, tree: str, paths: Sequence[str], names: Sequence[str]) -> dict[str, dict[str, str]]:
        """Attributes of ``paths`` as ``.gitattributes`` files in ``tree`` set them. Needs git 2.40
        or newer; an older git gives an empty answer."""
        if not paths:
            return {}
        out = self.run(["check-attr", f"--source={tree}", "-z", "--stdin", *names],
                       stdin=b"".join(os.fsencode(p) + b"\0" for p in paths), check=False)
        fields = out.split(b"\0")
        attrs: dict[str, dict[str, str]] = {}
        for i in range(0, len(fields) - 2, 3):
            path, name, value = os.fsdecode(fields[i]), fields[i + 1].decode(), fields[i + 2].decode()
            attrs.setdefault(path, {})[name] = value
        return attrs

    def mailmap_args(self, oid: str) -> list[str]:
        """``-c`` arguments that make git map identities with the ``.mailmap`` at ``oid``."""
        return ["-c", f"mailmap.blob={oid}:.mailmap"]

    def check_mailmap(self, oid: str, contacts: Sequence[str]) -> list[str]:
        """``git check-mailmap`` with the ``.mailmap`` at ``oid``: one mapped contact per input."""
        out = self.run([*self.mailmap_args(oid), "check-mailmap", "--", *contacts])
        return out.decode("utf-8", errors="replace").splitlines()
