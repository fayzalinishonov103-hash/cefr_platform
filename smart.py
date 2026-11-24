"""Smart practice: an adaptive session built from the whole question bank, plus the daily challenge.

How a session is chosen (no AI, no cost):
  1. MASTERY: from the student's real test answers and earlier smart answers, accuracy per question type and per CEFR level
     (newer answers weigh more: half-life 30 days; a small prior keeps three lucky answers from meaning "mastered").
  2. NEED of every question = weak question type + weak level + closeness to a level just above the student's own
     + a bonus for never-seen questions or ones answered wrong before - a penalty for ones answered right very recently
     (a simple spaced-repetition rule).
  3. Questions share a text/audio/map, so the session is built around the best-scoring PART(s), not random single questions.
The session is stored; a submit can only answer the questions that were issued, and every request grades on the server.
"""
import logging
import random
import re
from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, request, abort, flash
from flask_login import login_required, current_user

import gamify
import security
from extensions import db
from grading import is_correct, _show, LEVEL_ORDER
from models import (Attempt, Test, Part, QuestionGroup, Question, PracticeSet, PracticeLog, MistakeFixed, SkillResult, XpEvent)
from progress import today_local, activity_counter, streaks
from skills import QTYPE_LABELS, skills_profile

bp = Blueprint("smart", __name__)
log = logging.getLogger(__name__)

SKILLS = ("reading", "listening")
SET_SIZE, DAILY_SIZE = 8, 5
MAX_ATTEMPTS, MAX_LOGS = 30, 800
PRIOR_ACC, PRIOR_WEIGHT, HALF_LIFE_DAYS = 0.6, 2.0, 30.0
MIN_SAMPLE = 3


# ------------------------------------------------------------------ history and mastery
def level_index(label, default=2):
    """'B2' -> 3. Unknown or 'B1 dan past' -> default (or 1 for 'B1 dan past')."""
    if label and label.startswith("B1 dan"):
        return 1
    return LEVEL_ORDER.index(label) if label in LEVEL_ORDER else default


def user_level(user):
    """Index of the student's estimated level: overall profile, else the placement test, else B1."""
    overall = skills_profile(user)["overall_level"]
    if overall:
        return level_index(overall)
    placed = (SkillResult.query.filter_by(user_id=user.id, skill="placement")
              .order_by(SkillResult.created_at.desc()).first())
    return level_index(placed.cefr_level) if placed else 2


def history(user_id):
    """Every answer we know, newest first: [{qid, qtype, level, correct, when}]."""
    events = []
    attempts = (Attempt.query.join(Test, Test.id == Attempt.test_id)
                .filter(Attempt.user_id == user_id, Attempt.finished_at.isnot(None), Test.skill.in_(SKILLS))
                .order_by(Attempt.finished_at.desc(), Attempt.id.desc()).limit(MAX_ATTEMPTS).all())
    if attempts:
        test_ids = {a.test_id for a in attempts}
        by_test = {}
        rows = (db.session.query(Question, QuestionGroup, Part)
                .join(QuestionGroup, QuestionGroup.id == Question.group_id)
                .join(Part, Part.id == QuestionGroup.part_id).filter(Part.test_id.in_(test_ids)).all())
        for q, g, p in rows:
            by_test.setdefault(p.test_id, []).append((q, g))
        for a in attempts:
            answers = a.answers or {}
            when = security.naive(a.finished_at)
            for q, g in by_test.get(a.test_id, []):
                events.append({"qid": q.id, "qtype": g.qtype, "level": q.cefr_level, "when": when,
                               "correct": is_correct(answers.get(f"q{q.number}", ""), q.answer)})
    for row in PracticeLog.query.filter_by(user_id=user_id).order_by(PracticeLog.created_at.desc()).limit(MAX_LOGS):
        events.append({"qid": row.question_id, "qtype": row.qtype, "level": row.level, "when": row.created_at,
                       "correct": row.correct})
    events.sort(key=lambda e: e["when"], reverse=True)
    return events


