from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from pydantic import BaseModel
import os
import requests

# -----------------------------
# Load ENV
# -----------------------------
load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

if not PEXELS_API_KEY:
    raise RuntimeError("PEXELS_API_KEY is missing")

# -----------------------------
# Disable OpenAPI
# -----------------------------
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# -----------------------------
# Request Model
# -----------------------------
class ImageRequest(BaseModel):
    prompt: str
    orientation: str = "landscape"

# -----------------------------
# Health Check
# -----------------------------
@app.get("/")
def home():
    return {"status": "Render backend running"}

# -----------------------------
# Image Endpoint
# -----------------------------
@app.post("/generate-image")
def generate_image(payload: ImageRequest):

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
        raise HTTPException(
            status_code=500,
            detail=f"Pexels error: {response.text}"
        )

    data = response.json()

    if not data.get("photos"):
        raise HTTPException(status_code=404, detail="No images found")

    photo = data["photos"][0]

    return {
        "success": True,
        "image_url": photo["src"]["large"],
        "photographer": photo["photographer"]
    }


