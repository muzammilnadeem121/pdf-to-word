# Urdu PDF to Word Converter

A production-oriented application for converting Urdu PDF documents into editable Microsoft Word (`.docx`) files.

## Milestone 1

This milestone sets up the backend foundation:

- Python package structure for future conversion modules
- FastAPI application shell
- Health-check endpoint
- Basic backend tests

## Milestone 2

This milestone adds PDF upload only:

- `POST /upload` multipart endpoint
- PDF extension and `application/pdf` content-type validation
- UUID-based local storage under `uploads/`
- Upload metadata response

OCR, extraction, layout preservation, Unicode normalization, and DOCX export will be implemented in later milestones.

## Backend setup

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run tests:

```bash
python -m pytest
```

Start the API:

```bash
python -m uvicorn backend.app:app --reload
```

Then open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`

Upload a PDF:

```bash
python - <<'PY'
from pathlib import Path
import httpx

sample = Path('sample.pdf')
sample.write_bytes(b'%PDF-1.7\n')
with sample.open('rb') as pdf:
    response = httpx.post(
        'http://127.0.0.1:8000/upload',
        files={'file': ('sample.pdf', pdf, 'application/pdf')},
    )
print(response.status_code)
print(response.json())
sample.unlink()
PY
```

## Current structure

```text
backend/
  app.py
  config.py
extractor/
ocr/
layout/
exporter/
services/
  upload_service.py
models/
uploads/
output/
tests/
requirements.txt
```