def mastery(events, now=None):
    """{'type': {qtype: {acc, n}}, 'level': {level: {acc, n}}}; acc is a recency-weighted accuracy pulled toward a prior."""
    now = now or security.now()
    out = {"type": {}, "level": {}}
    sums = {"type": {}, "level": {}}
    for e in events:
        age = max((now - e["when"]).total_seconds() / 86400, 0)
        w = 0.5 ** (age / HALF_LIFE_DAYS)
        for dim, key in (("type", e["qtype"]), ("level", e["level"] or "?")):
            c, t, n = sums[dim].setdefault(key, [0.0, 0.0, 0])
            sums[dim][key] = [c + w * e["correct"], t + w, n + 1]
    for dim in sums:
        for key, (c, t, n) in sums[dim].items():
            out[dim][key] = {"acc": (c + PRIOR_ACC * PRIOR_WEIGHT) / (t + PRIOR_WEIGHT), "n": n}
    return out


def need(q, qtype, stats, last, lvl, now, rng):
    """How much this question is worth practising right now (higher = more). Returns (score, tags)."""
    tags = []
    type_row = stats["type"].get(qtype)
    type_w = 1 - (type_row["acc"] if type_row else PRIOR_ACC)
    lvl_row = stats["level"].get(q.cefr_level or "?")
    lvl_w = 1 - (lvl_row["acc"] if lvl_row else PRIOR_ACC)
    fit = max(0.0, 1 - abs(level_index(q.cefr_level, lvl) - (lvl + 0.5)) / 3)
    score = 0.45 * type_w + 0.2 * lvl_w + 0.2 * fit
    if type_row and type_row["n"] >= MIN_SAMPLE and type_row["acc"] < PRIOR_ACC:
        tags.append(f"{QTYPE_LABELS.get(qtype, qtype)}: {round((1 - type_row['acc']) * 100)}% xato")
    seen = last.get(q.id)
    if seen is None:
        score += 0.1
        tags.append("Yangi savol")
    else:
        when, ok = seen
        age = (now - when).total_seconds() / 86400
        if not ok and age >= 1:
            score += 0.3
            tags.append("Qayta takrorlash")
        elif ok and age < 2:
            score -= 0.6
        elif ok and age < 7:
            score -= 0.3
    if q.cefr_level:
        tags.append(q.cefr_level)
    return score + rng.random() * 0.03, tags


def build_set(user, skill, size, rng=None, now=None):
    """-> list of (Question, QuestionGroup, Part, Test, tags) built around the best part(s), or [] when the bank is empty."""
    rng, now = rng or random.Random(), now or security.now()
    skills = SKILLS if skill == "any" else (skill,)
    rows = (db.session.query(Question, QuestionGroup, Part, Test)
            .join(QuestionGroup, QuestionGroup.id == Question.group_id).join(Part, Part.id == QuestionGroup.part_id)
            .join(Test, Test.id == Part.test_id).filter(Test.is_active.is_(True), Test.skill.in_(skills)).all())
    if not rows:
        return []
    events = history(user.id)
    stats, lvl = mastery(events, now), user_level(user)
    last = {}
    for e in events:                                   # newest first: the first sighting is the latest answer
        last.setdefault(e["qid"], (e["when"], e["correct"]))
    parts = {}
    for q, g, p, t in rows:
        score, tags = need(q, g.qtype, stats, last, lvl, now, rng)
        parts.setdefault(p.id, []).append((score, q, g, p, t, tags))
    ranked = sorted(parts.values(), key=lambda items: -sum(s for s, *_ in sorted(items, key=lambda x: -x[0])[:5])
                    / min(5, len(items)))
    picked = []
    for items in ranked:
        for item in sorted(items, key=lambda x: -x[0]):
            if len(picked) < size:
                picked.append(item)
        if len(picked) >= size:
            break
    picked.sort(key=lambda x: (x[3].test_id, x[3].number, x[1].number))
    return [(q, g, p, t, tags) for _s, q, g, p, t, tags in picked]


# ------------------------------------------------------------------ pages
def _paras(passage):
    return [" ".join(x.split()) for x in re.split(r"\n\s*\n", passage or "") if x.strip()]


def card(q, group, part, test, tags):
    return {"q": q, "qtype": group.qtype, "instruction": group.instruction, "test": test.title, "part": part.number,
            "skill": test.skill, "tags": tags, "paras": _paras(part.passage) if test.skill == "reading" else [],
            "audio": part.audio_url if test.skill == "listening" else None, "image": part.image_url,
            "bits": q.text.split("___") if group.qtype == "gap_fill" and "___" in (q.text or "") else None}


