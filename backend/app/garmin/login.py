"""One-time interactive login. Prompts for credentials and MFA, caches tokens locally.

Usage: uv run python -m app.garmin.login
"""
import getpass
import os

from garminconnect import Garmin

from .. import config


def main() -> None:
    email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ")
    password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")
    config.GARMIN_TOKENS.parent.mkdir(parents=True, exist_ok=True)
    api = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    api.login(str(config.GARMIN_TOKENS))
    print(f"Logged in as {api.get_full_name()}. Tokens saved to {config.GARMIN_TOKENS}")


if __name__ == "__main__":
    main()
