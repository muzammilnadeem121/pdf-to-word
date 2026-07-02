from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from backend.config import Settings, settings


@dataclass(frozen=True)
class UploadResult:
    filename: str
    stored_filename: str
    content_type: str
    size_bytes: int
    status: str = "uploaded"

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


async def save_pdf_upload(file: UploadFile, app_settings: Settings = settings) -> UploadResult:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A PDF file name is required.",
        )

    if Path(filename).suffix.lower() != app_settings.allowed_upload_extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    if file.content_type != app_settings.allowed_upload_content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only application/pdf uploads are supported.",
        )

    contents = await file.read()
    stored_filename = f"{uuid4().hex}{app_settings.allowed_upload_extension}"
    upload_path = app_settings.upload_dir / stored_filename
    app_settings.upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(contents)

    return UploadResult(
        filename=filename,
        stored_filename=stored_filename,
        content_type=file.content_type,
        size_bytes=len(contents),
    )