def _issue(user, kind, skill, size, day=None, rng=None):
    picked = build_set(user, skill, size, rng)
    if not picked:
        return None
    ps = PracticeSet(user_id=user.id, kind=kind, skill=skill, day=day, question_ids=[q.id for q, *_ in picked],
                     reasons={str(q.id): tags for q, _g, _p, _t, tags in picked})
    db.session.add(ps)
    db.session.commit()
    return ps


def _own_set(set_id):
    ps = db.session.get(PracticeSet, set_id)
    if ps is None or ps.user_id != current_user.id:
        abort(404)
    return ps


@bp.route("/smart")
@login_required
def home():
    events = history(current_user.id)
    stats = mastery(events)
    types = sorted(({"label": QTYPE_LABELS.get(k, k), "acc": round(v["acc"] * 100), "n": v["n"], "weak": v["n"] >= MIN_SAMPLE and v["acc"] < PRIOR_ACC}
                    for k, v in stats["type"].items()), key=lambda r: r["acc"])
    levels = [{"label": l, "acc": round(stats["level"][l]["acc"] * 100), "n": stats["level"][l]["n"]}
              for l in LEVEL_ORDER if l in stats["level"]]
    cur, best = streaks(activity_counter(current_user), today_local())
    return render_template("smart_home.html", g=gamify.summary(current_user), types=types, levels=levels,
                           badges=gamify.all_badges(current_user.id), streak=cur, best=best, answered=len(events),
                           labels=QTYPE_LABELS)


@bp.route("/smart/start", methods=["POST"])
@login_required
def start():
    skill = request.form.get("skill", "any")
    if skill not in SKILLS + ("any",):
        abort(400)
    open_set = (PracticeSet.query.filter_by(user_id=current_user.id, kind="smart", finished_at=None)
                .order_by(PracticeSet.id.desc()).first())
    if open_set and open_set.skill == skill and (security.now() - open_set.created_at) < timedelta(hours=6):
        return redirect(url_for("smart.session", set_id=open_set.id))           # resume instead of re-rolling
    ps = _issue(current_user, "smart", skill, SET_SIZE)
    if ps is None:
        flash("Hozircha mashq uchun savol yoʻq. Administrator test qoʻshishi kerak.", "error")
        return redirect(url_for("smart.home"))
    return redirect(url_for("smart.session", set_id=ps.id))


@bp.route("/smart/daily", methods=["POST"])
@login_required
def daily():
    """Today's challenge: one per day (Uzbekistan time). Calling it again returns the SAME set."""
    day = today_local()
    ps = PracticeSet.query.filter_by(user_id=current_user.id, kind="daily", day=day).first()
    if ps is None:
        ps = _issue(current_user, "daily", "any", DAILY_SIZE, day=day, rng=random.Random(f"{current_user.id}:{day}"))
        if ps is None:
            flash("Hozircha kunlik challenge uchun savol yoʻq. Administrator test qoʻshishi kerak.", "error")
            return redirect(url_for("smart.home"))
    return redirect(url_for("smart.result" if ps.finished_at else "smart.session", set_id=ps.id))


def _questions(ps):
    """Questions of the set that still exist (an admin edit may have replaced some), in the issued order."""
    found = {q.id: q for q in Question.query.filter(Question.id.in_(ps.question_ids))}
    return [found[i] for i in ps.question_ids if i in found]


@bp.route("/smart/<int:set_id>")
@login_required
def session(set_id):
    ps = _own_set(set_id)
    if ps.finished_at:
        return redirect(url_for("smart.result", set_id=ps.id))
    cards = []
    for q in _questions(ps):
        part = q.group.part
        cards.append(card(q, q.group, part, part.test, (ps.reasons or {}).get(str(q.id), [])))
    if not cards:
        flash("Bu mashqning savollari oʻzgartirilgan. Yangi mashq boshlang.", "error")
        return redirect(url_for("smart.home"))
    return render_template("smart_practice.html", ps=ps, cards=cards)


def _fix_mistakes(user_id, correct_ids):
    """A correct answer here also clears the question from the mistakes notebook (if it was in it)."""
    if not correct_ids:
        return
    from mistakes import collect
    mine = {m["qid"] for m in collect(user_id)}
    now = security.now()
    for qid in correct_ids & mine:
        row = MistakeFixed.query.filter_by(user_id=user_id, question_id=qid).first()
        if row:
            row.created_at = now
        else:
            db.session.add(MistakeFixed(user_id=user_id, question_id=qid))


