import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.auth.steam_openid import (
    OP_ENDPOINT,
    NonceStore,
    build_login_url,
    verify_callback,
)
from app.errors import AppError, ErrorCode

RETURN_TO = "http://localhost:3000/api/auth/steam/callback"
STEAM_ID = "76561198000000001"


def nonce(offset_seconds: int = 0, suffix: str = "abc") -> str:
    ts = datetime.fromtimestamp(time.time() + offset_seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ts + suffix


def callback_params(**overrides: str) -> dict[str, str]:
    claimed = f"https://steamcommunity.com/openid/id/{STEAM_ID}"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "id_res",
        "openid.op_endpoint": OP_ENDPOINT,
        "openid.claimed_id": claimed,
        "openid.identity": claimed,
        "openid.return_to": RETURN_TO,
        "openid.response_nonce": nonce(),
        "openid.assoc_handle": "1234567890",
        "openid.signed": "signed,op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
        "openid.sig": "c2lnbmF0dXJl",
    }
    params.update(overrides)
    return params


def steam_says(body: str, status: int = 200, seen: list | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(parse_qs(request.content.decode()))
        return httpx.Response(status, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_login_url_contains_openid_params():
    url = build_login_url(RETURN_TO, "http://localhost:3000")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == OP_ENDPOINT
    assert q["openid.mode"] == ["checkid_setup"]
    assert q["openid.return_to"] == [RETURN_TO]
    assert q["openid.realm"] == ["http://localhost:3000"]


async def test_valid_callback_returns_steam_id_and_sends_check_authentication():
    seen: list = []
    http = steam_says("ns:http://specs.openid.net/auth/2.0\r\nis_valid:true\r\n", seen=seen)
    steam_id = await verify_callback(callback_params(), RETURN_TO, http, NonceStore())
    assert steam_id == STEAM_ID
    assert seen[0]["openid.mode"] == ["check_authentication"]
    assert seen[0]["openid.sig"] == ["c2lnbmF0dXJl"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"openid.mode": "cancel"},
        {"openid.op_endpoint": "https://evil.example/openid/login"},
        {"openid.return_to": "https://evil.example/callback"},
        {"openid.claimed_id": "https://evil.example/openid/id/76561198000000001"},
        {"openid.claimed_id": "https://steamcommunity.com/openid/id/123"},
        {"openid.identity": "https://steamcommunity.com/openid/id/76561198000000002"},
        {"openid.response_nonce": "not-a-nonce"},
        {"openid.response_nonce": nonce(-3600)},
    ],
)
async def test_invalid_fields_rejected_before_calling_steam(overrides):
    http = steam_says("is_valid:true")
    with pytest.raises(AppError) as exc:
        await verify_callback(callback_params(**overrides), RETURN_TO, http, NonceStore())
    assert exc.value.code == ErrorCode.AUTH_FAILED


async def test_invalid_signature_rejected():
    with pytest.raises(AppError) as exc:
        await verify_callback(callback_params(), RETURN_TO, steam_says("is_valid:false"), NonceStore())
    assert exc.value.code == ErrorCode.AUTH_FAILED


async def test_steam_error_status_rejected():
    with pytest.raises(AppError):
        await verify_callback(callback_params(), RETURN_TO, steam_says("is_valid:true", 500), NonceStore())


async def test_network_error_rejected():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    http = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    with pytest.raises(AppError) as exc:
        await verify_callback(callback_params(), RETURN_TO, http, NonceStore())
    assert exc.value.code == ErrorCode.AUTH_FAILED


async def test_replayed_nonce_rejected():
    nonces = NonceStore()
    params = callback_params()
    http = steam_says("is_valid:true")
    assert await verify_callback(params, RETURN_TO, http, nonces) == STEAM_ID
    with pytest.raises(AppError):
        await verify_callback(params, RETURN_TO, http, nonces)


def test_nonce_store_expires_entries():
    store = NonceStore(max_age_seconds=300)
    n = nonce()
    now = time.time()
    assert store.check_and_store(n, now)
    assert not store.check_and_store(n, now + 10)
    # 만료 후에는 기록이 지워지지만, nonce 자체가 오래되어 여전히 거부된다.
    assert not store.check_and_store(n, now + 1000)
