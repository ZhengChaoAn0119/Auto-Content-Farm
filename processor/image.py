import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def generate(image_prompt: str, gcp_project: str) -> bytes:
    """Generate a 9:16 image via Imagen 3 on Vertex AI and return raw PNG bytes."""
    client = genai.Client(vertexai=True, project=gcp_project, location="us-central1")

    logger.info("Generating Imagen 3 image: %s", image_prompt[:80])
    response = client.models.generate_images(
        model="imagen-3.0-generate-001",
        prompt=image_prompt,
        config=types.GenerateImagesConfig(
            aspect_ratio="9:16",
            number_of_images=1,
            safety_filter_level="BLOCK_ONLY_HIGH",
            person_generation="ALLOW_ADULT",
        ),
    )
    if not response.generated_images:
        raise RuntimeError(f"Imagen 3 returned no images (safety filter or quota). Prompt: {image_prompt[:120]}")
    return response.generated_images[0].image.image_bytes
