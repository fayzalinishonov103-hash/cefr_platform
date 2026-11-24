"""Mistakes notebook: every Reading/Listening question the student got wrong, with a quick re-practice mode.

Nothing is copied: the list is rebuilt from the student's finished attempts (newest first) and the CURRENT answer key.
  * a question is a "mistake" when the NEWEST attempt that contained it was wrong or left empty;
  * answering it correctly in practice removes it from the list (MistakeFixed);
  * getting it wrong again in a later real attempt puts it back.
The answer key stays on the server; it is only shown after a practice submit.
"""
import random
import re
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user

from extensions import db
from grading import is_correct, _show
from models import Attempt, Test, Part, QuestionGroup, Question, MistakeFixed

bp = Blueprint("mistakes", __name__)
MAX_ATTEMPTS = 30           # newest finished attempts that are looked at
PRACTICE_SIZE = 10
LIST_LIMIT = 60
SKILLS = ("reading", "listening")


def _naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def collect(user_id, skill=None):
    """-> list of mistake dicts, newest first. 3 queries however many attempts there are."""
    attempts = (Attempt.query.join(Test, Test.id == Attempt.test_id)
                .filter(Attempt.user_id == user_id, Attempt.finished_at.isnot(None), Test.skill.in_(SKILLS))
                .order_by(Attempt.finished_at.desc(), Attempt.id.desc()).limit(MAX_ATTEMPTS).all())
    if not attempts:
        return []
    test_ids = {a.test_id for a in attempts}
    titles = {t.id: (t.title, t.skill) for t in Test.query.filter(Test.id.in_(test_ids))}
    structure = {}
    rows = (db.session.query(Question, QuestionGroup, Part)
            .join(QuestionGroup, QuestionGroup.id == Question.group_id)
            .join(Part, Part.id == QuestionGroup.part_id)
            .filter(Part.test_id.in_(test_ids)).order_by(Part.number, Question.number).all())
    for q, g, p in rows:
        structure.setdefault(p.test_id, []).append((q, g, p))
    fixed_at = {qid: _naive(at) for qid, at in
                db.session.query(MistakeFixed.question_id, MistakeFixed.created_at).filter_by(user_id=user_id)}

    seen, out = set(), []
    for attempt in attempts:                         # newest first: the first sighting of a question decides
        title, test_skill = titles.get(attempt.test_id, ("?", "reading"))
        if skill and test_skill != skill:
            continue
        answers = attempt.answers or {}
        when = _naive(attempt.finished_at)
        for q, g, p in structure.get(attempt.test_id, []):
            if q.id in seen:
                continue
            seen.add(q.id)
            given = answers.get(f"q{q.number}", "")
            if is_correct(given, q.answer):
                continue
            if q.id in fixed_at and when and when <= fixed_at[q.id]:
                continue                              # fixed after that attempt
            out.append({"qid": q.id, "skill": test_skill, "test": title, "part": p.number, "number": q.number,
                        "text": q.text or "", "level": q.cefr_level or "", "given": _show(q, given) if given else "",
                        "attempt_id": attempt.id, "when": when})
    return out


def _paras(passage):
    return [" ".join(x.split()) for x in re.split(r"\n\s*\n", passage or "") if x.strip()]


@bp.route("/mistakes")
@login_required
def index():
    skill = request.args.get("skill")
    skill = skill if skill in SKILLS else None
    items = collect(current_user.id, skill)
    levels = {}
    for m in items:
        levels[m["level"] or "?"] = levels.get(m["level"] or "?", 0) + 1
    return render_template("mistakes.html", items=items[:LIST_LIMIT], total=len(items), skill=skill,
                           levels=sorted(levels.items()), size=min(PRACTICE_SIZE, len(items)))


@bp.route("/mistakes/practice")
@login_required
def practice():
    skill = request.args.get("skill")
    skill = skill if skill in SKILLS else None
    items = collect(current_user.id, skill)
    if not items:
        return render_template("mistakes.html", items=[], total=0, skill=skill, levels=[], size=0)
    picked = random.sample(items, min(PRACTICE_SIZE, len(items)))
    questions = {q.id: q for q in Question.query.filter(Question.id.in_([m["qid"] for m in picked]))}
    cards = []
    for m in picked:
        q = questions[m["qid"]]
        part = q.group.part
        cards.append({"m": m, "q": q, "qtype": q.group.qtype, "instruction": q.group.instruction,
                      "paras": _paras(part.passage) if m["skill"] == "reading" else [],
                      "audio": part.audio_url if m["skill"] == "listening" else None,
                      "image": part.image_url,
                      "bits": q.text.split("___") if q.group.qtype == "gap_fill" and "___" in (q.text or "") else None})
    return render_template("mistakes_practice.html", cards=cards, skill=skill or "")


@bp.route("/mistakes/practice", methods=["POST"])
@login_required
def check():
    """Grade the submitted answers. Only questions that really are in THIS student's mistake list are accepted."""
    wanted = {}
    for key, value in request.form.items():
        if re.fullmatch(r"m\d{1,9}", key):
            wanted[int(key[1:])] = value.strip()[:200]
    if not wanted or len(wanted) > PRACTICE_SIZE:
        abort(400)
    skill = request.form.get("skill")
    mine = {m["qid"]: m for m in collect(current_user.id, skill if skill in SKILLS else None)}
    questions = {q.id: q for q in Question.query.filter(Question.id.in_(list(wanted)))}
    review, fixed = [], 0
    for qid, given in wanted.items():
        if qid not in mine or qid not in questions:
            continue
        q = questions[qid]
        ok = is_correct(given, q.answer)
        if ok:
            fixed += 1
            if not MistakeFixed.query.filter_by(user_id=current_user.id, question_id=qid).first():
                db.session.add(MistakeFixed(user_id=current_user.id, question_id=qid))
            else:
                MistakeFixed.query.filter_by(user_id=current_user.id, question_id=qid).update(
                    {"created_at": datetime.now(timezone.utc).replace(tzinfo=None)})
        review.append({"m": mine[qid], "given": _show(q, given) if given else "", "ok": ok,
                       "correct": _show(q, q.answer.split("|")[0])})
    if not review:
        abort(400)
    db.session.commit()
    left = len(collect(current_user.id, skill if skill in SKILLS else None))
    return render_template("mistakes_result.html", review=review, fixed=fixed, left=left, skill=skill or "")
