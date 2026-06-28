from fastapi.testclient import TestClient

from backend.app import create_app


client = TestClient(create_app())


def test_root_returns_app_metadata() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Urdu PDF to Word Converter",
        "version": "0.1.0",
        "status": "running",
    }


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
