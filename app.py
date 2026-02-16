from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from pydantic import BaseModel
import os
import requests
import feedparser
from typing import List, Dict, Any

# Google Trends
from pytrends.request import TrendReq

# Reddit
import praw

# -----------------------------
# Load ENV
# -----------------------------
load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "scripts-bot")

# -----------------------------
# FastAPI App (OpenAPI disabled)
# -----------------------------
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# -----------------------------
# MODELS
# -----------------------------
class ImageRequest(BaseModel):
    prompt: str
    orientation: str = "landscape"

class TrendingRequest(BaseModel):
    source: str = "all"
    limit: int = 5
    country: str = "IN"
    language: str = "en"
    subreddit: str = "all"

# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.get("/")
def home():
    return {"status": "Backend running", "endpoints": ["/generate-image", "/trending"]}

# ==========================================================
# ================= IMAGE SECTION ==========================
# ==========================================================

@app.post("/generate-image")
def generate_image(payload: ImageRequest):

    if not PEXELS_API_KEY:
        raise HTTPException(status_code=500, detail="PEXELS_API_KEY missing in Render ENV")

    if not payload.prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    params = {
        "query": payload.prompt,
        "per_page": 1,
        "orientation": payload.orientation
    }

    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params=params,
            timeout=10
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)

    data = response.json()

    if not data.get("photos"):
        raise HTTPException(status_code=404, detail="No images found")

    photo = data["photos"][0]

    return {
        "success": True,
        "image_url": photo["src"]["large"],
        "photographer": photo["photographer"],
        "source": "pexels"
    }

# ==========================================================
# ================= TREND SECTION ==========================
# ==========================================================

def clamp_limit(n: int) -> int:
    return max(1, min(n, 10))

def rss_top(rss_url: str, limit: int) -> List[Dict[str, Any]]:
    feed = feedparser.parse(rss_url)
    items = []
    for entry in feed.entries[:limit]:
        items.append({
            "title": getattr(entry, "title", ""),
            "link": getattr(entry, "link", ""),
            "published": getattr(entry, "published", "")
        })
    return items

def get_google_news(limit: int, country: str, language: str):
    rss_url = f"https://news.google.com/rss?hl={language}-{country}&gl={country}&ceid={country}:{language}"
    return {"source": "google_news", "items": rss_top(rss_url, limit)}

def get_reuters(limit: int):
    rss_url = "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"
    return {"source": "reuters", "items": rss_top(rss_url, limit)}

def get_flipboard(limit: int):
    rss_url = "https://flipboard.com/@news.rss"
    return {"source": "flipboard", "items": rss_top(rss_url, limit)}

def get_google_trends(limit: int, country: str):
    pn_map = {
        "IN": "india",
        "US": "united_states",
        "GB": "united_kingdom",
        "CA": "canada",
        "AU": "australia"
    }
    pn = pn_map.get(country.upper(), "india")

    pytrend = TrendReq()
    df = pytrend.trending_searches(pn=pn)
    terms = df.head(limit).iloc[:, 0].tolist()

    return {
        "source": "google_trends",
        "items": [{"title": t, "link": "", "published": ""} for t in terms]
    }

def get_reddit(limit: int, subreddit_name: str):

    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return {"source": "reddit", "items": [], "warning": "Reddit keys missing"}

    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )

    sub = reddit.subreddit(subreddit_name)
    items = []

    for post in sub.hot(limit=limit):
        items.append({
            "title": post.title,
            "link": post.url,
            "published": ""
        })

    return {"source": "reddit", "items": items}

@app.post("/trending")
def trending(payload: TrendingRequest):

    limit = clamp_limit(payload.limit)
    source = payload.source.lower()

    allowed = {"all", "google_trends", "google_news", "reddit", "reuters", "flipboard"}

    if source not in allowed:
        raise HTTPException(status_code=400, detail="Invalid source")

    results = []
    errors = []

    def safe_call(fn, name):
        try:
            results.append(fn())
        except Exception as e:
            errors.append({"source": name, "error": str(e)})

    if source in ("all", "google_trends"):
        safe_call(lambda: get_google_trends(limit, payload.country), "google_trends")

    if source in ("all", "google_news"):
        safe_call(lambda: get_google_news(limit, payload.country, payload.language), "google_news")

    if source in ("all", "reddit"):
        safe_call(lambda: get_reddit(limit, payload.subreddit), "reddit")

    if source in ("all", "reuters"):
        safe_call(lambda: get_reuters(limit), "reuters")

    if source in ("all", "flipboard"):
        safe_call(lambda: get_flipboard(limit), "flipboard")

    return {
        "success": True,
        "requested_source": source,
        "limit": limit,
        "data": results,
        "errors": errors
    }


