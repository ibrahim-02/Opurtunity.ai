import re

from google.cloud import storage
from loguru import logger

import config.settings as _cfg


def _sanitize(name: str) -> str:
    """Make a string safe for use as a GCS path segment."""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name[:100]


def _description_path(company: str, title: str, job_id: int) -> str:
    return f"descriptions/{_sanitize(company)}/{_sanitize(title)}_{job_id}.txt"


def _chunk_path(company: str, title: str, job_id: int, chunk_index: int) -> str:
    return f"chunks/{_sanitize(company)}/{_sanitize(title)}_{job_id}_chunk_{chunk_index}.txt"


class GCSClient:
    def __init__(self):
        self._client = storage.Client.from_service_account_json(_cfg.GCS_KEY_PATH)
        self._bucket = self._client.bucket(_cfg.GCS_BUCKET_NAME)

    def upload_description(self, company: str, title: str, job_id: int, text: str) -> str:
        """Upload description text to GCS. Returns the gs:// URI."""
        path = _description_path(company, title, job_id)
        blob = self._bucket.blob(path)
        blob.upload_from_string(text, content_type="text/plain; charset=utf-8")
        uri = f"gs://{_cfg.GCS_BUCKET_NAME}/{path}"
        logger.debug(f"Uploaded description → {uri}")
        return uri

    def upload_chunk(self, company: str, title: str, job_id: int, chunk_index: int, text: str) -> str:
        """Upload a single chunk to GCS. Returns the gs:// URI."""
        path = _chunk_path(company, title, job_id, chunk_index)
        blob = self._bucket.blob(path)
        blob.upload_from_string(text, content_type="text/plain; charset=utf-8")
        uri = f"gs://{_cfg.GCS_BUCKET_NAME}/{path}"
        logger.debug(f"Uploaded chunk → {uri}")
        return uri

    def download_description(self, uri: str) -> str | None:
        """Download description text from a gs:// URI."""
        try:
            path = uri.replace(f"gs://{_cfg.GCS_BUCKET_NAME}/", "")
            blob = self._bucket.blob(path)
            return blob.download_as_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"GCS download failed for {uri}: {e}")
            return None

    def is_available(self) -> bool:
        try:
            next(iter(self._client.list_blobs(_cfg.GCS_BUCKET_NAME, max_results=1)), None)
            return True
        except Exception as e:
            logger.debug(f"GCS availability check failed: {e}")
            return False
