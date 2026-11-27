import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.receipts import InMemoryObjectStore

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
FIXTURES = CONTRACTS / "fixtures"

HOST = "host-secret-test"
REVIEWER = "reviewer-token-test"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def key_path(tmp_path):
    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    p = tmp_path / "receipt_signing.pem"
    p.write_bytes(pem)
    return p


@pytest.fixture
def settings(key_path):
    return Settings(
        _env_file=None,
        HOST_SECRET=HOST,
        REVIEWER_TOKEN=REVIEWER,
        RECEIPT_SIGNING_KEY_PATH=str(key_path),
    )


@pytest.fixture
def app(settings):
    app = create_app(settings)
    app.state.store = InMemoryObjectStore()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)
