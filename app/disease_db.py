import json
import logging
from app.config import DISEASE_DB_PATH

logger = logging.getLogger(__name__)

_db: list[dict] = []


def _load_db() -> list[dict]:
    global _db
    if not _db:
        try:
            with open(DISEASE_DB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _db = data.get("diseases", [])
        except Exception as e:
            logger.error(f"Failed to load disease database: {e}")
            _db = []
    return _db


def lookup_disease(crop: str, disease: str) -> dict | None:
    """
    Find the best matching disease entry from the local database.
    Matches on crop name and disease name (case-insensitive fuzzy match).
    """
    db = _load_db()
    if not db:
        return None

    crop_lower = crop.lower().strip()
    disease_lower = disease.lower().strip()

    # Exact match first
    for entry in db:
        if (
            entry.get("crop", "").lower() in crop_lower or crop_lower in entry.get("crop", "").lower()
        ) and (
            entry.get("name", "").lower() in disease_lower
            or disease_lower in entry.get("name", "").lower()
            or _keyword_match(disease_lower, entry.get("name", "").lower())
        ):
            return entry

    # Fallback: match on crop alone if disease is Healthy
    if "healthy" in disease_lower:
        for entry in db:
            if "healthy" in entry.get("id", "") and (
                entry.get("crop", "").lower() in crop_lower
                or crop_lower in entry.get("crop", "").lower()
            ):
                return entry

    return None


def _keyword_match(query: str, target: str) -> bool:
    """All meaningful words from query must appear in target to avoid false positives."""
    keywords = [w for w in query.split() if len(w) > 3]
    if not keywords:
        return False
    return all(kw in target for kw in keywords)


def get_db_treatment(crop: str, disease: str) -> dict | None:
    """Return treatment info from local DB, or None if not found."""
    entry = lookup_disease(crop, disease)
    if entry:
        return {
            "db_entry": entry,
            "treatment": entry.get("treatment", {}),
            "hindi_summary": entry.get("hindi_summary", ""),
            "severity_typical": entry.get("severity_typical", ""),
            "market_impact": entry.get("market_impact", ""),
            "scientific_name": entry.get("scientific_name", ""),
        }
    return None
