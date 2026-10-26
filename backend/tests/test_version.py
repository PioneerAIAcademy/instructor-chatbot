"""The deployed version: APP_VERSION, else Render's commit."""

from app.version import app_version


def test_app_version_prefers_the_build_arg(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc1234")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "fffffffffffffffffffffffffffffffffffffff0")
    assert app_version() == "abc1234"


def test_app_version_falls_back_to_render(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "4fb5163a9e0c1d2e3f405162738495a6b7c8d9e0")
    assert app_version() == "4fb5163"


def test_app_version_none_when_unknown(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert app_version() is None
