"""Onboarding after registration: 6 short questions (one per screen) that personalise the study plan.

Design rules:
  * the registration form itself stays short (name, e-mail, password or Telegram); everything here is optional;
  * no exact birth date, phone or address: only an age range and a region;
  * age range / region / source are statistics and are saved only with the user's consent;
  * the user can skip, and can edit the answers later (/onboarding).
"""
from datetime import date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, distinct

from extensions import db
import security
from models import User, UserProfile, SkillResult, Attempt, UsageLog, _naive_now
from admin import admin_required

bp = Blueprint("onboarding", __name__)

GOALS = [("cefr", "Milliy CEFR imtihoni"), ("university", "Universitetga kirish yoki oʻqish"),
         ("work_abroad", "Chet elda ish"), ("other", "Boshqa, oʻzim uchun")]
TARGETS = [("B1", "B1"), ("B2", "B2"), ("C1", "C1"), ("", "Hali bilmayman")]
MINUTES = [5, 10, 20, 30]
INTERESTS = [("football", "Futbol"), ("tech", "Texnologiya"), ("music", "Musiqa"), ("travel", "Sayohat"),
             ("business", "Biznes"), ("anime", "Anime"), ("movies", "Kino"), ("games", "Oʻyinlar"),
             ("science", "Fan"), ("sport", "Sport va sogʻliq")]
MAX_INTERESTS = 6
AGES = [("u15", "15 yoshgacha"), ("16-17", "16–17"), ("18-24", "18–24"), ("25-34", "25–34"), ("35+", "35 va katta")]
REGIONS = [("tashkent_c", "Toshkent shahri"), ("tashkent_r", "Toshkent viloyati"), ("andijan", "Andijon"),
           ("bukhara", "Buxoro"), ("fergana", "Fargʻona"), ("jizzakh", "Jizzax"), ("khorezm", "Xorazm"),
           ("namangan", "Namangan"), ("navoi", "Navoiy"), ("kashkadarya", "Qashqadaryo"),
           ("karakalpak", "Qoraqalpogʻiston"), ("samarkand", "Samarqand"), ("syrdarya", "Sirdaryo"),
           ("surkhandarya", "Surxondaryo"), ("abroad", "Oʻzbekistondan tashqarida")]
SOURCES = [("instagram", "Instagram"), ("telegram", "Telegram"), ("youtube", "YouTube yoki TikTok"),
           ("friend", "Doʻst yoki oʻqituvchi"), ("search", "Google qidiruvi"), ("other", "Boshqa")]
MAX_EXAM_DAYS = 730

_LABELS = {k: dict(v) for k, v in {"goal": GOALS, "target": TARGETS, "interest": INTERESTS, "age": AGES,
                                    "region": REGIONS, "source": SOURCES}.items()}


def parse_signup(form):
    """The three questions on the registration form itself: interests, age range, region (+ consent for the last two)."""
    interests = []
    for code in form.getlist("interests"):
        if code in _LABELS["interest"] and code not in interests:
            interests.append(code)
    if len(interests) > MAX_INTERESTS:
        return None, f"Qiziqishlardan koʻpi bilan {MAX_INTERESTS} tasini tanlang."
    consent = form.get("consent") == "1"
    age, region = form.get("age_range"), form.get("region")
    return {"interests": interests, "consent": consent,
            "age_range": age if consent and age in _LABELS["age"] else None,
            "region": region if consent and region in _LABELS["region"] else None}, None


def save_signup(user, data):
    """Create the profile row right after registration (not 'completed': the onboarding adds goal, level, time)."""
    if not (data["interests"] or data["consent"]):
        return
    db.session.add(UserProfile(user_id=user.id, interests=data["interests"], age_range=data["age_range"],
                               region=data["region"], consent_at=_naive_now() if data["consent"] else None))
    db.session.commit()


def signup_ctx(form):
    """Values and option lists for the registration template (kept on a validation error)."""
    v = {"interests": form.getlist("interests") if form else [], "age_range": form.get("age_range") if form else None,
         "region": form.get("region") if form else None, "consent": bool(form and form.get("consent") == "1")}
    return {"v": v, "interests": INTERESTS, "ages": AGES, "regions": REGIONS, "max_interests": MAX_INTERESTS}


