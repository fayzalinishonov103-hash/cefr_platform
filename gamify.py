"""XP, levels, badges and the opt-in weekly leaderboard.

Rules that keep it honest:
  * XP is only written through award(), and (user, reason, ref) is unique in the database, so a replayed or double-clicked
    request can never pay twice;
  * the hooks called from the normal test flows (after_test / after_ai) can NEVER break those flows: any error is
    logged and swallowed;
  * the leaderboard is opt-in and shows a nickname chosen by the student, never a real name or e-mail.
"""
import logging
import math
import re
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

import security
from extensions import db
from models import (XpEvent, Badge, LeaderboardMember, PracticeLog, PracticeSet, Attempt, Test, SkillResult,
                    MistakeFixed)

log = logging.getLogger(__name__)

XP_PER_CORRECT_IN_TEST = 3
XP_WRITING = XP_SPEAKING = 40
XP_PRACTICE_ANSWER, XP_PRACTICE_CORRECT = 5, 5
XP_DAILY_BONUS, XP_DAILY_STREAK_STEP, XP_DAILY_STREAK_MAX = 20, 3, 10
NICK_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")

BADGES = {
    "first_test": ("Birinchi qadam", "Birinchi testni tugatdingiz"),
    "tests_10": ("Tajribali", "10 ta test tugatdingiz"),
    "correct_100": ("Yuz toʻgʻri", "Jami 100 ta toʻgʻri javob berdingiz"),
    "streak_7": ("Haftalik seriya", "7 kun ketma-ket mashq qildingiz"),
    "streak_30": ("Oylik seriya", "30 kun ketma-ket mashq qildingiz"),
    "first_writing": ("Yozuvchi", "Birinchi Writing AI bahosi"),
    "first_speaking": ("Notiq", "Birinchi Speaking AI bahosi"),
    "smart_10": ("Aqlli oʻquvchi", "10 ta aqlli mashqni tugatdingiz"),
    "daily_5": ("Doimiy", "5 ta kunlik challenge tugatdingiz"),
    "perfect_daily": ("Mukammal kun", "Kunlik challenge'da hamma javob toʻgʻri"),
    "fixer_20": ("Xato tuzatuvchi", "20 ta xatoni tuzatdingiz"),
    "level_5": ("5-daraja", "XP darajasi 5 ga yetdi"),
}


# ------------------------------------------------------------------ XP and levels
def award(user_id, amount, reason, ref):
    """Give XP once per (user, reason, ref). Returns True when it was paid now, False when it had been paid before."""
    if amount <= 0:
        return False
    db.session.add(XpEvent(user_id=user_id, amount=int(amount), reason=reason, ref=str(ref)))
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def total_xp(user_id, since=None):
    q = db.session.query(db.func.coalesce(db.func.sum(XpEvent.amount), 0)).filter(XpEvent.user_id == user_id)
    if since is not None:
        q = q.filter(XpEvent.created_at >= since)
    return int(q.scalar() or 0)


def level_info(xp):
    """Level n needs 50*(n-1)^2 XP: 50, 200, 450, 800... Returns level, progress inside the level (0-100) and XP to the next."""
    level = int(math.sqrt(max(xp, 0) / 50)) + 1
    floor_xp, next_xp = 50 * (level - 1) ** 2, 50 * level ** 2
    return {"level": level, "pct": round(100 * (xp - floor_xp) / (next_xp - floor_xp)), "to_next": next_xp - xp,
            "xp": xp, "next_xp": next_xp}


# ------------------------------------------------------------------ badges
def _give(user_id, code, have, new):
    if code in have:
        return
    db.session.add(Badge(user_id=user_id, code=code))
    try:
        db.session.commit()
        new.append(code)
        have.add(code)
    except IntegrityError:
        db.session.rollback()
        have.add(code)


