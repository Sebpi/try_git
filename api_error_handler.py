"""
Handles Anthropic API errors, including usage limit errors (HTTP 400).
"""

import re
from datetime import datetime, timezone


def parse_regain_access_time(message: str) -> datetime | None:
    """Extract the regain access timestamp from an API limit error message."""
    match = re.search(r"You will regain access on (\d{4}-\d{2}-\d{2} at \d{2}:\d{2} UTC)", message)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d at %H:%M UTC").replace(tzinfo=timezone.utc)
    return None


def handle_api_error(error: Exception) -> None:
    """
    Handle an Anthropic API error, printing a user-friendly message.

    Raises the error again if it is not a recognized usage limit error.
    """
    error_str = str(error)

    if "invalid_request_error" in error_str and "API usage limits" in error_str:
        regain_time = parse_regain_access_time(error_str)
        if regain_time:
            now = datetime.now(timezone.utc)
            wait_seconds = max(0, (regain_time - now).total_seconds())
            hours, remainder = divmod(int(wait_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            wait_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            print(
                f"API usage limit reached. Access will be restored at "
                f"{regain_time.strftime('%Y-%m-%d %H:%M UTC')} "
                f"(in approximately {wait_str})."
            )
        else:
            print("API usage limit reached. Please check your Anthropic dashboard for details.")
        return

    raise error


if __name__ == "__main__":
    # Example: simulate the error
    sample_error = Exception(
        "Anthropic API error: Error code: 400 - {'type': 'error', 'error': "
        "{'type': 'invalid_request_error', 'message': 'You have reached your "
        "specified API usage limits. You will regain access on 2026-04-01 at 00:00 UTC.'}, "
        "'request_id': 'req_011CZaZy9cdRArf7nGvNqXXP'}"
    )
    handle_api_error(sample_error)
