import json
import logging
import re
import google.generativeai as genai

logger = logging.getLogger(__name__)


def _init_client(api_key: str, model: str) -> genai.GenerativeModel:
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)


def summarize(post: dict, api_key: str, model: str) -> str:
    """Summarize a PTT post into 3–5 Traditional Chinese bullet points."""
    client = _init_client(api_key, model)
    prompt = f"""請將以下PTT股票版文章摘要成3到5個重點，使用繁體中文條列式呈現。
只輸出條列重點，不要加標題或額外說明。

標題：{post['title']}
內容：
{post['content'][:3000]}
"""
    response = client.generate_content(prompt)
    return response.text.strip()


def analyze_sentiment(summary: str, api_key: str, model: str) -> dict:
    """
    Return sentiment dict: {sentiment: 看多|看空|中立, confidence: int, reason: str}
    """
    client = _init_client(api_key, model)
    prompt = f"""根據以下股票討論摘要，判斷市場情緒。
請以JSON格式回覆，包含以下欄位：
- sentiment: 只能是「看多」、「看空」或「中立」其中一個
- confidence: 信心程度，0到100的整數
- reason: 一句話說明判斷依據（繁體中文）

摘要：
{summary}

只輸出JSON，不要有其他文字。
"""
    response = client.generate_content(prompt)
    text = response.text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```json\s*|^```\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse sentiment JSON: %s", text)
        return {"sentiment": "中立", "confidence": 50, "reason": "無法解析"}


def generate_post_text(summaries: list[str], sentiments: list[dict], api_key: str, model: str) -> str:
    """Generate a YouTube Community Post in Traditional Chinese based on today's PTT stock summaries."""
    client = _init_client(api_key, model)

    sentiment_counts = {"看多": 0, "看空": 0, "中立": 0}
    for s in sentiments:
        key = s.get("sentiment", "中立")
        sentiment_counts[key] = sentiment_counts.get(key, 0) + 1

    dominant = max(sentiment_counts, key=sentiment_counts.get)
    summaries_text = "\n\n".join(f"• {s}" for s in summaries)

    prompt = f"""根據今日PTT股票版熱門討論，撰寫一則YouTube社群貼文。

要求：
1. 使用繁體中文
2. 開頭要有吸引人的hook（一句話）
3. 條列今日市場重點（2到3點）
4. 一句話總結今日整體情緒（主要情緒：{dominant}）
5. 結尾加上互動呼籲，例如詢問觀眾看法
6. 總長度控制在280字以內
7. 不要使用hashtag
8. 不要加任何標題或說明文字，直接輸出貼文內容

今日討論摘要：
{summaries_text}

情緒統計：看多 {sentiment_counts['看多']} 篇、看空 {sentiment_counts['看空']} 篇、中立 {sentiment_counts['中立']} 篇
"""
    response = client.generate_content(prompt)
    return response.text.strip()


def generate_image_prompt(summaries: list[str], sentiments: list[dict], api_key: str, model: str) -> str:
    """Generate an English DALL-E prompt based on today's stock sentiment."""
    client = _init_client(api_key, model)

    dominant = max(
        {"看多": 0, "看空": 0, "中立": 0} | {s.get("sentiment", "中立"): 1 for s in sentiments},
        key=lambda k: sum(1 for s in sentiments if s.get("sentiment") == k),
    )
    mood_map = {"看多": "bullish, upward trend, green", "看空": "bearish, downward trend, red", "中立": "neutral, sideways, blue"}
    mood = mood_map.get(dominant, "neutral")

    prompt = f"""Create a concise English image generation prompt for a 9:16 financial illustration.
The Taiwan stock market today is {mood}.
Key topics from today: {'; '.join(summaries[:2])[:300]}

Output only the image prompt, under 200 characters, no explanations.
Style: modern financial infographic illustration, clean design, bold colors.
"""
    response = client.generate_content(prompt)
    return response.text.strip()
