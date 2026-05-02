import json
import logging
import time
from google.cloud import storage
from google.api_core.exceptions import NotFound

logger = logging.getLogger(__name__)

COOKIES_PATH = "cookies/youtube_cookies.json"
PROCESSED_PATH = "processed/processed_urls.json"
IMAGES_PREFIX = "images/"


def _client(bucket_name: str) -> tuple[storage.Client, storage.Bucket]:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    return client, bucket


def load_cookies(bucket_name: str) -> list | None:
    _, bucket = _client(bucket_name)
    blob = bucket.blob(COOKIES_PATH)
    try:
        data = blob.download_as_text()
        return json.loads(data)
    except NotFound:
        logger.info("No cookie file found in GCS")
        return None


def save_cookies(bucket_name: str, cookies: list) -> None:
    _, bucket = _client(bucket_name)
    blob = bucket.blob(COOKIES_PATH)
    blob.upload_from_string(json.dumps(cookies), content_type="application/json")
    logger.info("Cookies saved to GCS")


def load_processed_urls(bucket_name: str) -> set[str]:
    _, bucket = _client(bucket_name)
    blob = bucket.blob(PROCESSED_PATH)
    try:
        data = blob.download_as_text()
        return set(json.loads(data))
    except NotFound:
        return set()


def save_processed_urls(bucket_name: str, urls: set[str]) -> None:
    _, bucket = _client(bucket_name)
    blob = bucket.blob(PROCESSED_PATH)
    blob.upload_from_string(json.dumps(list(urls)), content_type="application/json")
    logger.info("Processed URLs saved to GCS (%d total)", len(urls))


def upload_image(bucket_name: str, image_bytes: bytes) -> str:
    """Upload image bytes to GCS and return the blob path."""
    _, bucket = _client(bucket_name)
    blob_path = f"{IMAGES_PREFIX}temp_{int(time.time())}.png"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(image_bytes, content_type="image/png")
    logger.info("Image uploaded to GCS: %s", blob_path)
    return blob_path


def download_image(bucket_name: str, blob_path: str) -> bytes:
    _, bucket = _client(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.download_as_bytes()


def delete_image(bucket_name: str, blob_path: str) -> None:
    _, bucket = _client(bucket_name)
    blob = bucket.blob(blob_path)
    try:
        blob.delete()
        logger.info("Deleted image from GCS: %s", blob_path)
    except NotFound:
        pass
