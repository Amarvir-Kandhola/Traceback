import pytest
from fastapi.testclient import TestClient

from tracebackai.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
