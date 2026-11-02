"""Steam OpenID 2.0 로그인. Steam이 확인해 준 claimed_id에서 본인 SteamID64를 얻는다.

검증 순서: 응답 필드 확인 → nonce 재사용·만료 확인 → Steam에 check_authentication으로 서명 재검증.
"""

import logging
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

OP_ENDPOINT = "https://steamcommunity.com/openid/login"
_NS = "http://specs.openid.net/auth/2.0"
_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
_CLAIMED_ID = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")
NONCE_MAX_AGE_SECONDS = 300


def build_login_url(return_to: str, realm: str) -> str:
    params = {
        "openid.ns": _NS,
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": _IDENTIFIER_SELECT,
        "openid.claimed_id": _IDENTIFIER_SELECT,
    }
    return f"{OP_ENDPOINT}?{urlencode(params)}"


class NonceStore:
    """처리한 response_nonce를 만료 시각까지 기억해 재사용(replay)을 막는다. 단일 인스턴스 전제."""

    def __init__(self, max_age_seconds: int = NONCE_MAX_AGE_SECONDS) -> None:
        self._seen: dict[str, float] = {}
        self._max_age = max_age_seconds

    def check_and_store(self, nonce: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self._seen = {n: exp for n, exp in self._seen.items() if exp > now}
        issued = _nonce_timestamp(nonce)
        if issued is None or abs(now - issued) > self._max_age or nonce in self._seen:
            return False
        self._seen[nonce] = now + self._max_age
        return True


def _nonce_timestamp(nonce: str) -> float | None:
    # 형식: 2026-11-03T12:34:56Z<임의 문자열>
    try:
        return datetime.strptime(nonce[:20], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


async def verify_callback(
    params: Mapping[str, str], expected_return_to: str, http: httpx.AsyncClient, nonces: NonceStore
) -> str:
    """콜백 파라미터를 검증하고 SteamID64를 반환한다. 실패 시 AUTH_FAILED."""
    if params.get("openid.mode") != "id_res":
        raise _failed("mode")
    if params.get("openid.op_endpoint") != OP_ENDPOINT:
        raise _failed("op_endpoint")
    if params.get("openid.return_to") != expected_return_to:
        raise _failed("return_to")
    claimed_id = params.get("openid.claimed_id", "")
    match = _CLAIMED_ID.match(claimed_id)
    if not match or params.get("openid.identity") != claimed_id:
        raise _failed("claimed_id")
    if not nonces.check_and_store(params.get("openid.response_nonce", "")):
        raise _failed("nonce")

    check = {k: v for k, v in params.items() if k.startswith("openid.")}
    check["openid.mode"] = "check_authentication"
    try:
        res = await http.post(OP_ENDPOINT, data=check)
    except httpx.HTTPError as exc:
        logger.warning("steam openid verification request failed: %s", type(exc).__name__)
        raise _failed("network") from exc
    if res.status_code != 200 or "is_valid:true" not in (line.strip() for line in res.text.splitlines()):
        raise _failed("signature")
    return match.group(1)


def _failed(reason: str) -> AppError:
    logger.info("steam openid rejected: %s", reason)
    return AppError(ErrorCode.AUTH_FAILED, "Steam 로그인 확인에 실패했습니다.", 401)