@bp.route("/smart/<int:set_id>/submit", methods=["POST"])
@login_required
def submit(set_id):
    ps = _own_set(set_id)
    if ps.finished_at:
        return redirect(url_for("smart.result", set_id=ps.id))
    questions = _questions(ps)
    correct_ids, total = set(), 0
    for q in questions:                                   # only the issued questions are graded; extra form keys are ignored
        given = request.form.get(f"s{q.id}", "").strip()[:200]
        ok = is_correct(given, q.answer)
        total += 1
        if ok:
            correct_ids.add(q.id)
        db.session.add(PracticeLog(user_id=current_user.id, question_id=q.id, qtype=q.group.qtype,
                                   level=q.cefr_level, correct=ok))
    ps.finished_at, ps.correct, ps.total = security.now(), len(correct_ids), total
    _fix_mistakes(current_user.id, correct_ids)
    db.session.commit()
    _reward(ps)
    return redirect(url_for("smart.result", set_id=ps.id))


def _reward(ps):
    """XP and badges. Cannot break the submit, and cannot pay twice (unique per user/reason/ref)."""
    try:
        base = gamify.XP_PRACTICE_ANSWER * (ps.total or 0) + gamify.XP_PRACTICE_CORRECT * (ps.correct or 0)
        gamify.award(ps.user_id, base, ps.kind, ps.id)
        if ps.kind == "daily" and ps.total and ps.correct / ps.total >= 0.8:
            from models import User
            cur, _ = streaks(activity_counter(db.session.get(User, ps.user_id)), today_local())
            bonus = gamify.XP_DAILY_BONUS + gamify.XP_DAILY_STREAK_STEP * min(cur, gamify.XP_DAILY_STREAK_MAX)
            gamify.award(ps.user_id, bonus, "bonus", f"daily-{ps.id}")
        gamify.check_badges(ps.user_id)
    except Exception:
        db.session.rollback()
        log.exception("smart reward failed")


@bp.route("/smart/<int:set_id>/result")
@login_required
def result(set_id):
    ps = _own_set(set_id)
    if not ps.finished_at:
        return redirect(url_for("smart.session", set_id=ps.id))
    logs = {r.question_id: r.correct for r in PracticeLog.query.filter(
        PracticeLog.user_id == current_user.id, PracticeLog.question_id.in_(ps.question_ids),
        PracticeLog.created_at >= ps.created_at).order_by(PracticeLog.id)}
    rows = []
    for q in _questions(ps):
        rows.append({"q": q, "ok": logs.get(q.id), "key": _show(q, q.answer.split("|")[0]),
                     "tags": (ps.reasons or {}).get(str(q.id), []), "part": q.group.part.number,
                     "test": q.group.part.test.title})
    xp = db.session.query(db.func.coalesce(db.func.sum(XpEvent.amount), 0)).filter(
        XpEvent.user_id == current_user.id, XpEvent.ref.in_([str(ps.id), f"daily-{ps.id}"]),
        XpEvent.reason.in_([ps.kind, "bonus"])).scalar()
    return render_template("smart_result.html", ps=ps, rows=rows, xp=int(xp or 0), g=gamify.summary(current_user))


# ------------------------------------------------------------------ leaderboard
@bp.route("/leaderboard")
@login_required
def leaderboard():
    top, everyone = gamify.weekly_top()
    mine = next((r for r in everyone if r[3] == current_user.id), None)
    return render_template("leaderboard.html", top=top, mine=mine, member=mine is not None, total=len(everyone))


@bp.route("/leaderboard/join", methods=["POST"])
@login_required
def join():
    try:
        gamify.join_leaderboard(current_user.id, request.form.get("nickname", ""))
        flash("Reytingga qoʻshildingiz.", "ok")
    except gamify.NicknameError as e:
        flash(str(e), "error")
    return redirect(url_for("smart.leaderboard"))


@bp.route("/leaderboard/leave", methods=["POST"])
@login_required
def leave():
    gamify.leave_leaderboard(current_user.id)
    flash("Reytingdan chiqdingiz. Taxallusingiz oʻchirildi.", "ok")
    return redirect(url_for("smart.leaderboard"))
