import pytest

from app.config import ENV_FILE, Settings


def make(monkeypatch: pytest.MonkeyPatch, cors: str | None) -> Settings:
    if cors is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", cors)
    return Settings(_env_file=None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:3000", ["http://localhost:3000"]),
        ("http://a.com, http://b.com", ["http://a.com", "http://b.com"]),
        ('["http://a.com","http://b.com"]', ["http://a.com", "http://b.com"]),
        ("", []),
        (" , ", []),
    ],
)
def test_cors_origins_parsing(monkeypatch, raw, expected):
    assert make(monkeypatch, raw).cors_origins == expected


def test_cors_origins_default_when_unset(monkeypatch):
    assert make(monkeypatch, None).cors_origins == ["http://localhost:3000"]


def test_env_file_is_backend_dir_regardless_of_cwd():
    assert ENV_FILE.name == ".env"
    assert ENV_FILE.parent.name == "backend"


def test_missing_required_settings_fail(monkeypatch):
    monkeypatch.delenv("STEAM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="steam_api_key"):
        Settings(_env_file=None)
