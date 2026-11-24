"""Listening tests and Smart Audio Dictation trainer (connected speech)."""
import difflib
import re
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, abort, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import Test, Attempt
from reading import _now, _deadline
import gamify
from dictation_data import get_all_phrases, get_phrase_by_id

bp = Blueprint("listening", __name__)


@bp.route("/listening")
def tests():
    items = []
    for t in Test.query.filter_by(skill="listening", is_active=True).order_by(Test.id):
        count = sum(len(g.questions) for p in t.parts for g in p.groups)
        items.append((t, count))
    return render_template("listening_list.html", items=items)


@bp.route("/listening/<int:test_id>/start", methods=["POST"])
@login_required
def start(test_id):
    test = db.get_or_404(Test, test_id)
    if test.skill != "listening" or not (test.is_active or current_user.is_admin):
        abort(404)
    open_attempt = (Attempt.query.filter_by(user_id=current_user.id, test_id=test.id, finished_at=None)
                    .order_by(Attempt.started_at.desc()).first())
    if open_attempt and _now() < _deadline(open_attempt):      # resume instead of restarting the clock
        return redirect(url_for("reading.take", attempt_id=open_attempt.id))
    attempt = Attempt(user_id=current_user.id, test_id=test.id)
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for("reading.take", attempt_id=attempt.id))


# ------------------------------------------------------------------
# SMART AUDIO DICTATION TRAINER (CONNECTED SPEECH)
# ------------------------------------------------------------------

def _clean_tokens(text):
    return re.findall(r"[A-Za-z0-9']+", text.lower())


def _diff_dictation(target_text, user_text):
    t_tokens = _clean_tokens(target_text)
    u_tokens = _clean_tokens(user_text)

    matcher = difflib.SequenceMatcher(None, t_tokens, u_tokens)
    target_marked = []
    user_marked = []

    matches = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for w in t_tokens[i1:i2]:
                target_marked.append({"word": w, "status": "ok"})
                matches += 1
            for w in u_tokens[j1:j2]:
                user_marked.append({"word": w, "status": "ok"})
        elif tag == "replace":
            for w in t_tokens[i1:i2]:
                target_marked.append({"word": w, "status": "missed"})
            for w in u_tokens[j1:j2]:
                user_marked.append({"word": w, "status": "wrong"})
        elif tag == "delete":
            for w in t_tokens[i1:i2]:
                target_marked.append({"word": w, "status": "missed"})
        elif tag == "insert":
            for w in u_tokens[j1:j2]:
                user_marked.append({"word": w, "status": "extra"})

    accuracy = round((matches / max(len(t_tokens), 1)) * 100)
    return {
        "accuracy": accuracy,
        "is_passed": accuracy >= 80,
        "target_tokens": target_marked,
        "user_tokens": user_marked,
        "match_count": matches,
        "total_count": len(t_tokens)
    }


@bp.route("/listening/dictation")
def dictation():
    """Interactive Dictation page for connected speech."""
    phrases = get_all_phrases()
    level_filter = request.args.get("level", "all").upper()
    if level_filter in ("A2", "B1", "B2", "C1"):
        filtered = [p for p in phrases if p["level"] == level_filter]
    else:
        filtered = phrases

    return render_template("listening_dictation.html",
                           phrases=filtered,
                           active_level=level_filter,
                           total_phrases=len(phrases))


@bp.route("/listening/dictation/check", methods=["POST"])
def dictation_check():
    """Checks submitted dictation attempt, computes word diff, awards XP."""
    data = request.get_json(silent=True) or request.form
    try:
        phrase_id = int(data.get("phrase_id", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Noto'g'ri so'rov"}), 400

    phrase = get_phrase_by_id(phrase_id)
    if not phrase:
        return jsonify({"error": "Mashq topilmadi"}), 404

    user_text = (data.get("user_text") or "").strip()
    result = _diff_dictation(phrase["text"], user_text)

    xp_awarded = 0
    if current_user.is_authenticated and result["is_passed"]:
        day_tag = datetime.now().strftime("%Y%m%d")
        ref_id = f"dict_{phrase_id}_{day_tag}"
        if gamify.award(current_user.id, 10, "dictation", ref_id):
            xp_awarded = 10

    return jsonify({
        "ok": True,
        "accuracy": result["accuracy"],
        "is_passed": result["is_passed"],
        "target_tokens": result["target_tokens"],
        "user_tokens": result["user_tokens"],
        "match_count": result["match_count"],
        "total_count": result["total_count"],
        "target_text": phrase["text"],
        "phonetic": phrase["phonetic"],
        "feature": phrase["feature"],
        "explanation_uz": phrase["explanation_uz"],
        "xp_awarded": xp_awarded
    })
