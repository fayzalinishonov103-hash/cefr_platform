"""Registration, login and logout."""
import hashlib
import hmac
import logging
import secrets
import smtplib
import time
from email.message import EmailMessage

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from extensions import db
from models import User
import onboarding
import security
import verify

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)
RESET_MAX_AGE = 3600            # reset links live for 1 hour
TELEGRAM_MAX_AGE = 600          # Telegram login data older than 10 minutes is rejected
LOGIN_MAX_FAILS = security.LOGIN_PAIR_MAX
TELEGRAM_DOMAIN = "@telegram.local"


@bp.app_context_processor
def _telegram_context():
    return {"telegram_bot": current_app.config.get("TELEGRAM_BOT_USERNAME") if current_app.config.get("TELEGRAM_BOT_TOKEN") else ""}


def _safe_next(target):
    """Only relative redirects (prevents open-redirect attacks)."""
    return security.safe_next(target, url_for("main.dashboard"))


def _start_session(user, remember=True):
    """Fresh session for a freshly authenticated user (drops anything the visitor had before).
    remember=False: the sign-in ends when the browser closes (shared computers)."""
    session.clear()
    login_user(user, remember=remember)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        if security.limited("register", 3600, ip_max=10):
            flash("Juda koʻp urinish. Bir ozdan keyin qayta urinib koʻring.", "error")
            return render_template("register.html", **onboarding.signup_ctx(None)), 429
        security.record("register")
        if request.form.get("website"):                       # honeypot: invisible to people, bots fill every field
            log.info("Registration bot caught by honeypot (ip=%s)", security.client_ip())
            flash("Soʻrov qabul qilinmadi. Sahifani yangilab, qayta urinib koʻring.", "error")
            return render_template("register.html", **onboarding.signup_ctx(None)), 400
        if not current_app.testing and time.time() - session.get("reg_t", 0) < security.REGISTER_MIN_SECONDS:
            flash("Forma juda tez yuborildi. Bir necha soniya kutib, qayta urinib koʻring.", "error")
            return render_template("register.html", **onboarding.signup_ctx(request.form)), 400
        name = " ".join(request.form.get("name", "").split())
        email = security.clean_email(request.form.get("email"))
        password = request.form.get("password", "")
        extra, extra_error = onboarding.parse_signup(request.form)
        error = extra_error
        if error:
            pass
        elif not name or len(name) > 80:
            error = "Ism 1 dan 80 gacha belgidan iborat boʻlsin."
        elif not security.valid_email(email) or email.endswith(TELEGRAM_DOMAIN):
            error = "Email manzili notoʻgʻri."
        elif security.is_disposable(email):
            error = "Vaqtinchalik email manzillar qabul qilinmaydi. Oʻzingizning doimiy emailingizni kiriting."
        else:
            error = security.validate_password(password, email, name)
        canon = security.canonical_email(email)
        if not error and User.query.filter((User.email == email) | (User.email_canon == canon)).first():
            error = "Bu email bilan hisob allaqachon bor. Kirishni sinab koʻring."
        if error:
            flash(error, "error")
            return render_template("register.html", name=name, email=email, **onboarding.signup_ctx(request.form)), 400
        user = User(name=name, email=email, email_canon=canon)       # admin rights are never granted at registration
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        onboarding.save_signup(user, extra)
        sent = False
        if current_app.config.get("VERIFY_ENABLED"):          # a code + link to confirm the mailbox; never blocks sign-up
            try:
                sent = verify.send_verification(user)
            except Exception:
                log.exception("Verification e-mail failed for user %s", user.id)
        _start_session(user)
        flash("Hisob yaratildi. Xush kelibsiz!" + (" Emailingizga tasdiqlash kodi yuborildi." if sent else ""), "ok")
        return redirect(url_for("onboarding.edit", r=1))
    session["reg_t"] = int(time.time())                       # when the form was opened (see REGISTER_MIN_SECONDS)
    return render_template("register.html", **onboarding.signup_ctx(None))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = security.clean_email(request.form.get("email"))
        if security.login_blocked(email):
            flash("Juda koʻp xato urinish. 15 daqiqadan keyin qayta urinib koʻring.", "error")
            return render_template("login.html", email=email), 429
        password = request.form.get("password", "")[:1024]
        user = User.query.filter_by(email=email).first()
        if user:
            ok = user.check_password(password)
        else:
            check_password_hash(security.DUMMY_HASH, password)      # same work as a real check: no timing leak
            ok = False
        if ok:
            security.clear_login_failures(email)
            # the checkbox is "remember me"; a form without it (older clients, tests) keeps the old behaviour
            remember = request.form.get("remember") == "1" if request.form.get("remember_shown") else True
            _start_session(user, remember=remember)
            return redirect(_safe_next(request.args.get("next")))
        security.record("login_fail", email)
        flash("Email yoki parol notoʻgʻri.", "error")
        return render_template("login.html", email=email), 401
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # Order matters: clear the session FIRST, then logout_user(). logout_user() marks the "remember me" cookie for
    # deletion inside the session; clearing the session afterwards erased that mark, so the cookie survived and the
    # user was silently signed in again on the next request.
    session.clear()
    logout_user()
    return redirect(url_for("main.index"))


