import logging
import time
from config import Config
from crawler import ptt
from processor import gemini, image
from publisher import youtube
from storage import gcs

logger = logging.getLogger(__name__)


def run(cfg: Config, posts: list[dict] | None = None) -> dict:
    if posts is None:
        # 1. Fetch PTT posts
        logger.info("Step 1/6: Fetching PTT/%s posts (threshold=%d)", cfg.ptt_board, cfg.ptt_push_threshold)
        posts = ptt.fetch_popular_posts(cfg.ptt_board, cfg.ptt_push_threshold, cfg.max_posts_per_run)
    else:
        logger.info("Step 1/6: Using %d pre-fetched posts (local scrape)", len(posts))

    if not posts:
        logger.info("No posts met the push threshold — skipping run")
        return {"status": "skipped", "reason": "no posts above threshold"}

    # 2. Deduplicate
    logger.info("Step 2/6: Deduplicating against processed posts")
    processed_urls = gcs.load_processed_urls(cfg.gcs_bucket)
    new_posts = [p for p in posts if p["url"] not in processed_urls]

    if not new_posts:
        logger.info("All fetched posts already processed — skipping run")
        return {"status": "skipped", "reason": "all posts already processed"}

    logger.info("%d new posts to process", len(new_posts))

    # 3. Gemini: summarize + sentiment (batched into one call per post to reduce quota usage)
    logger.info("Step 3/6: Summarizing and analyzing sentiment via Gemini")
    summaries, sentiments = [], []
    for post in new_posts:
        summary, sentiment = gemini.summarize_and_analyze(post, cfg.gemini_api_key, cfg.gemini_model)
        summaries.append(summary)
        sentiments.append(sentiment)
        logger.info("Post '%s' → sentiment: %s (%d%%)", post["title"][:40], sentiment["sentiment"], sentiment["confidence"])
        time.sleep(4)

    # 4. Gemini: generate community post text + image prompt
    logger.info("Step 4/6: Generating community post text and image prompt")
    time.sleep(4)
    post_text = gemini.generate_post_text(summaries, sentiments, cfg.gemini_api_key, cfg.gemini_model)
    time.sleep(4)
    image_prompt = gemini.generate_image_prompt(summaries, sentiments, cfg.gemini_api_key, cfg.gemini_model)
    logger.info("Post text (%d chars): %s...", len(post_text), post_text[:60])

    # 5. Imagen 3: generate 9:16 image
    logger.info("Step 5/6: Generating 9:16 image via Imagen 3")
    image_bytes = image.generate(image_prompt, cfg.gcp_project)
    blob_path = gcs.upload_image(cfg.gcs_bucket, image_bytes)

    # 6. Playwright: post to YouTube Community
    logger.info("Step 6/6: Publishing YouTube Community Post")
    cookies = gcs.load_cookies(cfg.gcs_bucket)
    image_bytes_for_upload = gcs.download_image(cfg.gcs_bucket, blob_path)

    updated_cookies = youtube.post_community(
        post_text=post_text,
        image_bytes=image_bytes_for_upload,
        yt_email=cfg.yt_email,
        yt_password=cfg.yt_password,
        cookies=cookies,
    )

    # 7. Persist state
    gcs.save_cookies(cfg.gcs_bucket, updated_cookies)
    gcs.delete_image(cfg.gcs_bucket, blob_path)
    gcs.save_processed_urls(cfg.gcs_bucket, processed_urls | {p["url"] for p in new_posts})

    logger.info("Pipeline complete — %d posts published", len(new_posts))
    return {"status": "success", "posts_processed": len(new_posts)}
