import logging
from twilio.rest import Client
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM

logger = logging.getLogger(__name__)

_twilio_client: Client | None = None


def get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client


def send_message(to: str, body: str) -> bool:
    """Send a WhatsApp message via Twilio. Returns True on success."""
    try:
        client = get_twilio_client()
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=to,
            body=body[:4096],  # WhatsApp message limit
        )
        logger.info(f"Message sent to {to}: SID={message.sid}")
        return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {to}: {e}")
        return False


def format_diagnosis_messages(result: dict, db_info: dict | None) -> list[str]:
    """
    Format diagnosis into two WhatsApp messages, each under 1550 chars.
    Returns [msg1_diagnosis, msg2_treatment]
    """
    crop = result.get("crop", "Unknown")
    disease = result.get("disease", "Unknown")
    severity = result.get("severity", "Unknown")
    confidence = result.get("confidence", "Low")
    symptoms = result.get("symptoms_observed", "")
    ai_treatment = result.get("treatment", {})
    hindi_summary = result.get("hindi_summary", "")

    sev_emoji = {"Healthy": "✅", "Mild": "🟡", "Moderate": "🟠", "Severe": "🔴"}.get(severity, "⚠️")
    conf_emoji = {"High": "🎯", "Medium": "🔵", "Low": "❓"}.get(confidence, "🔵")

    # --- Message 1: Diagnosis card ---
    m1 = [
        "🌿 *KrishiBot — Crop Disease Report*",
        "━━━━━━━━━━━━━━━━━",
        f"🌱 *Crop:* {crop}",
        f"🦠 *Disease:* {disease}",
        f"{sev_emoji} *Severity:* {severity}",
        f"{conf_emoji} *Confidence:* {confidence}",
    ]
    if db_info and db_info.get("scientific_name"):
        m1.append(f"🔬 _{db_info['scientific_name']}_")
    if db_info and db_info.get("market_impact"):
        m1.append(f"📉 *Risk:* {db_info['market_impact']}")
    if symptoms:
        m1 += ["", f"📋 *Symptoms:*", _trim(symptoms, 200)]

    final_hindi = db_info["hindi_summary"] if db_info and db_info.get("hindi_summary") else hindi_summary
    if final_hindi:
        m1 += ["", "🇮🇳 *हिंदी में:*", _trim(final_hindi, 300)]

    # --- Message 2: Treatment plan ---
    treatment = db_info["treatment"] if db_info else ai_treatment
    immediate = treatment.get("immediate") or ai_treatment.get("immediate", "")
    chemical  = treatment.get("chemical")  or ai_treatment.get("chemical", "")
    organic   = treatment.get("organic")   or ai_treatment.get("organic", "")
    prevention= treatment.get("prevention")or ai_treatment.get("prevention", "")

    m2 = ["💊 *Treatment Plan:*", "━━━━━━━━━━━━━━━━━"]
    if immediate:
        m2 += [f"⚡ *Now:* {_trim(immediate, 200)}"]
    if chemical:
        m2 += [f"🧪 *Chemical:* {_trim(chemical, 200)}"]
    if organic:
        m2 += [f"🌿 *Organic:* {_trim(organic, 150)}"]
    if prevention:
        m2 += [f"🛡️ *Prevent:* {_trim(prevention, 150)}"]
    m2 += ["", "📸 Send another photo | दूसरी फोटो भेजें"]

    return ["\n".join(m1), "\n".join(m2)]


def _trim(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


def format_help_message() -> str:
    return (
        "🌾 *KrishiBot — AI Crop Doctor* 🌾\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "मैं आपकी फसल की बीमारी पहचान सकता हूँ!\n"
        "I can diagnose crop diseases from photos!\n\n"
        "📸 *How to use:*\n"
        "1. Take a clear photo of the affected leaf or plant\n"
        "2. Send the photo here on WhatsApp\n"
        "3. Get instant diagnosis + treatment in Hindi & English\n\n"
        "🌱 *Supported crops:*\n"
        "Tomato • Potato • Pepper • Rice • Wheat • Cotton • Maize and more\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📸 अभी फोटो भेजें! / Send a photo now!"
    )
