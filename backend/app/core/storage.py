
"""Локальное хранилище + Timeweb S3."""
from __future__ import annotations

import io
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO, Optional

from fastapi.responses import FileResponse, Response

from app.core.config import settings

UPLOAD_DIR = Path("uploads")
MATERIALS_DIR = Path("materials")
ASSIGNMENT_FILES_DIR = Path("assignment_files")
for _d in (UPLOAD_DIR, MATERIALS_DIR, ASSIGNMENT_FILES_DIR):
    _d.mkdir(exist_ok=True)

def s3_enabled() -> bool:
    """True, если включено и настроено S3-хранилище."""
    return bool(
        getattr(settings, "s3_enabled", False)
        and getattr(settings, "s3_access_key", "")
        and getattr(settings, "s3_bucket", "")
    )

@lru_cache
def get_s3_client():
    """Кэшированный boto3-клиент S3 (Timeweb и совместимые)."""
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )

def upload_bytes(
    data: bytes,
    key: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Загружает байты в S3 и возвращает ключ объекта."""
    client = get_s3_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key

def download_bytes(key: str) -> bytes:
    """Скачивает объект из S3 по ключу."""
    client = get_s3_client()
    buf = io.BytesIO()
    client.download_fileobj(settings.s3_bucket, key, buf)
    return buf.getvalue()

def delete_object(key: str) -> None:
    """Удаляет объект из S3 по ключу (ошибки игнорируются)."""
    try:
        get_s3_client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except Exception:
        pass

def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Временная ссылка GET на объект S3."""
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )

def guess_content_type(filename: str) -> str:
    """MIME-тип по имени файла."""
    ct, _ = mimetypes.guess_type(filename)
    return ct or "application/octet-stream"

def save_upload(
    content: bytes,
    *,
    folder: str,
    safe_filename: str,
    original_name: str,
    extension: str,
) -> dict[str, Any]:
    """
    Сохраняет файл в S3 или локально.
    folder: 'uploads' | 'materials' | 'assignment_files'
    """
    size = len(content)
    content_type = guess_content_type(original_name)

    if s3_enabled():
        key = f"{folder}/{safe_filename}"
        upload_bytes(content, key, content_type)
        return {
            "storage": "s3",
            "key": key,
            "original_name": original_name,
            "saved_name": safe_filename,
            "size": size,
            "extension": extension,
            "path": key,
        }

    base = {
        "uploads": UPLOAD_DIR,
        "materials": MATERIALS_DIR,
        "assignment_files": ASSIGNMENT_FILES_DIR,
    }.get(folder, UPLOAD_DIR)
    file_path = base / safe_filename
    file_path.write_bytes(content)
    return {
        "storage": "local",
        "path": str(file_path),
        "original_name": original_name,
        "saved_name": safe_filename,
        "size": size,
        "extension": extension,
    }

def delete_stored(file_info: dict) -> None:
    """Удаляет файл из S3 или с диска по метаданным."""
    if not file_info:
        return
    key = file_info.get("key")
    if file_info.get("storage") == "s3" or (key and not file_info.get("path", "").startswith(("uploads", "materials", "assignment"))):
        if key:
            delete_object(key)
            return

        p = file_info.get("path")
        if p and file_info.get("storage") == "s3":
            delete_object(p)
            return
    path = file_info.get("path")
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except TypeError:

            fp = Path(path)
            if fp.exists():
                fp.unlink()
        except Exception:
            pass

FILE_MISSING_DETAIL = "Файл не найден или удалён из хранилища"

def file_missing_exception():
    """HTTP 404, если файл отсутствует в хранилище."""
    from fastapi import HTTPException
    return HTTPException(status_code=404, detail=FILE_MISSING_DETAIL)

def file_response(file_info: dict, filename: Optional[str] = None) -> Response:
    """Отдаёт файл из S3 или с диска. При отсутствии — HTTP 404 с понятным текстом."""
    if not file_info:
        raise file_missing_exception()

    name = filename or file_info.get("original_name") or file_info.get("saved_name") or file_info.get("name") or "file"

    if file_info.get("storage") == "s3" or file_info.get("key"):
        key = file_info.get("key") or file_info.get("path")
        if not key:
            raise file_missing_exception()
        try:
            data = download_bytes(key)
        except Exception:
            raise file_missing_exception()
        return Response(
            content=data,
            media_type=guess_content_type(name),
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    path = file_info.get("path", "") or ""
    fp = Path(path)
    if fp.exists() and fp.is_file():
        return FileResponse(path=str(fp), filename=name)

    if s3_enabled() and path and not fp.is_absolute():
        try:
            data = download_bytes(path)
            return Response(
                content=data,
                media_type=guess_content_type(name),
                headers={"Content-Disposition": f'attachment; filename="{name}"'},
            )
        except Exception:
            pass

    raise file_missing_exception()

def read_text_content(file_info_or_path) -> str:
    """Читает текстовое содержимое (для анализа кода)."""
    if isinstance(file_info_or_path, dict):
        info = file_info_or_path
        if info.get("storage") == "s3" or info.get("key"):
            key = info.get("key") or info.get("path")
            return download_bytes(key).decode("utf-8", errors="replace")
        path = Path(info.get("path", ""))
    else:
        path = Path(str(file_info_or_path))
        if s3_enabled() and not path.exists() and "/" in str(path):
            try:
                return download_bytes(str(path)).decode("utf-8", errors="replace")
            except Exception:
                return ""
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""
