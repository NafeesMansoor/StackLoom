import pytest


@pytest.fixture()
def home(tmp_path, monkeypatch):
    base = tmp_path / "home"
    monkeypatch.setenv("STACKLOOM_HOME", str(base))
    monkeypatch.delenv("STACKLOOM_ADMIN_PASSWORD", raising=False)
    from stackloom import paths

    paths.ensure(base)
    return base


@pytest.fixture()
def conn(home):
    from stackloom import db

    c = db.connect()
    yield c
    c.close()
