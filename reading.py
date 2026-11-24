"""Reading test flow: list -> start -> take -> submit -> result."""
import re
from datetime import datetime, timedelta, timezone
import gamify
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from extensions import db
from models import Test, Attempt, HintLog
from cefr import raw_to_scaled, scaled_to_level
from grading import grade

bp = Blueprint("reading", __name__)
_ANSWER_KEY = re.compile(r"^q\d{1,3}$")        # only real answer fields are kept (no junk keys stored in the JSON column)
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
GRACE = timedelta(seconds=120)   # tolerance for slow networks when the timer hits 0


def _now():
    return datetime.now(timezone.utc)


def _utc(dt):
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _deadline(attempt):
    return _utc(attempt.started_at) + timedelta(minutes=attempt.test.duration_min)


def _own_attempt(attempt_id):
    attempt = db.session.get(Attempt, attempt_id)
    if attempt is None or attempt.user_id != current_user.id:
        abort(404)
    return attempt


def _build_parts(test):
    """Format everything on the backend so the template only has to print it."""
    parts = []
    for p in test.parts:
        has_headings = any(g.qtype == "heading" for g in p.groups)
        paras = [t.strip() for t in (p.passage or "").split("\n\n") if t.strip()]
        numbers = [q.number for g in p.groups for q in g.questions]
        parts.append({
            "number": p.number, "title": p.title, "groups": p.groups, "audio_url": p.audio_url or "", "image_url": p.image_url or "",
            "paragraphs": [(ROMAN[i] if has_headings else "", t) for i, t in enumerate(paras)],
            "first": min(numbers, default=0), "last": max(numbers, default=0), "total": len(numbers),
            "numbers": sorted(numbers),
        })
    return parts


@bp.route("/reading")
def tests():
    items = []
    for t in Test.query.filter_by(skill="reading", is_active=True).order_by(Test.id):
        count = sum(len(g.questions) for p in t.parts for g in p.groups)
        items.append((t, count))
    return render_template("reading_list.html", items=items)


@bp.route("/reading/<int:test_id>/start", methods=["POST"])
@login_required
def start(test_id):
    test = db.get_or_404(Test, test_id)
    if test.skill != "reading" or not (test.is_active or current_user.is_admin):
        abort(404)
    open_attempt = (Attempt.query.filter_by(user_id=current_user.id, test_id=test.id, finished_at=None)
                    .order_by(Attempt.started_at.desc()).first())
    if open_attempt and _now() < _deadline(open_attempt):      # resume instead of restarting the clock
        return redirect(url_for("reading.take", attempt_id=open_attempt.id))
    attempt = Attempt(user_id=current_user.id, test_id=test.id)
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for("reading.take", attempt_id=attempt.id))


@bp.route("/attempt/<int:attempt_id>")
@login_required
def take(attempt_id):
    attempt = _own_attempt(attempt_id)
    if attempt.finished_at:
        return redirect(url_for("reading.result", attempt_id=attempt.id))
    remaining = int((_deadline(attempt) - _now()).total_seconds())   # server is the clock authority
    parts = _build_parts(attempt.test)
    used = dict(db.session.query(HintLog.part_number, func.count(HintLog.id))
                .filter(HintLog.attempt_id == attempt.id).group_by(HintLog.part_number).all())
    limit = current_app.config["HINTS_PER_PART"]
    for p in parts:
        p["hints_left"] = max(0, limit - used.get(p["number"], 0))
    return render_template("reading_test.html", test=attempt.test, attempt=attempt,
                           parts=parts, remaining=max(remaining, 0),
                           is_listening=attempt.test.skill == "listening",
                           plays=current_app.config["LISTENING_PLAYS"])


@bp.route("/attempt/<int:attempt_id>/submit", methods=["POST"])
@login_required
def submit(attempt_id):
    attempt = _own_attempt(attempt_id)
    if attempt.finished_at:
        return redirect(url_for("reading.result", attempt_id=attempt.id))
    now = _now()
    answers = {k: v.strip()[:200] for k, v in request.form.items() if _ANSWER_KEY.match(k)}
    if now > _deadline(attempt) + GRACE:
        answers = {}
        flash("Vaqt tugagandan keyin yuborilgan javoblar hisobga olinmadi.", "error")
    result = grade(attempt.test, answers)
    scaled = raw_to_scaled(result["raw"], result["max"])
    attempt.answers = answers
    attempt.finished_at = now
    attempt.raw_score, attempt.max_score = result["raw"], result["max"]
    attempt.scaled_score = scaled
    attempt.cefr_level = scaled_to_level(scaled)
    db.session.commit()
    gamify.after_test(attempt.user_id, attempt)                   # XP + badges; never raises
    return redirect(url_for("reading.result", attempt_id=attempt.id))


@bp.route("/attempt/<int:attempt_id>/result")
@login_required
def result(attempt_id):
    attempt = _own_attempt(attempt_id)
    if not attempt.finished_at:
        return redirect(url_for("reading.take", attempt_id=attempt.id))
    return render_template("reading_result.html", attempt=attempt,
                           g=grade(attempt.test, attempt.answers or {}))
