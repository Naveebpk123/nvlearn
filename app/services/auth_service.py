from datetime import datetime, timezone

from flask import session


def _clear_pending_auth():
    session.pop("pending_register", None)
    session.pop("pending_login", None)
    session.pop("pending_auth_code", None)
    session.pop("pending_auth_expires_at", None)
    session.pop("pending_auth_email", None)


def _verification_is_valid(submitted_code):
    expected_code = session.get("pending_auth_code")
    expires_at = session.get("pending_auth_expires_at")
    if not expected_code or not expires_at:
        return False, "Your verification session expired. Please start again."
    if datetime.now(timezone.utc).timestamp() > expires_at:
        _clear_pending_auth()
        return False, "Your verification code expired. Please start again."
    if submitted_code != expected_code:
        return False, "That verification code is incorrect."
    return True, ""