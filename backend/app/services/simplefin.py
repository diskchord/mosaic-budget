from __future__ import annotations

import base64
import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

from ..config import get_settings
from ..utils import sanitize_message

settings = get_settings()


class SimpleFinError(RuntimeError):
    def __init__(self, message: str, *, code: str = "simplefin.error", status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class AccessParts:
    accounts_url: str
    username: str
    password: str
    origin: tuple[str, str, int]


def _decode_setup_token(token: str) -> str:
    compact = "".join(token.split())
    compact += "=" * (-len(compact) % 4)
    try:
        decoded = base64.urlsafe_b64decode(compact.encode()).decode("utf-8")
    except Exception as exc:
        raise SimpleFinError("The SimpleFIN setup token is not valid Base64 text.", code="claim.invalid_token") from exc
    return decoded.strip()


def _validate_public_https_url(url: str, *, credentials_required: bool = False) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https":
        raise SimpleFinError("SimpleFIN URLs must use HTTPS.", code="security.non_https")
    if not parsed.hostname:
        raise SimpleFinError("SimpleFIN URL has no hostname.", code="security.invalid_host")
    if parsed.fragment:
        raise SimpleFinError("SimpleFIN URL must not contain a fragment.", code="security.invalid_url")
    if credentials_required and parsed.username is None:
        raise SimpleFinError("The claimed Access URL did not include Basic Auth credentials.", code="claim.no_credentials")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise SimpleFinError("Local network hosts are not allowed for SimpleFIN connections.", code="security.private_host")
    try:
        records = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SimpleFinError("The SimpleFIN hostname could not be resolved.", code="security.unresolved_host") from exc
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise SimpleFinError(
                "The SimpleFIN URL resolves to a private or reserved network address.",
                code="security.private_host",
            )


def claim_setup_token(setup_token: str) -> tuple[str, str]:
    claim_url = _decode_setup_token(setup_token)
    _validate_public_https_url(claim_url)
    try:
        response = httpx.post(
            claim_url,
            content=b"",
            headers={"Content-Length": "0", "User-Agent": f"{settings.app_name}/1.0"},
            timeout=settings.simplefin_timeout_seconds,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise SimpleFinError("Unable to reach the SimpleFIN claim endpoint.", code="claim.network") from exc
    if response.status_code == 403:
        raise SimpleFinError(
            "The setup token was rejected or had already been claimed. Disable it in SimpleFIN and create a new token.",
            code="claim.rejected",
            status_code=403,
        )
    if response.is_redirect:
        raise SimpleFinError("The SimpleFIN claim endpoint returned an unsafe redirect.", code="claim.redirect")
    if response.status_code != 200:
        raise SimpleFinError(
            f"SimpleFIN claim failed with HTTP {response.status_code}.",
            code="claim.http",
            status_code=response.status_code,
        )
    access_url = response.text.strip()
    if len(access_url) > 10000:
        raise SimpleFinError("The claimed Access URL was unexpectedly long.", code="claim.invalid_response")
    _validate_public_https_url(access_url, credentials_required=True)
    return access_url, hashlib.sha256(access_url.encode()).hexdigest()


def access_parts(access_url: str) -> AccessParts:
    _validate_public_https_url(access_url, credentials_required=True)
    parsed = urlsplit(access_url)
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or ""
    port = parsed.port or 443
    netloc = host if port == 443 else f"{host}:{port}"
    base_path = parsed.path.rstrip("/") + "/"
    clean_base = urlunsplit(("https", netloc, base_path, "", ""))
    accounts_url = urljoin(clean_base, "accounts")
    return AccessParts(accounts_url, username, password, ("https", host.casefold(), port))


def _validate_redirect_chain(response: httpx.Response, origin: tuple[str, str, int]) -> None:
    for item in [*response.history, response]:
        parsed = urlsplit(str(item.url))
        item_origin = (parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port or 443)
        if item_origin != origin:
            raise SimpleFinError("SimpleFIN redirected to a different host; the response was rejected.", code="sync.redirect")


def fetch_account_set(
    access_url: str,
    *,
    start_epoch: int,
    end_epoch: int,
) -> dict[str, Any]:
    parts = access_parts(access_url)
    params = {
        "version": "2",
        "start-date": str(start_epoch),
        "end-date": str(end_epoch),
        "pending": "1",
    }
    try:
        response = httpx.get(
            parts.accounts_url,
            params=params,
            auth=httpx.BasicAuth(parts.username, parts.password),
            headers={"Accept": "application/json", "User-Agent": f"{settings.app_name}/1.0"},
            timeout=settings.simplefin_timeout_seconds,
            follow_redirects=False,
        )
        # Do not follow provider redirects after attaching Basic Auth. Rejecting
        # them prevents both credential forwarding and redirect-based SSRF.
        if response.is_redirect:
            raise SimpleFinError(
                "SimpleFIN returned a redirect; the response was rejected for safety.",
                code="sync.redirect",
                status_code=response.status_code,
            )
    except SimpleFinError:
        raise
    except httpx.HTTPError as exc:
        raise SimpleFinError("Unable to reach SimpleFIN.", code="sync.network") from exc

    if response.status_code == 402:
        raise SimpleFinError("SimpleFIN reports that payment is required.", code="sync.payment_required", status_code=402)
    if response.status_code == 403:
        raise SimpleFinError(
            "SimpleFIN authorization failed or the Access URL was revoked.",
            code="sync.authorization",
            status_code=403,
        )
    if response.status_code != 200:
        raise SimpleFinError(
            f"SimpleFIN returned HTTP {response.status_code}.",
            code="sync.http",
            status_code=response.status_code,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SimpleFinError("SimpleFIN returned malformed JSON.", code="sync.invalid_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts"), list):
        raise SimpleFinError("SimpleFIN response is missing the accounts list.", code="sync.invalid_payload")
    if "errlist" not in payload:
        payload["errlist"] = [
            {"code": "gen.", "msg": sanitize_message(message)} for message in payload.get("errors", [])
        ]
    if not isinstance(payload.get("errlist"), list):
        raise SimpleFinError("SimpleFIN response has an invalid error list.", code="sync.invalid_payload")
    payload.setdefault("connections", [])
    return payload
