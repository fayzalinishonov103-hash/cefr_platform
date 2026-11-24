"""E-mail confirmation: a 6-digit code (or a one-tap link) sent after registration.

Design (easy to use, hard to abuse):
  * People can sign up and use Reading, Listening, the level test and the dictionary at once, without confirming.
  * The paid AI features (Writing, Speaking, AI hints) need a confirmed e-mail: fake or bot accounts cannot reach them.
  * Telegram sign-up counts as confirmed (a Telegram account is already tied to a real phone number).
  * The code is stateless: HMAC(secret, user, e-mail, 10-minute window), valid 10-20 minutes. Wrong guesses are rate limited.
"""
import hmac
import logging
import time

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature

import mailer
import security
from extensions import db
from models import User

bp = Blueprint("verify", __name__)
log = logging.getLogger(__name__)

WINDOW = 600                                   # seconds: a code lives 10-20 minutes
LINK_MAX_AGE = 24 * 3600
GATED = {"writing.task", "writing.submit", "speaking.task", "speaking.submit", "ai.hint"}   # the paid AI features
NEEDS_EMAIL = "Bu imkoniyat uchun avval emailingizni tasdiqlang. Tasdiqlash kodi emailingizga yuborilgan."


def _code(user, window):
    key = current_app.config["SECRET_KEY"].encode()
    mac = hmac.new(key, f"verify:{user.id}:{user.email}:{window}".encode(), "sha256").digest()
    return f"{int.from_bytes(mac[:4], 'big') % 1_000_000:06d}"


def code_ok(user, code):
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    window = int(time.time() // WINDOW)
    return len(code) == 6 and any(hmac.compare_digest(_code(user, w), code) for w in (window, window - 1))


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="email-verify")


def send_verification(user):
    """E-mail the code and a link. Returns True when it was handed to the mail server."""
    link = url_for("verify.link", token=_serializer().dumps({"u": user.id, "e": user.email}), _external=True)
    code = _code(user, int(time.time() // WINDOW))
    body = (f"Salom, {user.name}!\n\nLevi emailingizni tasdiqlash kodi: {code}\n(10-20 daqiqa amal qiladi)\n\n"
            f"Yoki shu havolani oching (24 soat amal qiladi):\n{link}\n\n"
            "Agar siz Levi'da hisob yaratmagan boʻlsangiz, bu xatni eʼtiborsiz qoldiring.")
    security.record("verify_send", email=f"u{user.id}")
    return mailer.send_mail(user.email, "Levi — emailingizni tasdiqlang", body)


def mark_verified(user):
    if not user.email_verified_at:
        user.email_verified_at = security.now()
        db.session.commit()


@bp.before_app_request
def gate():
    """Unconfirmed accounts are sent to the code page BEFORE they start writing (so no essay is ever lost)."""
    if request.endpoint not in GATED or not current_user.is_authenticated or current_user.is_verified:
        return None
    if request.endpoint == "ai.hint":
        return jsonify(error=NEEDS_EMAIL), 403
    flash(NEEDS_EMAIL, "error")
    return redirect(url_for("verify.page", next=request.path))


@bp.route("/tasdiqlash", methods=["GET", "POST"])
@login_required
def page():
    target = security.safe_next(request.args.get("next"), url_for("main.dashboard"))
    if current_user.is_verified:
        return redirect(target)
    key = f"u{current_user.id}"
    if request.method == "POST":
        if security.limited("verify_fail", 900, ip_max=30, email=key, email_max=5):
            flash("Juda koʻp notoʻgʻri urinish. 15 daqiqadan keyin qayta urinib koʻring.", "error")
            return render_template("verify.html"), 429
        if code_ok(current_user, request.form.get("code")):
            mark_verified(current_user)
            flash("Email tasdiqlandi. Endi barcha imkoniyatlardan foydalana olasiz.", "ok")
            return redirect(target)
        security.record("verify_fail", email=key)
        flash("Kod notoʻgʻri yoki muddati tugagan. Yangi kod soʻrang.", "error")
        return render_template("verify.html"), 400
    return render_template("verify.html")


@bp.route("/tasdiqlash/yuborish", methods=["POST"])
@login_required
def resend():
    if not current_user.is_verified:
        if security.limited("verify_send", 3600, ip_max=10, email=f"u{current_user.id}", email_max=3):
            flash("Kod bir soatda 3 martadan koʻp yuborilmaydi. Biroz kuting.", "error")
        else:
            try:
                sent = send_verification(current_user)
            except Exception:
                log.exception("Verification e-mail failed for user %s", current_user.id)
                sent = None
            if sent:
                flash("Kod yuborildi. Pochtangizni (va spam papkasini) tekshiring.", "ok")
            elif sent is None:
                flash("Xat yuborib boʻlmadi. Birozdan keyin qayta urinib koʻring.", "error")
            else:
                flash("Email xizmati sozlanmagan, kod yuborib boʻlmadi. Administratorga murojaat qiling.", "error")
    return redirect(url_for("verify.page", next=request.args.get("next") or None))


@bp.route("/tasdiqlash/havola/<token>")
def link(token):
    try:
        data = _serializer().loads(token, max_age=LINK_MAX_AGE)
        user = db.session.get(User, data["u"])
        if user is None or user.email != data["e"]:
            raise BadSignature("account changed")
    except (BadSignature, KeyError, TypeError):
        flash("Havola yaroqsiz yoki muddati tugagan. Yangi kod soʻrang.", "error")
        return redirect(url_for("verify.page") if current_user.is_authenticated else url_for("auth.login"))
    mark_verified(user)
    flash("Email tasdiqlandi.", "ok")
    return redirect(url_for("main.dashboard") if current_user.is_authenticated else url_for("auth.login"))
