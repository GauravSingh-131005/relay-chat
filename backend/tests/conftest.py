import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("LLM_API_KEYS", "test-key-1,test-key-2")
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "true")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", "Paris is the capital of France.")
    from app.main import app
    with TestClient(app) as c:
        yield c


def uid() -> str:
    return uuid.uuid4().hex[:8]
