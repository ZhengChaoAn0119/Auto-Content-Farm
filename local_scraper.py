"""Scrape PTT locally, dispatch to Cloud Run for AI processing, save output locally."""
import json
import logging
import os
import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from config import get_config
from crawler.ptt import fetch_popular_posts
from storage import gcs

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

load_dotenv(override=True)

CLOUD_RUN_URL = os.environ["CLOUD_RUN_URL"]

posts = fetch_popular_posts(
    board=os.getenv("PTT_BOARD", "Stock"),
    threshold=int(os.getenv("PTT_PUSH_THRESHOLD", "50")),
    max_posts=int(os.getenv("MAX_POSTS_PER_RUN", "1")),
)

if not posts:
    print("No qualifying posts found — nothing to send.")
else:
    print(f"Sending {len(posts)} post(s) to Cloud Run...")
    resp = requests.post(f"{CLOUD_RUN_URL}/run",
                         json={"posts": posts}, timeout=300)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "ready":
        cfg = get_config()
        run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("output") / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        (out_dir / "post_text.txt").write_text(data["post_text"], encoding="utf-8")
        (out_dir / "processed_urls.json").write_text(
            json.dumps(data["processed_urls"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        image_bytes = gcs.download_image(cfg.gcs_bucket, data["image_blob_path"])
        (out_dir / "image.png").write_bytes(image_bytes)

        print(f"Saved to {out_dir}/")
        print(f"\nPost text:\n{data['post_text']}")
    else:
        print(data)
