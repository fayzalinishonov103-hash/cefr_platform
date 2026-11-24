"""Security helpers: password policy, persistent rate limits, safe redirects, AI cost cap.

Rate limits live in the database (not in process memory), so they hold across gunicorn workers and restarts.
Behind a proxy the client IP comes from X-Forwarded-For; app.py trusts exactly PROXY_HOPS proxies (see README).
"""
import re
from datetime import datetime, timedelta, timezone

import logging

from flask import current_app, request
from werkzeug.security import generate_password_hash

from extensions import db
from models import AuthAttempt, UsageLog

PASSWORD_MIN, PASSWORD_MAX = 10, 128
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# Login: failures counted over WINDOW seconds
LOGIN_WINDOW = 15 * 60
LOGIN_PAIR_MAX = 5          # same IP + same email
LOGIN_IP_MAX = 20           # one IP trying many emails (credential stuffing)
LOGIN_EMAIL_MAX = 20        # many IPs against one email (distributed guessing)

# Hash used to spend the same time when the email does not exist (no timing difference -> no account enumeration)
DUMMY_HASH = generate_password_hash("timing-equaliser-not-a-real-password")

_COMMON = {
    "password12", "password123", "password1234", "password12345", "1234567890", "12345678910", "0123456789",
    "qwertyuiop", "qwerty1234", "qwerty12345", "qwerty123456", "1q2w3e4r5t", "1qaz2wsx3e", "iloveyou12",
    "iloveyou123", "abcd123456", "abc1234567", "admin12345", "administrator", "welcome123", "letmein123",
    "parol12345", "parol123456", "parolparol", "uzbekistan", "uzbekistan1", "toshkent123", "1111111111",
    "0000000000", "9876543210", "123456789a", "a123456789", "asdfghjkl1", "zxcvbnm123", "football123",
    "monkey1234", "dragon1234", "sunshine12", "princess12", "trustno1234", "cefr123456", "cefrcefr12",
}


def now():
    """Naive UTC (matches the DateTime columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def client_ip():
    return (request.remote_addr or "unknown")[:64]


# ------------------------------------------------------------------ input checks
def clean_email(raw):
    return (raw or "").strip().lower()[:120]


def valid_email(email):
    return bool(EMAIL_RE.match(email)) and ".." not in email and len(email) <= 120


# Throw-away mailbox providers: accounts made with them cannot recover a password and are mostly bots.
DISPOSABLE_DOMAINS = {"mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
                      "10minutemail.net", "tempmail.com", "temp-mail.org", "tempmail.net", "yopmail.com", "trashmail.com",
                      "getnada.com", "dispostable.com", "maildrop.cc", "throwawaymail.com", "fakeinbox.com", "mailnesia.com",
                      "mohmal.com", "emailondeck.com", "mintemail.com", "spamgourmet.com", "tmpmail.org", "mytemp.email"}
REGISTER_MIN_SECONDS = 3     # a human needs more than this to fill in the form


def canonical_email(email):
    """One mailbox = one key. Drops "+tag" and, for Gmail, the dots: a.b+1@gmail.com and ab@gmail.com are the same inbox."""
    local, _, domain = (email or "").strip().lower().partition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def is_disposable(email):
    return email.rsplit("@", 1)[-1] in DISPOSABLE_DOMAINS


def validate_password(password, email="", name=""):
    """Return an Uzbek error message, or None when the password is acceptable."""
    if len(password) < PASSWORD_MIN:
        return f"Parol kamida {PASSWORD_MIN} ta belgidan iborat boʻlsin."
    if len(password) > PASSWORD_MAX:
        return f"Parol {PASSWORD_MAX} ta belgidan oshmasin."
    low = password.lower()
    if low in _COMMON or len(set(low)) < 4 or low.isdigit():
        return "Bu parol juda oddiy. Harf va raqamlarni aralashtirib, oʻzingizga xos parol oʻylab toping."
    local = (email or "").split("@")[0].lower()
    if (len(local) >= 4 and local in low) or (name and len(name.strip()) >= 4 and name.strip().lower() == low):
        return "Parolda email yoki ismingiz boʻlmasin."
    return None


def safe_next(target, default):
    """Only same-site absolute paths. Rejects '//host', '/\\host', control characters and full URLs."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return default
    if re.search(r"[\\\x00-\x20\x7f]", target):
        return default
    return target


# ------------------------------------------------------------------ rate limits (database backed)
def _purge():
    db.session.query(AuthAttempt).filter(AuthAttempt.created_at < now() - timedelta(days=1)).delete(
        synchronize_session=False)


def record(kind, email=None):
    """Remember one attempt of `kind` from the current IP."""
    _purge()
    db.session.add(AuthAttempt(kind=kind, ip=client_ip(), email=(email or "")[:120] or None))
    db.session.commit()


def _count(kind, window, **filters):
    q = AuthAttempt.query.filter(AuthAttempt.kind == kind, AuthAttempt.created_at >= now() - timedelta(seconds=window))
    return q.filter_by(**filters).count()


def login_blocked(email):
    ip = client_ip()
    return (_count("login_fail", LOGIN_WINDOW, ip=ip, email=email) >= LOGIN_PAIR_MAX
            or _count("login_fail", LOGIN_WINDOW, ip=ip) >= LOGIN_IP_MAX
            or _count("login_fail", LOGIN_WINDOW, email=email) >= LOGIN_EMAIL_MAX)


def clear_login_failures(email):
    AuthAttempt.query.filter(AuthAttempt.kind == "login_fail", AuthAttempt.email == email).delete(
        synchronize_session=False)
    db.session.commit()


def limited(kind, window, ip_max, email=None, email_max=None):
    """True when this IP (or this email) made too many `kind` requests inside `window` seconds."""
    if _count(kind, window, ip=client_ip()) >= ip_max:
        return True
    return bool(email and email_max and _count(kind, window, email=email) >= email_max)


# ------------------------------------------------------------------ AI cost cap
def ai_budget_ok(user_id, kind, cap, window_hours=24):
    """Log one paid AI call BEFORE it is made and say whether the user is still under the hard cap.
    The row stays even when the cap is hit, so hammering the endpoint never resets the count."""
    db.session.add(UsageLog(user_id=user_id, kind=kind))
    db.session.commit()
    since = now() - timedelta(hours=window_hours)
    used = UsageLog.query.filter(UsageLog.user_id == user_id, UsageLog.kind == kind,
                                 UsageLog.created_at >= since).count()
    if used > cap:
        return False
    global_cap = current_app.config.get("AI_GLOBAL_DAILY_CAP", 0)       # one ceiling for everybody together
    if global_cap and UsageLog.query.filter(UsageLog.created_at >= since).count() > global_cap:
        logging.getLogger(__name__).warning("AI_GLOBAL_DAILY_CAP (%s) reached: AI calls are paused for 24 h windows", global_cap)
        return False
    return True


def ai_usage_today(user_id, kind, window_hours=24):
    """Number of times this user invoked `kind` within the last 24 hours."""
    since = now() - timedelta(hours=window_hours)
    return UsageLog.query.filter(UsageLog.user_id == user_id, UsageLog.kind == kind,
                                 UsageLog.created_at >= since).count()


def ai_remaining(user_id, kind, cap, window_hours=24):
    """How many attempts are left today for this user (at least 0)."""
    used = ai_usage_today(user_id, kind, window_hours=window_hours)
    return max(0, cap - used)


def naive(dt):
    """Naive-UTC version of a datetime (SQLite returns naive, PostgreSQL may return aware)."""
    from datetime import timezone as _tz
    if dt is None:
        return None
    return dt.astimezone(_tz.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt
