import logging
import tempfile
import os
from playwright.sync_api import sync_playwright, Page, BrowserContext

logger = logging.getLogger(__name__)

YOUTUBE_URL = "https://www.youtube.com"
STUDIO_COMMUNITY_URL = "https://studio.youtube.com"


def _is_logged_in(page: Page) -> bool:
    page.goto(YOUTUBE_URL, wait_until="networkidle")
    return page.locator("a[href*='/channel/']").count() > 0 or \
           page.locator("button[aria-label*='Account']").count() > 0


def _login(page: Page, email: str, password: str) -> None:
    logger.info("Performing YouTube login")
    page.goto("https://accounts.google.com/ServiceLogin?service=youtube", wait_until="networkidle")

    page.fill("input[type='email']", email)
    page.click("#identifierNext")
    page.wait_for_selector("input[type='password']", state="visible")

    page.fill("input[type='password']", password)
    page.click("#passwordNext")
    page.wait_for_url("**/youtube.com**", timeout=30000)
    logger.info("Login successful")


def _load_cookies(context: BrowserContext, cookies: list) -> None:
    context.add_cookies(cookies)


def _post_community(page: Page, text: str, image_bytes: bytes) -> None:
    logger.info("Navigating to YouTube Studio")
    page.goto(STUDIO_COMMUNITY_URL, wait_until="networkidle")

    # Navigate to Community tab
    community_link = page.locator("a[href*='/community']").first
    community_link.wait_for(state="visible", timeout=15000)
    community_link.click()
    page.wait_for_load_state("networkidle")

    # Click "Create post" button
    create_btn = page.locator("button:has-text('Create post'), ytcp-button:has-text('建立貼文')").first
    create_btn.wait_for(state="visible", timeout=15000)
    create_btn.click()

    # Type post text
    text_area = page.locator("div[contenteditable='true']").first
    text_area.wait_for(state="visible", timeout=10000)
    text_area.click()
    text_area.type(text, delay=20)

    # Upload image via temp file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        file_input = page.locator("input[type='file']")
        file_input.set_input_files(tmp_path)
        # Wait for image preview to appear
        page.wait_for_selector("img[src*='blob:'], ytcp-image-display", timeout=20000)
        logger.info("Image uploaded to post")
    finally:
        os.unlink(tmp_path)

    # Click Post button
    post_btn = page.locator("ytcp-button#post-button, button:has-text('Post'), button:has-text('發佈')").first
    post_btn.wait_for(state="visible", timeout=10000)
    post_btn.click()

    # Confirm post was published
    page.wait_for_load_state("networkidle")
    logger.info("Community post published successfully")


def post_community(
    post_text: str,
    image_bytes: bytes,
    yt_email: str,
    yt_password: str,
    cookies: list | None,
) -> list:
    """
    Post a YouTube Community Post with text and image.
    Returns updated cookies to persist back to GCS.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        if cookies:
            logger.info("Loading %d cookies from GCS", len(cookies))
            _load_cookies(context, cookies)

        page = context.new_page()

        if not _is_logged_in(page):
            logger.info("Not logged in, performing fresh login")
            _login(page, yt_email, yt_password)

        _post_community(page, post_text, image_bytes)

        updated_cookies = context.cookies()
        browser.close()

    return updated_cookies
