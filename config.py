import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # PTT
    ptt_board: str = field(default_factory=lambda: os.getenv("PTT_BOARD", "Stock"))
    ptt_push_threshold: int = field(default_factory=lambda: int(os.getenv("PTT_PUSH_THRESHOLD", "30")))
    max_posts_per_run: int = field(default_factory=lambda: int(os.getenv("MAX_POSTS_PER_RUN", "3")))

    # Gemini
    gemini_api_key: str = field(default_factory=lambda: os.environ["GEMINI_API_KEY"])
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    # OpenAI
    openai_api_key: str = field(default_factory=lambda: os.environ["OPENAI_API_KEY"])

    # YouTube
    yt_email: str = field(default_factory=lambda: os.environ["YT_EMAIL"])
    yt_password: str = field(default_factory=lambda: os.environ["YT_PASSWORD"])

    # GCS
    gcs_bucket: str = field(default_factory=lambda: os.environ["GCS_BUCKET"])


def get_config() -> Config:
    return Config()
