from fastapi import FastAPI, File, UploadFile

from backend.config import settings
from services.upload_service import save_pdf_upload


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)

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

    return app


app = create_app()
