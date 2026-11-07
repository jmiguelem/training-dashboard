from garminconnect import Garmin

from .. import config


class GarminNotLoggedIn(Exception):
    pass


def get_client() -> Garmin:
    """Log in from cached tokens only. Run `python -m app.garmin.login` to create them."""
    if not config.GARMIN_TOKENS.exists():
        raise GarminNotLoggedIn("No Garmin tokens. Run: uv run python -m app.garmin.login")
    api = Garmin()
    try:
        api.login(str(config.GARMIN_TOKENS))
    except Exception as exc:
        raise GarminNotLoggedIn(f"Garmin login failed: {exc}") from exc
    return api
