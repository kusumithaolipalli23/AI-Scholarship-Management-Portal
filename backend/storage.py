"""
Document storage abstraction.

- "local" (default): current behavior (backend/uploads/), now with real magic-byte
  content validation (not just trusting the file extension) and safe, random,
  non-guessable stored filenames.
- "supabase": uploads go to a Supabase Storage bucket via the Storage REST API
  (requests-based; no extra SDK dependency). Requires SUPABASE_URL and
  SUPABASE_SERVICE_ROLE_KEY. Not testable from this sandbox (no outbound
  network) — code-complete, verify against your real project.
"""
import io
import logging
import os
import uuid

import requests

from config import config

logger = logging.getLogger("scholarai.storage")

BASE_DIR = os.path.dirname(__file__)
LOCAL_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# Magic-byte signatures so a renamed .exe can't masquerade as a .pdf/.png/.jpg
_MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
}


class StorageError(Exception):
    pass


def validate_file(filename, file_bytes):
    """Raises StorageError with a user-facing message if the file is invalid.
    Checks: extension allow-list, size limit, and actual file signature
    (magic bytes) matching the claimed extension — this stops someone
    uploading e.g. a renamed executable as "resume.pdf"."""
    if "." not in filename:
        raise StorageError("File must have an extension")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        raise StorageError(f"Unsupported file format. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise StorageError("File exceeds 5MB size limit")
    if len(file_bytes) == 0:
        raise StorageError("File is empty")
    signatures = _MAGIC_SIGNATURES.get(ext, [])
    if signatures and not any(file_bytes.startswith(sig) for sig in signatures):
        raise StorageError("File content does not match its extension (failed content validation)")
    return ext


def save_document(filename, file_bytes):
    """
    Validates and stores a document. Returns a dict with at least
    `stored_name` (used to retrieve/delete it later) and `backend`.
    """
    ext = validate_file(filename, file_bytes)
    stored_name = f"{uuid.uuid4().hex}.{ext}"

    if config.STORAGE_BACKEND == "supabase":
        return _save_supabase(stored_name, file_bytes, ext)
    return _save_local(stored_name, file_bytes)


def _save_local(stored_name, file_bytes):
    path = os.path.join(LOCAL_UPLOAD_DIR, stored_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    logger.info(f"Stored document locally: {stored_name} ({len(file_bytes)} bytes)")
    return {"stored_name": stored_name, "backend": "local"}


def _save_supabase(stored_name, file_bytes, ext):
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise StorageError("Supabase storage is not configured (missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY)")
    content_types = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
    url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_STORAGE_BUCKET}/{stored_name}"
    headers = {
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": content_types.get(ext, "application/octet-stream"),
        "x-upsert": "true",
    }
    try:
        resp = requests.post(url, headers=headers, data=file_bytes, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Supabase storage upload failed: {e}")
        raise StorageError("Failed to upload document to Supabase Storage") from e
    logger.info(f"Stored document in Supabase Storage: {stored_name}")
    return {"stored_name": stored_name, "backend": "supabase"}


def load_document(stored_name):
    """Returns (file_bytes, content_type) or raises StorageError if not found."""
    if config.STORAGE_BACKEND == "supabase":
        return _load_supabase(stored_name)
    return _load_local(stored_name)


def _load_local(stored_name):
    path = os.path.join(LOCAL_UPLOAD_DIR, stored_name)
    if not os.path.isfile(path):
        raise StorageError("Document not found")
    with open(path, "rb") as f:
        return f.read()


def _load_supabase(stored_name):
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise StorageError("Supabase storage is not configured")
    url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_STORAGE_BUCKET}/{stored_name}"
    headers = {"Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Supabase storage download failed: {e}")
        raise StorageError("Document not found in Supabase Storage") from e
    return resp.content


def delete_document(stored_name):
    if config.STORAGE_BACKEND == "supabase":
        return _delete_supabase(stored_name)
    return _delete_local(stored_name)


def _delete_local(stored_name):
    path = os.path.join(LOCAL_UPLOAD_DIR, stored_name)
    try:
        os.remove(path)
    except OSError:
        pass


def _delete_supabase(stored_name):
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        return
    url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_STORAGE_BUCKET}/{stored_name}"
    headers = {"Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"}
    try:
        requests.delete(url, headers=headers, timeout=20)
    except requests.RequestException as e:
        logger.warning(f"Supabase storage delete failed (non-fatal): {e}")
