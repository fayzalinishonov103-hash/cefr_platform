"""Application factory. Run with:  python app.py"""
import os
import secrets
from datetime import timedelta
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, request
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import db, login_manager, csrf

_STATIC_CSS = Path(__file__).resolve().parent / "static" / "css"
load_dotenv()   # reads OPENAI_API_KEY, SECRET_KEY, ... from the local ".env" file


def _ensure_columns():
    """Tiny migration: add columns introduced after the first release (SQLite / PostgreSQL)."""
    columns = {c["name"] for c in inspect(db.engine).get_columns("user")}
    if "is_admin" not in columns:
        default = "FALSE" if db.engine.dialect.name == "postgresql" else "0"
        db.session.execute(text(f'ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT {default}'))
        db.session.commit()
    if "telegram_id" not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN telegram_id BIGINT'))
        db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_user_telegram_id ON "user" (telegram_id)'))
        db.session.commit()
    if "email_verified_at" not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN email_verified_at TIMESTAMP'))
        db.session.execute(text('UPDATE "user" SET email_verified_at = CURRENT_TIMESTAMP'))   # accounts that existed before are trusted
        db.session.commit()
    if "email_canon" not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN email_canon VARCHAR(255)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_user_email_canon ON "user" (email_canon)'))
        db.session.commit()
    if "session_token" not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN session_token VARCHAR(32) NOT NULL DEFAULT \'\''))
        db.session.commit()
    from models import User
    import security
    for user in User.query.filter((User.session_token == "") | (User.session_token.is_(None))).all():
        user.rotate_session()                      # existing accounts get their own token
    for user in User.query.filter(User.email_canon.is_(None)).all():
        user.email_canon = security.canonical_email(user.email)
    db.session.commit()


def _ensure_part_image_column():
    """Add part.image_url to a database created before maps existed. Idempotent and safe when several workers start at once."""
    def has():
        return "image_url" in {c["name"] for c in inspect(db.engine).get_columns("part")}
    if has():
        return
    try:
        db.session.execute(text('ALTER TABLE "part" ADD COLUMN image_url VARCHAR(255)'))
        db.session.commit()
    except Exception:                                  # another worker added it first
        db.session.rollback()
        if not has():
            raise


def _csp():
    """Content-Security-Policy. Inline scripts/styles stay allowed (the templates use them); everything else is
    locked to this site plus the few third parties the pages really use."""
    return "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://telegram.org",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https://i.ytimg.com https://telegram.org",
        "media-src 'self' blob: https:",
        "connect-src 'self'",
        "frame-src https://oauth.telegram.org",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


