import logging
import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

# Closest native DALL-E 3 size to 9:16
IMAGE_SIZE = "1024x1792"


def generate(image_prompt: str, api_key: str) -> bytes:
    """Generate a 9:16 image via DALL-E 3 and return raw PNG bytes."""
    client = OpenAI(api_key=api_key)

    logger.info("Generating DALL-E 3 image: %s", image_prompt[:80])
    response = client.images.generate(
        model="dall-e-3",
        prompt=image_prompt,
        size=IMAGE_SIZE,
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url
    logger.info("Image generated, downloading from URL")

    img_response = requests.get(image_url, timeout=30)
    img_response.raise_for_status()
    return img_response.content
