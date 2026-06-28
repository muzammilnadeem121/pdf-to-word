from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "Urdu PDF to Word Converter"
    app_version: str = "0.1.0"
    upload_dir: Path = Path("uploads")
    output_dir: Path = Path("output")
    allowed_upload_extension: str = ".pdf"
    allowed_upload_content_type: str = "application/pdf"


settings = Settings()