def parse(form, today=None, short=False):
    """Validate the submitted form. Returns (clean_dict, error_or_None). Unknown codes are rejected, never stored.
    short=True: the interests/age/region/consent answers were already given at registration and are left untouched."""
    today = today or date.today()
    pick = lambda name, labels: (form.get(name) or "").strip() if (form.get(name) or "").strip() in labels else None
    goal = pick("goal", _LABELS["goal"])
    target = form.get("target_level")
    target = target if target in _LABELS["target"] else None
    minutes = form.get("daily_minutes", "")
    minutes = int(minutes) if minutes.isdigit() and int(minutes) in MINUTES else None
    interests = []
    for code in form.getlist("interests"):
        if code in _LABELS["interest"] and code not in interests:
            interests.append(code)
    if len(interests) > MAX_INTERESTS:
        return None, f"Qiziqishlardan koʻpi bilan {MAX_INTERESTS} tasini tanlang."
    exam = None
    raw = (form.get("exam_date") or "").strip()
    if raw:
        try:
            exam = date.fromisoformat(raw)
        except ValueError:
            return None, "Imtihon sanasi notoʻgʻri."
        if not today <= exam <= today + timedelta(days=MAX_EXAM_DAYS):
            return None, "Imtihon sanasi bugundan keyin va 2 yil ichida boʻlsin."
    if short:
        return {"short": True, "goal": goal, "target_level": target, "exam_date": exam, "daily_minutes": minutes,
                "source": pick("source", _LABELS["source"])}, None
    consent = form.get("consent") == "1"
    clean = {"goal": goal, "target_level": target, "exam_date": exam, "daily_minutes": minutes,
             "interests": interests,
             # statistics fields exist only with consent
             "age_range": pick("age_range", _LABELS["age"]) if consent else None,
             "region": pick("region", _LABELS["region"]) if consent else None,
             "source": pick("source", _LABELS["source"]) if consent else None,
             "consent": consent}
    return clean, None


def profile_of(user):
    return UserProfile.query.filter_by(user_id=user.id).first()


def summary(profile, today=None):
    """Short facts for the dashboard line, or None when there is nothing useful to show."""
    if not profile or not profile.completed_at:
        return None
    today = today or date.today()
    parts = []
    if profile.target_level:
        parts.append(f"Maqsad: {profile.target_level}")
    elif profile.goal:
        parts.append(f"Maqsad: {_LABELS['goal'][profile.goal]}")
    if profile.daily_minutes:
        parts.append(f"kuniga {profile.daily_minutes} daqiqa")
    if profile.exam_date and profile.exam_date >= today:
        parts.append(f"imtihongacha {(profile.exam_date - today).days} kun")
    return " · ".join(parts) or None


def _save(user, clean):
    profile = profile_of(user) or UserProfile(user_id=user.id)
    now = _naive_now()
    profile.goal, profile.target_level = clean["goal"], clean["target_level"]
    profile.exam_date, profile.daily_minutes = clean["exam_date"], clean["daily_minutes"]
    if clean.get("short"):
        profile.source = clean["source"] if profile.consent_at else None      # statistics only with consent
        profile.completed_at, profile.skipped_at = now, None
        db.session.add(profile)
        db.session.commit()
        return
    profile.interests = clean["interests"]
    profile.age_range, profile.region, profile.source = clean["age_range"], clean["region"], clean["source"]
    profile.consent_at = (profile.consent_at or now) if clean["consent"] else None
    profile.completed_at, profile.skipped_at = now, None
    db.session.add(profile)
    db.session.commit()


def _next_page(user):
    return url_for("placement.intro")


@bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def edit():
    profile = profile_of(current_user)
    if request.method == "POST":
        if request.form.get("action") == "skip":
            if profile is None:
                db.session.add(UserProfile(user_id=current_user.id, skipped_at=_naive_now()))
                db.session.commit()
            elif not profile.completed_at:
                profile.skipped_at = _naive_now()
                db.session.commit()
            return redirect(_next_page(current_user))
        short = request.form.get("short") == "1"
        clean, error = parse(request.form, short=short)
        if error:
            flash(error, "error")
            return render_template("onboarding.html", **_ctx(profile, request.form, short)), 400
        _save(current_user, clean)
        flash("Rahmat! Reja siz aytgan maqsadga moslanadi.", "ok")
        return redirect(_next_page(current_user))
    short = True      # goal, level, minutes. Interests / age / region are no longer asked
    return render_template("onboarding.html", **_ctx(profile, None, short))


