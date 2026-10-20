import pytest

from config import settings


def test_folders_created():
    settings.ensure_dirs()
    assert settings.RAW_DIR.is_dir()
    assert settings.OUTPUT_DIR.is_dir()


def test_raw_and_env_are_gitignored():
    ignored = (settings.PROJECT_ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in ignored
    assert "data/raw/" in ignored


@pytest.mark.skipif(not (settings.PROJECT_ROOT / ".env").exists(),
                    reason="no .env (fresh clone): add FRED_API_KEY to run this check")
def test_fred_key_loads_from_env():
    assert len(settings.get_fred_api_key()) > 0
