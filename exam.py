"""Mock exam: a guided path through all four skills ending in one overall level.

How it works (no change to the normal test flows):
  * starting an exam only records the time;
  * a skill counts as done when the student finishes a test/task of that skill AFTER that moment
    (the latest one counts), so students pick any test they like;
  * when all four are done the exam is completed and a snapshot of the results is stored.
"""
from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, abort, flash, g
from flask_login import login_required, current_user

import security
from cefr import scaled_to_level
from extensions import db
from models import ExamSession, Attempt, Test, SkillResult

bp = Blueprint("exam", __name__)

STAGES = [("reading", "Reading", "reading.tests"), ("listening", "Listening", "listening.tests"),
          ("writing", "Writing", "writing.tasks"), ("speaking", "Speaking", "speaking.tasks")]
STARTS_PER_DAY = 5


def stage_results(user_id, since):
    """{skill: {score, level, title, url, when}} for results created at/after `since` (latest one per skill)."""
    out = {}
    rows = (db.session.query(Attempt, Test).join(Test, Test.id == Attempt.test_id)
            .filter(Attempt.user_id == user_id, Attempt.finished_at.isnot(None), Attempt.finished_at >= since,
                    Attempt.scaled_score.isnot(None), Test.skill.in_(("reading", "listening")))
            .order_by(Attempt.finished_at.asc()).all())
    for attempt, test in rows:
        out[test.skill] = {"score": attempt.scaled_score, "level": attempt.cefr_level, "title": test.title,
                           "url": url_for("reading.result", attempt_id=attempt.id)}
    for skill, endpoint in (("writing", "writing.result"), ("speaking", "speaking.result")):
        row = (SkillResult.query.filter(SkillResult.user_id == user_id, SkillResult.skill == skill,
                                        SkillResult.created_at >= since, SkillResult.scaled_score.isnot(None))
               .order_by(SkillResult.created_at.desc(), SkillResult.id.desc()).first())
        if row:
            out[skill] = {"score": row.scaled_score, "level": row.cefr_level,
                          "title": (row.feedback or {}).get("title", skill.capitalize()),
                          "url": url_for(endpoint, result_id=row.id)}
    return out


def overall(results):
    """(average score, CEFR label) once all four skills are present, otherwise (None, None)."""
    if not all(k in results for k, _, _ in STAGES):
        return None, None
    avg = round(sum(results[k]["score"] for k, _, _ in STAGES) / len(STAGES), 1)
    return avg, scaled_to_level(avg)


def open_session(user_id):
    return (ExamSession.query.filter_by(user_id=user_id, finished_at=None, cancelled=False)
            .order_by(ExamSession.id.desc()).first())


@bp.app_context_processor
def _inject():
    def open_exam():
        """The signed-in student's running exam (cached per request) - used by the banner in base.html."""
        if not current_user.is_authenticated:
            return None
        if "open_exam" not in g:
            g.open_exam = open_session(current_user.id)
        return g.open_exam
    return {"open_exam": open_exam}


@bp.route("/exam")
@login_required
def index():
    current = open_session(current_user.id)
    if current:
        return redirect(url_for("exam.detail", session_id=current.id))
    history = (ExamSession.query.filter(ExamSession.user_id == current_user.id, ExamSession.finished_at.isnot(None))
               .order_by(ExamSession.id.desc()).limit(10).all())
    return render_template("exam.html", exam=None, history=history, stages=STAGES)


@bp.route("/exam/start", methods=["POST"])
@login_required
def start():
    current = open_session(current_user.id)
    if current:
        return redirect(url_for("exam.detail", session_id=current.id))
    since = security.now() - timedelta(hours=24)
    if ExamSession.query.filter(ExamSession.user_id == current_user.id, ExamSession.started_at >= since).count() >= STARTS_PER_DAY:
        flash("Bugun juda koʻp imtihon boshladingiz. Ertaga davom ettiring.", "error")
        return redirect(url_for("exam.index"))
    exam = ExamSession(user_id=current_user.id, started_at=security.now())
    db.session.add(exam)
    db.session.commit()
    return redirect(url_for("exam.detail", session_id=exam.id))


@bp.route("/exam/<int:session_id>")
@login_required
def detail(session_id):
    exam = db.session.get(ExamSession, session_id)
    if exam is None or exam.user_id != current_user.id or exam.cancelled:
        abort(404)
    if exam.finished_at:
        results = exam.results or {}
    else:
        results = stage_results(current_user.id, exam.started_at)
        score, level = overall(results)
        if score is not None:                      # all four done: complete the exam and keep a snapshot
            exam.finished_at, exam.overall_score, exam.overall_level, exam.results = security.now(), score, level, results
            db.session.commit()
    done = sum(1 for k, _, _ in STAGES if k in results)
    return render_template("exam.html", exam=exam, results=results, stages=STAGES, done=done)


@bp.route("/exam/<int:session_id>/cancel", methods=["POST"])
@login_required
def cancel(session_id):
    exam = db.session.get(ExamSession, session_id)
    if exam is None or exam.user_id != current_user.id or exam.finished_at:
        abort(404)
    exam.cancelled = True
    db.session.commit()
    flash("Imtihon bekor qilindi. Natijalaringiz profilda saqlanib qoladi.", "ok")
    return redirect(url_for("exam.index"))
