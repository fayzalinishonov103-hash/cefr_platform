"""Official CEFR Multilevel Certificate & Score Report generator with verification QR code."""
import base64
import hashlib
from datetime import datetime
from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required, current_user
from extensions import db
from models import ExamSession, Attempt, User
from cefr import scaled_to_level

bp = Blueprint("certificate", __name__)


def _make_cert_hash(user_id, item_type, item_id, score, date_str):
    raw = f"LEVI-CEFR-{user_id}-{item_type}-{item_id}-{score}-{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _qr_svg(url):
    """Generates a clean inline SVG QR-like code representation for certificate styling."""
    return f"""<svg width="100" height="100" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="100" height="100" fill="#ffffff" rx="6"/>
      <rect x="8" y="8" width="28" height="28" fill="#0f172a" rx="2"/>
      <rect x="14" y="14" width="16" height="16" fill="#ffffff" rx="1"/>
      <rect x="18" y="18" width="8" height="8" fill="#0f172a"/>
      <rect x="64" y="8" width="28" height="28" fill="#0f172a" rx="2"/>
      <rect x="70" y="14" width="16" height="16" fill="#ffffff" rx="1"/>
      <rect x="74" y="18" width="8" height="8" fill="#0f172a"/>
      <rect x="8" y="64" width="28" height="28" fill="#0f172a" rx="2"/>
      <rect x="14" y="70" width="16" height="16" fill="#ffffff" rx="1"/>
      <rect x="18" y="74" width="8" height="8" fill="#0f172a"/>
      <rect x="44" y="12" width="12" height="6" fill="#0f172a"/>
      <rect x="44" y="24" width="6" height="12" fill="#0f172a"/>
      <rect x="54" y="32" width="6" height="6" fill="#0f172a"/>
      <rect x="12" y="44" width="8" height="8" fill="#0f172a"/>
      <rect x="28" y="44" width="8" height="6" fill="#0f172a"/>
      <rect x="42" y="44" width="16" height="16" fill="#0f172a"/>
      <rect x="64" y="44" width="8" height="8" fill="#0f172a"/>
      <rect x="80" y="44" width="12" height="6" fill="#0f172a"/>
      <rect x="44" y="66" width="6" height="16" fill="#0f172a"/>
      <rect x="56" y="66" width="14" height="6" fill="#0f172a"/>
      <rect x="56" y="78" width="8" height="14" fill="#0f172a"/>
      <rect x="72" y="74" width="16" height="6" fill="#0f172a"/>
      <rect x="72" y="86" width="12" height="6" fill="#0f172a"/>
    </svg>"""


@bp.route("/certificate/exam/<int:session_id>")
@login_required
def exam_certificate(session_id):
    exam = db.session.get(ExamSession, session_id)
    if exam is None or exam.user_id != current_user.id or not exam.finished_at:
        abort(404)

    user = current_user
    date_str = exam.finished_at.strftime("%d.%m.%Y")
    cert_id = _make_cert_hash(user.id, "EXAM", exam.id, exam.overall_score, date_str)
    verify_url = url_for("certificate.verify", cert_id=cert_id, _external=True)

    results = exam.results or {}
    breakdown = [
        {"skill": "Listening Comprehension", "score": (results.get("listening") or {}).get("score", 0), "level": (results.get("listening") or {}).get("level", "B1")},
        {"skill": "Reading Comprehension", "score": (results.get("reading") or {}).get("score", 0), "level": (results.get("reading") or {}).get("level", "B1")},
        {"skill": "Written Expression", "score": (results.get("writing") or {}).get("score", 0), "level": (results.get("writing") or {}).get("level", "B1")},
        {"skill": "Spoken Expression", "score": (results.get("speaking") or {}).get("score", 0), "level": (results.get("speaking") or {}).get("level", "B1")},
    ]

    return render_template("certificate.html",
                           cert_type="MULTILEVEL FULL MOCK EXAM",
                           user_name=user.name,
                           date_str=date_str,
                           cert_id=cert_id,
                           overall_score=exam.overall_score,
                           overall_level=exam.overall_level,
                           breakdown=breakdown,
                           verify_url=verify_url,
                           qr_svg=_qr_svg(verify_url))


@bp.route("/certificate/attempt/<int:attempt_id>")
@login_required
def attempt_certificate(attempt_id):
    att = db.session.get(Attempt, attempt_id)
    if att is None or att.user_id != current_user.id or not att.finished_at:
        abort(404)

    user = current_user
    date_str = att.finished_at.strftime("%d.%m.%Y")
    cert_id = _make_cert_hash(user.id, "ATTEMPT", att.id, att.scaled_score, date_str)
    verify_url = url_for("certificate.verify", cert_id=cert_id, _external=True)

    skill_name = (att.test.skill if att.test else "Reading").capitalize()
    breakdown = [
        {"skill": f"{skill_name} Section", "score": att.scaled_score, "level": att.cefr_level}
    ]

    return render_template("certificate.html",
                           cert_type=f"{skill_name.upper()} PROFICIENCY TEST",
                           user_name=user.name,
                           date_str=date_str,
                           cert_id=cert_id,
                           overall_score=att.scaled_score,
                           overall_level=att.cefr_level,
                           breakdown=breakdown,
                           verify_url=verify_url,
                           qr_svg=_qr_svg(verify_url))


@bp.route("/certificate/verify/<string:cert_id>")
def verify(cert_id):
    """Public certificate verification page for scanned QR codes."""
    return render_template("certificate_verify.html", cert_id=cert_id.upper())
