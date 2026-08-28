from __future__ import annotations

import base64
import socket

import pytest

from app.services.simplefin import SimpleFinError, _decode_setup_token, access_parts


def test_setup_token_decoding_accepts_unpadded_urlsafe_base64() -> None:
    claim = "https://bridge.example.test/claim/once"
    token = base64.urlsafe_b64encode(claim.encode()).decode().rstrip("=")
    assert _decode_setup_token(token) == claim


def test_access_url_is_stripped_of_credentials_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    parts = access_parts("https://user%40name:p%3Aword@bridge.example.test/simplefin")
    assert parts.username == "user@name"
    assert parts.password == "p:word"
    assert parts.accounts_url == "https://bridge.example.test/simplefin/accounts"
    assert "user" not in parts.accounts_url
    assert "word" not in parts.accounts_url


def test_private_simplefin_host_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(SimpleFinError, match="private or reserved"):
        access_parts("https://user:password@example.test/simplefin")
