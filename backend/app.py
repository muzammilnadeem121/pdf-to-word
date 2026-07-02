from fastapi import FastAPI, File, UploadFile

from backend.config import settings
from services.upload_service import save_pdf_upload
from document_engine.pipeline import DocumentIntelligencePipeline
import logging
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from services.converter import ConversionService
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger = logging.getLogger(__name__)
    _conversion_service = ConversionService()
    _pipeline = DocumentIntelligencePipeline()

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/upload")
    async def upload_pdf(file: UploadFile = File(...)) -> dict[str, str | int]:
        result = await save_pdf_upload(file)
        return result.to_dict()

    @app.post("/convert/{file_id}")
    async def convert_pdf(file_id: str):
        upload_path = Path("uploads") / file_id
        if not upload_path.exists():
            raise HTTPException(status_code=404, detail=f"No uploaded file found with id: {file_id}")
        try:
            result = _pipeline.convert_to_docx(str(upload_path))
        except Exception as exc:
            logger.exception("Conversion failed for %s", file_id)
            raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}")
        return {
            "message": "Conversion successful",
            "download_url": f"/download/{result['filename']}",
            "total_pages": result["total_pages"],
        }


# ── New: Download endpoint ────────────────────────────────────────────────────

    @app.get("/download/{filename}")
    async def download_docx(filename: str):
        """
        Download a converted DOCX file by filename.
    
        filename is the value from the download_url returned by /convert.
        """
        # Security: strip any path traversal attempts
        safe_name = Path(filename).name
        file_path = Path("output") / safe_name
    
        if not file_path.exists() or file_path.suffix != ".docx":
            raise HTTPException(status_code=404, detail="File not found.")
    
        return FileResponse(
            path=str(file_path),
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            filename=safe_name,
        )

    return app


app = create_app()
