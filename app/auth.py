from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.deps import get_settings

COOKIE_NAME = "consilium_session"
SESSION_MAX_AGE = 24 * 60 * 60  # 24h


def verify_google_token(token: str) -> dict:
    """Verify a Google ID token. Blocking; call via a threadpool. Raises on failure."""
    client_id = get_settings().google_client_id
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")
    info = id_token.verify_oauth2_token(
        token, google_requests.Request(), client_id, clock_skew_in_seconds=10
    )
    if not info.get("email_verified", False):
        raise ValueError("Google account email is not verified")
    return {
        "email": info["email"],
        "name": info.get("name", info["email"]),
        "picture": info.get("picture", ""),
    }


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="consilium-session")


def create_session_cookie(payload: dict) -> str:
    return _serializer().dumps(payload)


def read_session(cookie: str | None) -> dict | None:
    """Return the session payload, or None if missing/tampered/expired."""
    if not cookie:
        return None
    try:
        return _serializer().loads(cookie, max_age=SESSION_MAX_AGE)
    except BadSignature:  # SignatureExpired is a subclass
        return None