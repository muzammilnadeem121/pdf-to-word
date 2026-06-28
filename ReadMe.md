# Urdu PDF to Word Converter

A production-oriented application for converting Urdu PDF documents into editable Microsoft Word (`.docx`) files.

## Milestone 1

This milestone sets up the backend foundation only:

- Python package structure for future conversion modules
- FastAPI application shell
- Health-check endpoint
- Basic backend tests

PDF upload, OCR, extraction, layout preservation, Unicode normalization, and DOCX export will be implemented in later milestones.

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
models/
uploads/
output/
tests/
requirements.txt
```
