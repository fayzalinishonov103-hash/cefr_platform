"""Daily progress for the dashboard: streak, today's activity, last 7 days, and a "next step" recommendation.

Activity = a finished Reading/Listening attempt, a graded Writing/Speaking answer or a video marked as seen in Shadowing. Days are counted in
Uzbekistan time (UTC+5, no daylight saving), while the database stores UTC.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from extensions import db
from models import Attempt, SkillResult, PracticeSet, VocabWord, ShadowMark
from skills import skills_profile

UZ_OFFSET = timedelta(hours=5)
WEEKDAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
SKILLS = [("reading", "Reading", "reading.tests"), ("listening", "Listening", "listening.tests"),
          ("writing", "Writing", "writing.tasks"), ("speaking", "Speaking", "speaking.tasks")]


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_date(dt):
    return (_utc(dt) + UZ_OFFSET).date()


def today_local(now=None):
    return local_date(now or datetime.now(timezone.utc))


def activity_counter(user):
    """{local date: number of activities}"""
    days = Counter()
    for (when,) in db.session.query(Attempt.finished_at).filter(Attempt.user_id == user.id,
                                                                  Attempt.finished_at.isnot(None)):
        days[local_date(when)] += 1
    for (when,) in db.session.query(SkillResult.created_at).filter(SkillResult.user_id == user.id,
                                                                     SkillResult.created_at.isnot(None)):
        days[local_date(when)] += 1
    for (when,) in db.session.query(PracticeSet.finished_at).filter(PracticeSet.user_id == user.id,
                                                                      PracticeSet.finished_at.isnot(None)):
        days[local_date(when)] += 1
    for (when,) in db.session.query(ShadowMark.created_at).filter(ShadowMark.user_id == user.id,
                                                                    ShadowMark.kind == "seen",
                                                                    ShadowMark.created_at.isnot(None)):
        days[local_date(when)] += 1
    return days


def streaks(days, today):
    """(current, best). The current streak stays alive if the last active day is today or yesterday."""
    active = {d for d, n in days.items() if n}
    day = today if today in active else today - timedelta(days=1)
    current = 0
    while day in active:
        current += 1
        day -= timedelta(days=1)
    best = run = 0
    prev = None
    for d in sorted(active):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return current, best


def recommendation(user, profile):
    """One concrete next step: a skill never tried, otherwise the weakest skill."""
    latest = profile["latest"]
    if all(latest[k] is None for k, _, _ in SKILLS):
        return {"text": "Birinchi mashqni bajaring: Reading testi darajangizni aniqlashga yordam beradi.",
                "endpoint": "reading.tests", "button": "READING BOSHLASH"}
    for key, label, endpoint in SKILLS:
        if latest[key] is None:
            return {"text": f"{label} hali sinab koʻrilmagan. Umumiy daraja barcha skillar boʻyicha hisoblanadi.",
                    "endpoint": endpoint, "button": f"{label.upper()} BOSHLASH"}
    key, label, endpoint = min(SKILLS, key=lambda s: latest[s[0]])
    return {"text": f"Eng past natija: {label} ({profile['levels'][key]}, {latest[key]}/75). Shu skill ustida ishlang.",
            "endpoint": endpoint, "button": f"{label.upper()} MASHQI"}


def dashboard_progress(user, now=None):
    now = now or datetime.now(timezone.utc)
    days, today = activity_counter(user), today_local(now)
    current, best = streaks(days, today)
    week = []
    for back in range(6, -1, -1):
        d = today - timedelta(days=back)
        week.append({"label": WEEKDAYS[d.weekday()], "done": days.get(d, 0) > 0, "today": back == 0})
    due = VocabWord.query.filter(VocabWord.user_id == user.id,
                                 VocabWord.next_review <= now.replace(tzinfo=None)).count()
    return {"streak": current, "best": best, "today": days.get(today, 0), "week": week, "vocab_due": due,
            "next": recommendation(user, skills_profile(user))}
