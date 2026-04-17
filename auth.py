"""
Lightweight auth for internal team use.

Cookie-based session with a simple user picker. No passwords — this is
an internal tool for ~10 known team members. Can be upgraded to M365/Entra
SSO later by swapping the login mechanism while keeping the same
get_current_user() dependency.
"""

import json
import logging
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

COOKIE_NAME = "zlq_user"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def get_current_user(request: Request) -> Optional[dict]:
    """Extract the current user from the session cookie.
    Returns None if not logged in."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    try:
        user = json.loads(cookie)
        if user.get("id") and user.get("name"):
            return user
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def set_user_cookie(response: Response, user: dict):
    """Set the session cookie with user identity."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=json.dumps({"id": user["id"], "name": user["name"], "role": user.get("role", "rep")}),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def clear_user_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME)


def require_login(request: Request) -> Optional[RedirectResponse]:
    """If user is not logged in, return a redirect to login. Otherwise return None."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/qbr/login", status_code=303)
    return None
