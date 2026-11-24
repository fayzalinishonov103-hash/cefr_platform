"""Vocabulary notebook: save words in one click, review them with spaced repetition (Leitner boxes)."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import VocabWord

bp = Blueprint("vocab", __name__, url_prefix="/vocab")
INTERVAL_DAYS = [0, 1, 3, 7, 14]          # days until next review for box 0..4
MAX_WORDS_PER_USER = 2000


def _now():
    # naive UTC so comparisons work on both SQLite and PostgreSQL
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _own(word_id):
    w = db.session.get(VocabWord, word_id)
    if w is None or w.user_id != current_user.id:
        abort(404)
    return w


def _wants_json():
    return request.is_json or request.accept_mimetypes.best == "application/json"


def _save(word, meaning, context):
    word = " ".join((word or "").split())[:80]
    if not word:
        return None, "Soʻzni kiriting."
    exists = VocabWord.query.filter(VocabWord.user_id == current_user.id,
                                    func.lower(VocabWord.word) == word.lower()).first()
    if exists:
        return exists, "Bu soʻz daftaringizda allaqachon bor."
    if VocabWord.query.filter_by(user_id=current_user.id).count() >= MAX_WORDS_PER_USER:
        return None, "Daftar toʻldi. Avval ba’zi soʻzlarni oʻchiring."
    item = VocabWord(user_id=current_user.id, word=word, meaning=(meaning or "").strip()[:200],
                     context=(context or "").strip()[:300], next_review=_now())
    db.session.add(item)
    db.session.commit()
    return item, None


@bp.route("")
@login_required
def index():
    words = VocabWord.query.filter_by(user_id=current_user.id).order_by(VocabWord.created_at.desc()).all()
    due = sum(1 for w in words if w.next_review is None or w.next_review <= _now())
    return render_template("vocab.html", words=words, due=due)


@bp.route("/add", methods=["POST"])
@login_required
def add():
    data = request.get_json(silent=True) if request.is_json else request.form
    data = data or {}
    item, problem = _save(data.get("word"), data.get("meaning"), data.get("context"))
    if _wants_json():
        if item is None:
            return jsonify(error=problem), 400
        return jsonify(ok=True, note=problem or "Daftarga saqlandi.")
    flash(problem or "Soʻz daftarga qoʻshildi.", "error" if (problem and item is None) else "ok")
    return redirect(url_for("vocab.index"))


@bp.route("/<int:word_id>/delete", methods=["POST"])
@login_required
def delete(word_id):
    db.session.delete(_own(word_id))
    db.session.commit()
    return redirect(url_for("vocab.index"))


@bp.route("/review")
@login_required
def review():
    word = (VocabWord.query.filter(VocabWord.user_id == current_user.id, VocabWord.next_review <= _now())
            .order_by(VocabWord.next_review.asc()).first())
    left = VocabWord.query.filter(VocabWord.user_id == current_user.id, VocabWord.next_review <= _now()).count()
    return render_template("vocab_review.html", word=word, left=left)


@bp.route("/<int:word_id>/review", methods=["POST"])
@login_required
def grade(word_id):
    w = _own(word_id)
    known = request.form.get("result") == "known"
    w.box = min(w.box + 1, len(INTERVAL_DAYS) - 1) if known else 0
    w.next_review = _now() + timedelta(days=INTERVAL_DAYS[w.box] if known else 0, minutes=0 if known else 10)
    db.session.commit()
    return redirect(url_for("vocab.review"))
