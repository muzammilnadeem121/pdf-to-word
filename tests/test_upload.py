from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app


client = TestClient(create_app())


def test_upload_pdf_saves_file() -> None:
    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "sample.pdf"
    assert payload["stored_filename"].endswith(".pdf")
    assert payload["content_type"] == "application/pdf"
    assert payload["size_bytes"] == 9
    assert payload["status"] == "uploaded"
    assert (Path("uploads") / payload["stored_filename"]).exists()


def test_upload_rejects_non_pdf_extension() -> None:
    response = client.post(
        "/upload",
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Only PDF files are supported."}


def test_upload_rejects_non_pdf_content_type() -> None:
    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Only application/pdf uploads are supported."}
