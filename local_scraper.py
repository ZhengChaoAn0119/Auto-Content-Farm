"""Scrape PTT locally and dispatch posts to Cloud Run for processing."""
import logging
import os
import requests
from dotenv import load_dotenv
from crawler.ptt import fetch_popular_posts

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
    print(resp.json())
