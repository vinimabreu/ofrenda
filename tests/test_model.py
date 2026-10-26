from __future__ import annotations

import urllib.request
from typing import Any

import pytest

from conftest import REAL_CHECK_LOCAL_MODEL
from ofrenda import model


@pytest.mark.parametrize("host", ["127.0.0.1:11434", "http://localhost:11434", "127.9.9.9", "[::1]:11434", "::1",
                                  "0.0.0.0:11434", "http://[::]:11434"])
def test_loopback_hosts(host: str) -> None:
    assert model.is_loopback(host)


@pytest.mark.parametrize("host", ["192.168.1.20:11434", "http://ollama.example:11434", "10.0.0.5", "8.8.8.8",
                                  "https://gpu-box.example"])
def test_hosts_off_this_machine(host: str) -> None:
    assert not model.is_loopback(host)


def test_a_remote_host_is_refused_before_any_request() -> None:
    with pytest.raises(model.RemoteHostRefused, match="--allow-remote-model"):
        model.asker(host="192.168.1.20:11434")
    with pytest.raises(model.RemoteHostRefused):
        model.chat("s", "u", host="http://ollama.example:11434")
    with pytest.raises(model.RemoteHostRefused):
        model.digest(host="10.0.0.5")


def test_a_remote_host_is_allowed_only_on_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_call(host: str, path: str, body: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        seen.append(model.base_url(host) + path)
        return {"message": {"content": '{"text": "", "quotes": []}'}}

    monkeypatch.setattr(model, "_call", fake_call)
    ask = model.asker(host="10.0.0.5:11434", allow_remote=True)
    assert ask("s", "u", None) == '{"text": "", "quotes": []}'
    assert seen == ["http://10.0.0.5:11434/api/chat"]


@pytest.mark.parametrize("name", ["gpt-oss:120b-cloud", "kimi-k2:cloud", "Qwen3-Coder:480B-CLOUD"])
def test_cloud_models_are_refused_by_name(name: str) -> None:
    with pytest.raises(model.RemoteHostRefused, match="cloud model"):
        REAL_CHECK_LOCAL_MODEL(name)


def test_a_model_ollama_forwards_elsewhere_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model, "_call", lambda *a, **k: {"remote_host": "https://ollama.example"})
    with pytest.raises(model.RemoteHostRefused, match=r"runs on https://ollama\.example"):
        REAL_CHECK_LOCAL_MODEL("plain-name")
    monkeypatch.setattr(model, "_call", lambda *a, **k: {"details": {}})
    REAL_CHECK_LOCAL_MODEL("plain-name")
    REAL_CHECK_LOCAL_MODEL("whatever:cloud", allow_remote=True)


@pytest.mark.parametrize("host, url", [("127.0.0.1", "http://127.0.0.1:11434"), ("localhost:8080",
                                                                                 "http://localhost:8080"),
                                       ("::1", "http://[::1]:11434"), ("https://[::1]:1234/x", "https://[::1]:1234")])
def test_base_url(host: str, url: str) -> None:
    assert model.base_url(host) == url


@pytest.mark.parametrize("host", ["", "ftp://127.0.0.1", "http://", "127.0.0.1:notaport"])
def test_unreadable_addresses_say_so(host: str) -> None:
    with pytest.raises(model.ModelUnavailable, match="can't read the Ollama address"):
        model.base_url(host)


def test_the_opener_has_no_proxy_and_no_redirects() -> None:
    kinds = {type(handler) for handler in model._OPENER.handlers}
    assert urllib.request.HTTPRedirectHandler not in kinds
    # an empty ProxyHandler registers nothing, so no handler on the opener knows any proxy,
    # whatever http_proxy says
    assert all(not getattr(h, "proxies", None) for h in model._OPENER.handlers)


def test_the_chat_body_is_temperature_zero_json_and_no_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies: list[dict[str, Any]] = []

    def fake_call(host: str, path: str, body: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        assert body is not None
        bodies.append(body)
        return {"message": {"content": "  reply  "}}

    monkeypatch.setattr(model, "_call", fake_call)
    assert model.chat("system", "user", schema={"type": "object"}) == "reply"
    body = bodies[0]
    assert body["options"]["temperature"] == 0 and body["think"] is False and body["stream"] is False
    assert body["format"] == {"type": "object"} and body["model"] == model.DEFAULT_MODEL
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
