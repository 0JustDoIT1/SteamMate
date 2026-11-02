"""서명 쿠키 세션. 쿠키에는 steamId만 담고, 서버는 사용자 정보를 저장하지 않는다."""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "sm_session"
_SALT = "steammate-session-v1"


class SessionManager:
    def __init__(self, secret: str, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)
        self.max_age_seconds = max_age_seconds

    def issue(self, steam_id: str) -> str:
        return self._serializer.dumps({"sid": steam_id})

    def read(self, token: str | None) -> str | None:
        """유효한 토큰이면 steamId, 위조·만료·형식 오류면 None."""
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=self.max_age_seconds)
        except (SignatureExpired, BadSignature):
            return None
        steam_id = data.get("sid") if isinstance(data, dict) else None
        if not isinstance(steam_id, str) or not (steam_id.isdigit() and len(steam_id) == 17):
            return None
        return steam_id
