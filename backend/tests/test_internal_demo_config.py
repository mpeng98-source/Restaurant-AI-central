import importlib.util
from pathlib import Path

import pytest

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("demo_secrets", ROOT / "ops/demo/fetch_secrets.py")
secrets_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(secrets_module)


def test_secret_files_are_strict_private_and_not_overwritten(tmp_path):
    directory = tmp_path / "secrets"
    values = {key: "D7" + "x" * 40 for key in
              ("postgres_password", "app_password", "migration_password", "redis_password", "session_secret")}
    secrets_module.materialize(values, directory)
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "database_url").read_text().startswith("postgresql+psycopg://chubby_app:")
    assert (directory / "migration_database_url").read_text().startswith("postgresql+psycopg://chubby_migrator:")
    assert (directory / "session_secret").stat().st_mode & 0o777 == 0o444
    with pytest.raises(FileExistsError):
        secrets_module.materialize(values, directory)
    with pytest.raises(ValueError):
        secrets_module.materialize({**values, "unknown": "secret"}, tmp_path / "invalid")
    with pytest.raises(ValueError):
        secrets_module.materialize({**values, "session_secret": "short"}, tmp_path / "invalid")


def test_settings_load_managed_secret_mounts_without_environment_passwords(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    (tmp_path / "database_url").write_text("postgresql+psycopg://chubby_app:synthetic@db/chubby")
    (tmp_path / "session_secret").write_text("D7" + "x" * 40)
    settings = Settings(_env_file=None, _secrets_dir=tmp_path, environment="internal-demo",
                        cookie_secure=True, frontend_base_url="https://demo.example",
                        cors_origins=["https://demo.example"])
    assert settings.database_url.startswith("postgresql+psycopg://chubby_app:")
    assert settings.evidence_scanner_path is None
    assert settings.cookie_secure