# ------------------------------------------------------------ password reset
def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def _fingerprint(user):
    """Changes when the password changes, so a reset link works only once."""
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def _send_reset_email(user, link):
    """Send through SMTP when configured; otherwise print the link to the server log (development)."""
    host = current_app.config.get("SMTP_HOST")
    if not host:
        if current_app.debug or current_app.testing:      # the link is a password: never write it to production logs
            log.warning("SMTP sozlanmagan. %s uchun tiklash havolasi: %s", user.email, link)
        else:
            log.error("SMTP sozlanmagan: parolni tiklash xati yuborilmadi (%s).", user.email)
        return
    msg = EmailMessage()
    msg["Subject"] = "Levi — parolni tiklash"
    msg["From"] = current_app.config["SMTP_FROM"]
    msg["To"] = user.email
    msg.set_content(f"Salom, {user.name}!\n\nParolni tiklash uchun havola (1 soat amal qiladi):\n{link}\n\n"
                    "Agar siz soʻramagan boʻlsangiz, bu xatni eʼtiborsiz qoldiring.")
    port = current_app.config["SMTP_PORT"]
    smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP       # 465 = SSL from the start, 587 = STARTTLS
    with smtp_class(host, port, timeout=15) as smtp:
        if port != 465:
            smtp.starttls()
        if current_app.config.get("SMTP_USER"):
            smtp.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
        smtp.send_message(msg)


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = security.clean_email(request.form.get("email"))
        throttled = security.limited("forgot", 3600, ip_max=5, email=email, email_max=3)
        security.record("forgot", email)            # counted even when throttled, so spamming never frees the limit
        user = User.query.filter_by(email=email).first() if not throttled else None
        if user and not user.email.endswith(TELEGRAM_DOMAIN):
            token = _serializer().dumps({"id": user.id, "fp": _fingerprint(user)})
            try:
                _send_reset_email(user, url_for("auth.reset", token=token, _external=True))
            except Exception:
                log.exception("Reset email failed")
        # same answer whether or not the email exists or the request was throttled (no enumeration)
        flash("Agar bu email roʻyxatdan oʻtgan boʻlsa, parolni tiklash havolasi yuborildi.", "ok")
        return redirect(url_for("auth.login"))
    return render_template("forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    try:
        data = _serializer().loads(token, max_age=RESET_MAX_AGE)
        user = db.session.get(User, data["id"])
        if user is None or not hmac.compare_digest(data["fp"], _fingerprint(user)):
            raise BadSignature("used")
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        flash("Havola eskirgan yoki allaqachon ishlatilgan. Yangisini soʻrang.", "error")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        password = request.form.get("password", "")
        problem = security.validate_password(password, user.email, user.name)
        if problem:
            flash(problem, "error")
            return render_template("reset.html"), 400
        if password != request.form.get("password2", ""):
            flash("Ikkala parol bir xil emas.", "error")
            return render_template("reset.html"), 400
        user.set_password(password)
        user.rotate_session()                       # every device that was signed in is signed out
        if not user.email_verified_at:
            user.email_verified_at = security.now()  # they just proved they own the mailbox
        db.session.commit()
        security.clear_login_failures(user.email)
        flash("Parol yangilandi. Endi kirishingiz mumkin.", "ok")
        return redirect(url_for("auth.login"))
    return render_template("reset.html")


# ------------------------------------------------------------ Telegram login
def verify_telegram(data: dict, bot_token: str, now=None) -> bool:
    """Check the signature of Telegram Login Widget data (https://core.telegram.org/widgets/login)."""
    given = data.get("hash", "")
    fields = {k: v for k, v in data.items() if k != "hash"}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not given or not hmac.compare_digest(expected, given):
        return False
    try:
        age = (now or time.time()) - int(fields.get("auth_date", "0"))
    except ValueError:
        return False
    return 0 <= age <= TELEGRAM_MAX_AGE


@bp.route("/auth/telegram")
def telegram():
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    data = request.args.to_dict()
    if not token or not verify_telegram(data, token):
        flash("Telegram orqali kirish muvaffaqiyatsiz boʻldi. Qayta urinib koʻring.", "error")
        return redirect(url_for("auth.login"))
    try:
        tg_id = int(data["id"])
    except (KeyError, ValueError):
        flash("Telegram orqali kirish muvaffaqiyatsiz boʻldi. Qayta urinib koʻring.", "error")
        return redirect(url_for("auth.login"))
    user = User.query.filter_by(telegram_id=tg_id).first()
    first_time = user is None
    if user is None:
        name = (data.get("first_name") or data.get("username") or "Talaba").strip()[:80]
        tg_email = f"tg{tg_id}{TELEGRAM_DOMAIN}"
        user = User(name=name, email=tg_email, email_canon=tg_email, telegram_id=tg_id,
                    email_verified_at=security.now())      # a Telegram account is tied to a real phone number
        user.set_password(secrets.token_urlsafe(32))       # random: this account signs in through Telegram
        db.session.add(user)
        db.session.commit()
    _start_session(user)
    return redirect(url_for("onboarding.edit" if first_time else "main.dashboard"))
