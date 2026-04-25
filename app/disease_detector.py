import httpx
import base64
import json
import re
import logging
from google import genai
from google.genai import types
from app.config import GOOGLE_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

logger = logging.getLogger(__name__)

_genai_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=GOOGLE_API_KEY)
    return _genai_client


SYSTEM_PROMPT = """You are KrishiBot, an expert agricultural disease diagnosis AI for Indian farmers.

Analyze the crop image and respond ONLY with valid JSON in this exact format:
{
  "crop": "crop name (e.g. Tomato, Potato, Pepper, Rice, Wheat, Cotton — or 'Unknown' if unclear)",
  "disease": "exact disease name or 'Healthy' if no disease found",
  "severity": "Healthy / Mild / Moderate / Severe",
  "confidence": "High / Medium / Low",
  "symptoms_observed": "brief 1-2 line description of what you see in the image",
  "treatment": {
    "immediate": "what farmer should do right now",
    "chemical": "specific pesticide/fungicide name and dose per litre of water used in India",
    "organic": "natural/organic alternative treatment",
    "prevention": "how to prevent this in future"
  },
  "hindi_summary": "2-3 sentences in Hindi script explaining the disease and key action for the farmer"
}

Rules:
- Be specific about chemical names and doses used in India
- If the image is NOT a crop/plant, set crop to 'Not a plant' and disease to 'Please send a clear photo of the affected crop leaf or plant'
- If image is blurry, set confidence to 'Low'
- Always include a Hindi summary
- Focus on crops grown in India"""


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    return None


async def download_image(image_url: str) -> tuple[bytes, str]:
    """Download image from Twilio URL using basic auth."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        response = await client.get(image_url, auth=auth)
        logger.info(f"Image download: status={response.status_code} size={len(response.content)} url={image_url[:60]}")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        if "text/html" in content_type or len(response.content) < 500:
            raise ValueError(f"Unexpected response: content-type={content_type}, size={len(response.content)}")
        return response.content, content_type


async def detect_disease(image_url: str) -> dict:
    """Download image and detect crop disease using Google Gemini Vision."""
    try:
        image_bytes, content_type = await download_image(image_url)
    except Exception as e:
        logger.error(f"Image download failed: {e}")
        return _error_result("Image download failed. Please resend the photo.")

    try:
        client = _get_client()

        # Convert content_type to Gemini mime type
        mime_type = content_type if content_type.startswith("image/") else "image/jpeg"

        logger.info(f"Calling Gemini with image: {len(image_bytes)} bytes, mime={mime_type}")

        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                SYSTEM_PROMPT,
            ],
        )

        raw = response.text
        logger.info(f"Gemini response: {raw[:300]}")

        result = _extract_json(raw)
        if result is None:
            logger.warning(f"Could not parse JSON from: {raw[:300]}")
            return _error_result("Could not parse AI response. Please resend the photo.")

        return result

    except Exception as e:
        logger.error(f"Gemini API error: {type(e).__name__}: {e}")
        return _error_result("AI service error. Please try again in a moment.")


def _error_result(message: str) -> dict:
    return {
        "crop": "Unknown",
        "disease": message,
        "severity": "Unknown",
        "confidence": "Low",
        "symptoms_observed": "",
        "treatment": {
            "immediate": "Please send a clear, well-lit photo of the affected leaf or plant.",
            "chemical": "",
            "organic": "",
            "prevention": "",
        },
        "hindi_summary": "फोटो विश्लेषण में समस्या हुई। कृपया प्रभावित पत्ती या पौधे की स्पष्ट फोटो दोबारा भेजें।",
    }
