import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "training.db"))
WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID", "")
WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET", "")
WHOOP_REDIRECT_URI = os.getenv(
    "WHOOP_REDIRECT_URI", "http://localhost:8000/auth/whoop/callback"
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
WHOOP_SCOPES = "offline read:recovery read:cycles read:sleep read:workout read:profile"

GARMIN_TOKENS = Path(os.getenv("GARMIN_TOKENS", ROOT / "data" / "garmin_tokens"))