def check_badges(user_id):
    """Award every badge the user has now earned. Idempotent. Returns the codes earned by THIS call."""
    from progress import activity_counter, streaks, today_local
    from models import User
    have = {b.code for b in Badge.query.filter_by(user_id=user_id)}
    if len(have) == len(BADGES):
        return []
    new = []
    tests = Attempt.query.join(Test, Test.id == Attempt.test_id).filter(
        Attempt.user_id == user_id, Attempt.finished_at.isnot(None), Test.skill.in_(("reading", "listening"))).count()
    corrects = (db.session.query(db.func.coalesce(db.func.sum(Attempt.raw_score), 0))
                .filter(Attempt.user_id == user_id, Attempt.finished_at.isnot(None)).scalar() or 0)
    corrects += PracticeLog.query.filter_by(user_id=user_id, correct=True).count()
    dailies = PracticeSet.query.filter(PracticeSet.user_id == user_id, PracticeSet.kind == "daily",
                                       PracticeSet.finished_at.isnot(None)).all()
    smart = PracticeSet.query.filter(PracticeSet.user_id == user_id, PracticeSet.kind == "smart",
                                     PracticeSet.finished_at.isnot(None)).count()
    user = db.session.get(User, user_id)
    cur, _best = streaks(activity_counter(user), today_local())
    checks = {
        "first_test": tests >= 1, "tests_10": tests >= 10, "correct_100": corrects >= 100,
        "streak_7": cur >= 7, "streak_30": cur >= 30,
        "first_writing": SkillResult.query.filter_by(user_id=user_id, skill="writing").count() >= 1,
        "first_speaking": SkillResult.query.filter_by(user_id=user_id, skill="speaking").count() >= 1,
        "smart_10": smart >= 10, "daily_5": len(dailies) >= 5,
        "perfect_daily": any(d.total and d.total >= 3 and d.correct == d.total for d in dailies),
        "fixer_20": MistakeFixed.query.filter_by(user_id=user_id).count() >= 20,
        "level_5": level_info(total_xp(user_id))["level"] >= 5,
    }
    for code, ok in checks.items():
        if ok:
            _give(user_id, code, have, new)
    return new


# ------------------------------------------------------------------ hooks for the existing flows (never raise)
def after_test(user_id, attempt):
    try:
        award(user_id, XP_PER_CORRECT_IN_TEST * (attempt.raw_score or 0), "test", attempt.id)
        check_badges(user_id)
    except Exception:
        db.session.rollback()
        log.exception("XP hook failed (test)")


def after_ai_result(user_id, skill, result_id):
    try:
        award(user_id, XP_WRITING if skill == "writing" else XP_SPEAKING, skill, result_id)
        check_badges(user_id)
    except Exception:
        db.session.rollback()
        log.exception("XP hook failed (ai result)")


# ------------------------------------------------------------------ what the pages show
def summary(user):
    from progress import today_local
    xp = total_xp(user.id)
    daily = PracticeSet.query.filter_by(user_id=user.id, kind="daily", day=today_local()).first()
    earned = Badge.query.filter_by(user_id=user.id).order_by(Badge.created_at.desc()).all()
    return {**level_info(xp), "daily": daily, "badges": earned,
            "member": LeaderboardMember.query.filter_by(user_id=user.id).first()}


def all_badges(user_id):
    """[(code, title, description, earned_at or None)] for the badge wall (earned first)."""
    got = {b.code: b.created_at for b in Badge.query.filter_by(user_id=user_id)}
    rows = [(c, t, d, got.get(c)) for c, (t, d) in BADGES.items()]
    return sorted(rows, key=lambda r: (r[3] is None, r[3] or 0))


# ------------------------------------------------------------------ leaderboard (opt-in, nickname only)
class NicknameError(ValueError):
    pass


def join_leaderboard(user_id, nickname):
    nickname = (nickname or "").strip()
    if not NICK_RE.match(nickname):
        raise NicknameError("Taxallus 3–20 ta belgidan iborat boʻlsin: lotin harflari, raqam, _ yoki -.")
    if LeaderboardMember.query.filter_by(user_id=user_id).first():
        raise NicknameError("Siz allaqachon reytingdasiz.")
    db.session.add(LeaderboardMember(user_id=user_id, nickname=nickname, nick_key=nickname.lower()))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise NicknameError("Bu taxallus band. Boshqasini tanlang.")


def leave_leaderboard(user_id):
    LeaderboardMember.query.filter_by(user_id=user_id).delete()
    db.session.commit()


def weekly_top(limit=20, days=7):
    """[(rank, nickname, xp, user_id)] over the last `days` days, members only, best first."""
    since = security.now() - timedelta(days=days)
    rows = (db.session.query(LeaderboardMember.nickname, db.func.coalesce(db.func.sum(XpEvent.amount), 0).label("xp"),
                             LeaderboardMember.user_id)
            .outerjoin(XpEvent, db.and_(XpEvent.user_id == LeaderboardMember.user_id, XpEvent.created_at >= since))
            .group_by(LeaderboardMember.id).order_by(db.text("xp DESC"), LeaderboardMember.id).all())
    ranked = [(i, n, int(x), uid) for i, (n, x, uid) in enumerate(rows, 1)]
    return ranked[:limit], ranked
