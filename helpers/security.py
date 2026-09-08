import hashlib
import hmac
import base64
import os
from config import settings

SENSITIVE_KEYS = {
    "BOT_TOKEN",
    "API_HASH",
    "DATA_URI",
    "SHORTED_LINK_API",
    "STRING",
}

def mask_sensitive_value(key: str, val: str) -> str:
    """Masque l'affichage des clés sensibles pour les logs et l'UI Telegram."""
    if not val or not isinstance(val, str):
        return str(val) if val is not None else ""
    if key in SENSITIVE_KEYS or "TOKEN" in key or "SECRET" in key or "PASS" in key or "KEY" in key or "URI" in key:
        if len(val) <= 8:
            return "********"
        return f"{val[:3]}...{val[-4:]}"
    return val
