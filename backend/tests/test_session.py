from app.auth.session import SessionManager

SECRET = "x" * 32
STEAM_ID = "76561198000000001"


def test_roundtrip():
    sessions = SessionManager(SECRET, 3600)
    assert sessions.read(sessions.issue(STEAM_ID)) == STEAM_ID


def test_tampered_token_rejected():
    token = SessionManager(SECRET, 3600).issue(STEAM_ID)
    assert SessionManager(SECRET, 3600).read(token[:-2] + "aa") is None


def test_token_signed_with_other_secret_rejected():
    token = SessionManager("y" * 32, 3600).issue(STEAM_ID)
    assert SessionManager(SECRET, 3600).read(token) is None


def test_expired_token_rejected():
    token = SessionManager(SECRET, 3600).issue(STEAM_ID)
    assert SessionManager(SECRET, -1).read(token) is None


def test_missing_or_garbage_token():
    sessions = SessionManager(SECRET, 3600)
    assert sessions.read(None) is None
    assert sessions.read("") is None
    assert sessions.read("not-a-token") is None


def test_payload_with_invalid_steam_id_rejected():
    sessions = SessionManager(SECRET, 3600)
    assert sessions.read(sessions._serializer.dumps({"sid": "123"})) is None
    assert sessions.read(sessions._serializer.dumps(["76561198000000001"])) is None