def _ctx(profile, form, short=False):
    """Template values: from the failed form if there is one, else from the saved profile."""
    if form is not None:
        v = {"goal": form.get("goal"), "target_level": form.get("target_level"), "exam_date": form.get("exam_date", ""),
             "daily_minutes": int(form["daily_minutes"]) if form.get("daily_minutes", "").isdigit() else None,
             "interests": form.getlist("interests"), "age_range": form.get("age_range"), "region": form.get("region"),
             "source": form.get("source"), "consent": form.get("consent") == "1"}
    elif profile:
        v = {"goal": profile.goal, "target_level": profile.target_level, "exam_date": profile.exam_date.isoformat() if profile.exam_date else "",
             "daily_minutes": profile.daily_minutes, "interests": profile.interests or [], "age_range": profile.age_range,
             "region": profile.region, "source": profile.source, "consent": bool(profile.consent_at)}
    else:
        v = {"goal": None, "target_level": None, "exam_date": "", "daily_minutes": None, "interests": [],
             "age_range": None, "region": None, "source": None, "consent": False}
    return {"short": short, "v": v, "goals": GOALS, "targets": TARGETS, "minutes": MINUTES, "interests": INTERESTS, "ages": AGES,
            "regions": REGIONS, "sources": SOURCES, "max_interests": MAX_INTERESTS,
            "today": date.today().isoformat(), "last": (date.today() + timedelta(days=MAX_EXAM_DAYS)).isoformat()}


@bp.route("/maxfiylik")
def privacy():
    return render_template("privacy.html", contact=current_app.config.get("PRIVACY_CONTACT", ""))


@bp.route("/shartlar")
def terms():
    return render_template("terms.html", contact=current_app.config.get("PRIVACY_CONTACT", ""))


# ------------------------------------------------------------------ admin statistics
def _unique_users(column, *conditions):
    return db.session.query(func.count(distinct(column))).filter(*conditions).scalar() or 0


def funnel(users, done):
    """Where people drop off: each step counts distinct users who reached it."""
    return [("Roʻyxatdan oʻtgan", users),
            ("Onboardingni tugatgan", done),
            ("Daraja aniqlash testini topshirgan", _unique_users(SkillResult.user_id, SkillResult.skill == "placement")),
            ("Kamida 1 ta Reading/Listening testni tugatgan", _unique_users(Attempt.user_id, Attempt.finished_at.isnot(None))),
            ("Writing yoki Speaking topshirgan", _unique_users(SkillResult.user_id, SkillResult.skill.in_(("writing", "speaking"))))]
def _count(column):
    rows = (db.session.query(column, func.count(UserProfile.id)).filter(column.isnot(None))
            .group_by(column).order_by(func.count(UserProfile.id).desc()).all())
    return rows


@bp.route("/admin/onboarding")
@admin_required
def stats():
    done = UserProfile.query.filter(UserProfile.completed_at.isnot(None)).count()
    consented = UserProfile.query.filter(UserProfile.consent_at.isnot(None)).count()
    interests = {}
    for (items,) in db.session.query(UserProfile.interests):
        for code in items or []:
            interests[code] = interests.get(code, 0) + 1
    def named(rows, key):
        return [(_LABELS[key].get(code, str(code)), n) for code, n in rows]
    data = {
        "Maqsad": named(_count(UserProfile.goal), "goal"),
        "Maqsadli daraja": [(c or "Hali bilmaydi", n) for c, n in db.session.query(UserProfile.target_level, func.count(UserProfile.id))
                            .filter(UserProfile.completed_at.isnot(None), UserProfile.target_level.isnot(None)).group_by(UserProfile.target_level).all()],
        "Kunlik vaqt": [(f"{m} daqiqa", n) for m, n in _count(UserProfile.daily_minutes)],
        "Qiziqishlar": sorted(((_LABELS["interest"].get(c, c), n) for c, n in interests.items()), key=lambda x: -x[1]),
        "Yosh oraligʻi": named(_count(UserProfile.age_range), "age"),
        "Viloyat": named(_count(UserProfile.region), "region"),
        "Qayerdan eshitgan": named(_count(UserProfile.source), "source"),
    }
    users = User.query.count()
    now = security.now()
    return render_template("admin_onboarding.html", data=data, users=users, done=done, consented=consented,
                           funnel=funnel(users, done),
                           new7=User.query.filter(User.created_at >= now - timedelta(days=7)).count(),
                           ai24=UsageLog.query.filter(UsageLog.created_at >= now - timedelta(hours=24)).count(),
                           ai_cap=current_app.config.get("AI_GLOBAL_DAILY_CAP", 0))
