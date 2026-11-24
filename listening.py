"""Listening tests: list and start. Taking, submitting and grading reuse the Reading flow (reading.py),
because an Attempt works the same way for both skills; only the page differs (audio player instead of a passage)."""
from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required, current_user

from extensions import db
from models import Test, Attempt
from reading import _now, _deadline

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
