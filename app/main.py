import logging
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.disease_detector import detect_disease
from app.disease_db import get_db_treatment
from app.whatsapp_client import send_message, format_diagnosis_messages, format_help_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KrishiBot — AI Crop Disease Diagnosis",
    description="WhatsApp chatbot for Indian farmers to diagnose crop diseases via photo",
    version="1.0.0",
)

# Simple in-memory session: tracks last action per phone number
# In production, replace with Redis
_sessions: dict[str, dict] = {}

GREETINGS = {"hi", "hello", "hey", "hii", "namaste", "namaskar", "help", "start", "menu", "?", ""}


@app.get("/")
def health_check():
    return {"status": "KrishiBot is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Twilio sends POST with form-encoded data when a WhatsApp message arrives.
    Fields: From, Body, NumMedia, MediaUrl0, MediaContentType0
    """
    form = await request.form()

    from_number: str = form.get("From", "")
    body: str = form.get("Body", "").strip()
    num_media: int = int(form.get("NumMedia", 0))
    media_url: str = form.get("MediaUrl0", "")
    media_type: str = form.get("MediaContentType0", "")

    logger.info(f"Incoming from={from_number} | body='{body[:60]}' | media={num_media}")

    # Greeting or help request
    if num_media == 0 and body.lower() in GREETINGS:
        send_message(from_number, format_help_message())
        return PlainTextResponse("OK")

    # Image received — run disease detection
    if num_media > 0 and media_url and media_type.startswith("image/"):
        # Send acknowledgment first so farmer knows we received it
        send_message(
            from_number,
            "📸 Photo received! Analyzing your crop... please wait 10-15 seconds.\n"
            "फोटो मिली! फसल का विश्लेषण हो रहा है...",
        )

        result = await detect_disease(media_url)
        crop = result.get("crop", "")
        disease = result.get("disease", "")

        # Enrich with local disease database
        db_info = get_db_treatment(crop, disease) if crop and disease else None

        msg1, msg2 = format_diagnosis_messages(result, db_info)
        send_message(from_number, msg1)
        send_message(from_number, msg2)

        # Save session context
        _sessions[from_number] = {"last_crop": crop, "last_disease": disease}
        return PlainTextResponse("OK")

    # Non-image media (video, audio, document)
    if num_media > 0 and not media_type.startswith("image/"):
        send_message(
            from_number,
            "📸 Please send a *photo* (image) of the affected crop leaf or plant.\n"
            "कृपया प्रभावित पत्ती या पौधे की *फोटो* भेजें।",
        )
        return PlainTextResponse("OK")

    # Text question — answer as agri advisor
    if body:
        session = _sessions.get(from_number, {})
        last_crop = session.get("last_crop", "")
        last_disease = session.get("last_disease", "")

        context = f"Farmer previously asked about {last_crop} with {last_disease}. " if last_crop else ""
        _handle_text_question(from_number, body, context)
        return PlainTextResponse("OK")

    return PlainTextResponse("OK")


def _handle_text_question(to: str, question: str, context: str = "") -> None:
    """
    Answer a text question from the farmer using OpenRouter (text-only).
    Quick responses for common questions, else forward to AI.
    """
    q_lower = question.lower()

    # Quick FAQ responses
    if any(w in q_lower for w in ["dose", "kitna", "कितना", "amount", "quantity", "matra", "मात्रा"]):
        msg = (
            "💊 *Dosage Reminder:*\n"
            "Always mix chemicals as per label. General guidelines:\n"
            "• Mancozeb 75% WP: 2g per litre of water\n"
            "• Copper Oxychloride 50%: 3g per litre\n"
            "• Neem Oil: 5ml per litre + 2ml liquid soap\n"
            "• Imidacloprid 17.8% SL: 0.5ml per litre\n\n"
            "🌾 Spray early morning or evening. Wear gloves.\n"
            "📸 Send a photo for specific disease treatment."
        )
        send_message(to, msg)
        return

    if any(w in q_lower for w in ["spray", "when", "kab", "कब", "time", "samay"]):
        msg = (
            "⏰ *Best Time to Spray:*\n"
            "• Early morning (6-9 AM) or evening (4-7 PM)\n"
            "• Avoid spraying in afternoon heat or wind\n"
            "• Don't spray before rain (wash-off)\n"
            "• Re-spray after heavy rain\n\n"
            "🌾 *छिड़काव का सही समय:*\n"
            "सुबह 6-9 बजे या शाम 4-7 बजे करें।\n"
            "तेज धूप या बारिश से पहले छिड़काव न करें।"
        )
        send_message(to, msg)
        return

    # Default: prompt to send a photo
    msg = (
        f"🌾 *KrishiBot*\n\n"
        f"Your message: _{question}_\n\n"
        f"📸 For best diagnosis, please *send a photo* of the affected crop leaf or plant.\n\n"
        f"I support: Tomato • Potato • Pepper • Rice • Wheat • Cotton and more.\n\n"
        f"📸 प्रभावित पत्ती की फोटो भेजें — मैं तुरंत बीमारी पहचानूंगा!"
    )
    send_message(to, msg)