def create_app(config=None):
    app = Flask(__name__)
    production = (os.environ.get("APP_ENV", "").lower() == "production" or bool(os.environ.get("DATABASE_URL"))
                  or bool(os.environ.get("RENDER") or os.environ.get("DYNO") or os.environ.get("RAILWAY_ENVIRONMENT")))
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        PRODUCTION=production,
        # --- cookies / sessions
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=production,
        REMEMBER_COOKIE_HTTPONLY=True, REMEMBER_COOKIE_SAMESITE="Lax", REMEMBER_COOKIE_SECURE=production,
        REMEMBER_COOKIE_DURATION=timedelta(days=14), PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        # the CSRF token is tied to the session; a 1-hour expiry would break submitting a long (up to 240 min) test
        WTF_CSRF_TIME_LIMIT=None,
        HINTS_PER_DAY=60,
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///cefr.db").replace("postgres://", "postgresql://", 1),
        HINTS_PER_PART=3,
        WRITING_PER_DAY=10,
        C1_TRANSFORM_PER_DAY=int(os.environ.get("C1_TRANSFORM_PER_DAY", "2")),
        SPEAKING_PER_DAY=int(os.environ.get("SPEAKING_PER_DAY", "10")),
        LISTENING_PLAYS=int(os.environ.get("LISTENING_PLAYS", "2")),   # how many times a student may play each part
        MAX_CONTENT_LENGTH=30 * 1024 * 1024,                           # audio uploads in the admin panel
        SMTP_HOST=os.environ.get("SMTP_HOST", ""), SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER", ""), SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_FROM=os.environ.get("SMTP_FROM", "Levi <no-reply@example.com>"),
        PRIVACY_CONTACT=os.environ.get("PRIVACY_CONTACT", ""),
        # hard daily ceiling for ALL paid AI calls together (0 = off). Protects the OpenAI bill from bots and spikes.
        # e-mail confirmation (6-digit code) is needed for Writing/Speaking/AI hints. On by default when SMTP is configured;
        # VERIFY_EMAIL=1 / 0 forces it on / off.
        VERIFY_ENABLED={"1": True, "0": False}.get(os.environ.get("VERIFY_EMAIL", ""), bool(os.environ.get("SMTP_HOST"))),
        AI_GLOBAL_DAILY_CAP=int(os.environ.get("AI_GLOBAL_DAILY_CAP", "0")),
        # built with tools/build_css.py and tools/fetch_fonts.py; when the files exist the site stops using the CDNs
        TAILWIND_LOCAL=_STATIC_CSS.joinpath("tailwind.css").exists(), FONTS_LOCAL=_STATIC_CSS.joinpath("fonts.css").exists(),
        TAILWIND_VERSION=int(_STATIC_CSS.joinpath("tailwind.css").stat().st_mtime) if _STATIC_CSS.joinpath("tailwind.css").exists() else 0,
        TELEGRAM_BOT_TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        TELEGRAM_BOT_USERNAME=os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@"),
    )
    if config:
        app.config.update(config)

    if app.config["PRODUCTION"] and not app.config["VERIFY_ENABLED"] and not app.config.get("TESTING"):
        app.logger.warning("Email tasdiqlash OʻCHIQ (SMTP_HOST berilmagan): har kim sohta emailda hisob ochib, AI dan foydalana oladi.")

    key = app.config["SECRET_KEY"]
    if not key or key == "dev-only-change-me" or len(key) < 32:
        if app.config["PRODUCTION"] and not app.config.get("TESTING"):
            raise RuntimeError("SECRET_KEY yoʻq yoki juda qisqa. Uzun tasodifiy qiymat bering: "
                               "python -c \"import secrets; print(secrets.token_hex(32))\"")
        app.config["SECRET_KEY"] = key if len(key) >= 32 else secrets.token_hex(32)   # dev: random per start

    hops = int(os.environ.get("PROXY_HOPS", "1" if production else "0"))
    if hops:                                    # real client IP from X-Forwarded-For (needed for rate limits)
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bu sahifa uchun avval tizimga kiring."
    csrf.init_app(app)

    import models  # noqa: F401  (registers tables)
    from main import bp as main_bp
    from auth import bp as auth_bp
    from reading import bp as reading_bp
    from ai_hint import bp as ai_bp
    from admin import bp as admin_bp
    from writing import bp as writing_bp
    from skills import bp as skills_bp
    from vocab import bp as vocab_bp
    from listening import bp as listening_bp
    from speaking import bp as speaking_bp
    from account import bp as account_bp
    from shadowing import bp as shadowing_bp, admin_bp as shadow_admin_bp
    from placement import bp as placement_bp
    from exam import bp as exam_bp
    from admin_ai import bp as admin_ai_bp
    from smart import bp as smart_bp
    from mistakes import bp as mistakes_bp
    from onboarding import bp as onboarding_bp
    from verify import bp as verify_bp
    from battle import bp as battle_bp
    from certificate import bp as certificate_bp
    for bp in (main_bp, auth_bp, reading_bp, ai_bp, admin_bp, writing_bp, skills_bp, vocab_bp, listening_bp, speaking_bp, account_bp,
               shadowing_bp, shadow_admin_bp, placement_bp, exam_bp, admin_ai_bp, mistakes_bp, smart_bp, onboarding_bp, verify_bp, battle_bp, certificate_bp):
        app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        _ensure_columns()
        _ensure_part_image_column()

    @app.route("/health")
    def health():
        """For uptime monitors / load balancers: 200 when the app and the database answer."""
        try:
            db.session.execute(text("SELECT 1"))
            return {"ok": True}
        except Exception:
            return {"ok": False}, 503

    csp_header = ("Content-Security-Policy-Report-Only" if os.environ.get("CSP_MODE") == "report-only"
                  else "Content-Security-Policy")

    @app.after_request
    def _security_headers(resp):
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=(), microphone=(self)")
        h.setdefault(csp_header, _csp() + ("; upgrade-insecure-requests" if app.config["PRODUCTION"] else ""))
        if app.config["PRODUCTION"]:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint != "static" and resp.mimetype == "text/html":
            h["Cache-Control"] = "no-store"     # signed-in pages must not be shown again from the cache after logout
        return resp

    def _error_page(code, title, text_):
        from flask import render_template, request
        if request.path.startswith(("/admin/audio",)) or request.is_json:
            return {"error": text_}, code
        return render_template("error.html", code=code, title=title, message=text_), code

    @app.errorhandler(403)
    def _403(e): return _error_page(403, "Ruxsat yoʻq", "Bu sahifaga kirish huquqingiz yoʻq.")

    @app.errorhandler(404)
    def _404(e): return _error_page(404, "Sahifa topilmadi", "Bunday sahifa mavjud emas yoki oʻchirilgan.")

    @app.errorhandler(413)
    def _413(e): return _error_page(413, "Fayl juda katta", "Yuborilgan fayl ruxsat etilgan hajmdan katta.")

    @app.errorhandler(500)
    def _500(e):
        db.session.rollback()
        return _error_page(500, "Xatolik yuz berdi", "Kutilmagan xato. Qayta urinib koʻring, davom etsa administratorga xabar bering.")

    @app.cli.command("make-admin")
    @click.argument("email")
    def make_admin(email):
        """Give an existing user admin rights:  flask --app app make-admin EMAIL"""
        user = models.User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            click.echo("Bunday foydalanuvchi topilmadi. Avval roʻyxatdan oʻting.")
            raise SystemExit(1)
        user.is_admin = True
        db.session.commit()
        click.echo(f"{user.email} endi admin.")

    @app.cli.command("revoke-admin")
    @click.argument("email")
    def revoke_admin(email):
        """Take admin rights away:  flask --app app revoke-admin EMAIL"""
        user = models.User.query.filter_by(email=email.strip().lower()).first()
        if not user or not user.is_admin:
            click.echo("Bunday admin topilmadi.")
            raise SystemExit(1)
        user.is_admin = False
        user.rotate_session()
        db.session.commit()
        click.echo(f"{user.email} endi admin emas.")

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
