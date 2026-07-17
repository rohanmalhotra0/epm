"""Test fixtures. A fresh temp data dir + deterministic seeding (no env seed)."""

from __future__ import annotations

import os
import tempfile

# Must be set before importing app.config (which reads EPMW_DATA_DIR at first use).
os.environ["EPMW_DATA_DIR"] = tempfile.mkdtemp(prefix="epmw-test-")
os.environ["EPMW_DISABLE_ENV_SEED"] = "1"
os.environ["EPMW_LOG_JSON"] = "false"

import pytest  # noqa: E402

from app.artifacts import build_metadata_from_connector  # noqa: E402
from app.connector import DemoConnector, reset_demo_state  # noqa: E402
from app.db.base import get_sessionmaker  # noqa: E402
from app.db.init import initialize  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db() -> None:
    initialize(seed=True)


@pytest.fixture(autouse=True)
def _reset_demo() -> None:
    reset_demo_state()
    yield
    reset_demo_state()


@pytest.fixture
def session():
    SessionLocal = get_sessionmaker()
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@pytest.fixture
def demo_connector() -> DemoConnector:
    return DemoConnector()


@pytest.fixture
async def md():
    return await build_metadata_from_connector(DemoConnector(), "MCWPCF")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
