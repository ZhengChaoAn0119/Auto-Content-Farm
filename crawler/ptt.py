import logging
import re
from curl_cffi import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PTT_BASE = "https://www.ptt.cc"
SESSION_COOKIES = {"over18": "1"}


def _parse_push_count(raw: str) -> int:
    """Convert PTT push label to integer. '爆'→100, 'XX'→-100, numeric→int."""
    raw = raw.strip()
    if raw == "爆":
        return 100
    if raw.startswith("X"):
        return -100
    try:
        return int(raw)
    except ValueError:
        return 0


_IMPERSONATE_TARGETS = ["chrome124", "safari17_0", "chrome116", "chrome120"]


def _fetch_page(url: str) -> BeautifulSoup:
    last_err: Exception | None = None
    for target in _IMPERSONATE_TARGETS:
        try:
            resp = requests.get(url, cookies=SESSION_COOKIES, impersonate=target, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.debug("Impersonate target %s failed for %s: %s", target, url, e)
            last_err = e
    raise last_err


def _fetch_post_content(url: str) -> str:
    """Fetch the body text of a single PTT post."""
    try:
        soup = _fetch_page(url)
        content_div = soup.find("div", id="main-content")
        if not content_div:
            return ""
        # Remove metadata spans and push sections
        for tag in content_div.find_all(["div", "span"], class_=re.compile(r"article-meta|push")):
            tag.decompose()
        return content_div.get_text(separator="\n").strip()
    except Exception as e:
        logger.warning("Failed to fetch post content from %s: %s", url, e)
        return ""


def fetch_popular_posts(board: str, threshold: int, max_posts: int) -> list[dict]:
    """
    Return up to `max_posts` posts from the PTT `board` with push count >= `threshold`.
    Each dict has: title, url, push_count, author, content.
    """
    collected: list[dict] = []
    index_url = f"{PTT_BASE}/bbs/{board}/index.html"

    while len(collected) < max_posts and index_url:
        logger.info("Fetching PTT index: %s", index_url)
        try:
            soup = _fetch_page(index_url)
        except Exception as e:
            logger.error("Failed to fetch PTT index page %s: %s", index_url, e)
            break

        entries = soup.select("div.r-ent")
        for entry in reversed(entries):
            push_el = entry.select_one("div.nrec span")
            link_el = entry.select_one("div.title a")
            meta_el = entry.select_one("div.meta div.author")

            if not link_el:
                continue  # deleted post

            push_count = _parse_push_count(push_el.text) if push_el else 0
            if push_count < threshold:
                continue

            post_url = PTT_BASE + link_el["href"]
            title = link_el.text.strip()
            author = meta_el.text.strip() if meta_el else ""

            logger.info("Qualifying post (push=%d): %s", push_count, title)
            content = _fetch_post_content(post_url)

            collected.append({
                "title": title,
                "url": post_url,
                "push_count": push_count,
                "author": author,
                "content": content,
            })

            if len(collected) >= max_posts:
                break

        if len(collected) >= max_posts:
            break

        # Navigate to previous page
        prev_link = soup.select_one("a.btn.wide:-soup-contains('上頁')")
        if prev_link and prev_link.get("href"):
            index_url = PTT_BASE + prev_link["href"]
        else:
            break

    logger.info("Fetched %d qualifying posts from PTT/%s", len(collected), board)
    return collected
