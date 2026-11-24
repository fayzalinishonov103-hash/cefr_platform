"""Onboarding + Levi branding.  Run:  python -m pytest -q test_onboarding.py"""
import pytest

from app import create_app
from extensions import db
from models import User, UserProfile

GOOD_PW = "Correct-Horse-9"


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin); u.set_password("password123"); db.session.add(u)
        db.session.commit()
    return app


def login(c, email="stud@x.uz"):
    return c.post("/login", data={"email": email, "password": "password123"})


def profile(app, email="stud@x.uz"):
    with app.app_context():
        return UserProfile.query.join(User, User.id == UserProfile.user_id).filter(User.email == email).first()


def test_register_asks_only_essentials_and_goes_to_short_onboarding(app):
    c = app.test_client()
    page = c.get("/register").get_data(as_text=True)
    assert 'name="interests"' not in page and 'name="age_range"' not in page and 'name="region"' not in page   # only the essentials
    r = c.post("/register", data={"name": "Ali", "email": "ali@x.uz", "password": GOOD_PW, "interests": ["anime", "tech"],
                                  "age_range": "16-17", "region": "samarkand", "consent": "1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/onboarding?r=1")
    p = profile(app, "ali@x.uz")
    assert p.interests == ["anime", "tech"] and p.region == "samarkand" and p.age_range == "16-17" and p.consent_at and not p.completed_at
    short = c.get("/onboarding?r=1").get_data(as_text=True)
    assert 'name="short"' in short and 'name="interests"' not in short and 'name="region"' not in short   # not asked twice


def test_register_without_consent_drops_age_and_region_but_keeps_interests(app):
    c = app.test_client()
    c.post("/register", data={"name": "Vali", "email": "vali@x.uz", "password": GOOD_PW, "interests": ["music"],
                              "age_range": "18-24", "region": "andijan"})
    p = profile(app, "vali@x.uz")
    assert p.interests == ["music"] and p.age_range is None and p.region is None and p.consent_at is None


def test_register_too_many_interests_rejected_and_nothing_created(app):
    c = app.test_client()
    r = c.post("/register", data={"name": "X", "email": "x1@x.uz", "password": GOOD_PW,
                                  "interests": ["football", "tech", "music", "travel", "business", "anime", "movies"]})
    assert r.status_code == 400
    with app.app_context():
        assert User.query.filter_by(email="x1@x.uz").count() == 0


def test_short_onboarding_keeps_signup_answers(app):
    c = app.test_client()
    c.post("/register", data={"name": "Ali", "email": "ali@x.uz", "password": GOOD_PW, "interests": ["anime"],
                              "region": "samarkand", "age_range": "16-17", "consent": "1"})
    r = c.post("/onboarding?r=1", data={"short": "1", "goal": "cefr", "target_level": "B2", "daily_minutes": "10", "source": "telegram"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/placement")
    p = profile(app, "ali@x.uz")
    assert p.interests == ["anime"] and p.region == "samarkand" and p.goal == "cefr" and p.source == "telegram" and p.completed_at


def test_short_onboarding_without_consent_never_stores_source(app):
    c = app.test_client()
    c.post("/register", data={"name": "Vali", "email": "vali@x.uz", "password": GOOD_PW, "interests": ["music"]})
    c.post("/onboarding?r=1", data={"short": "1", "goal": "cefr", "source": "telegram"})
    assert profile(app, "vali@x.uz").source is None


def test_onboarding_requires_login(app):
    c = app.test_client()
    assert c.get("/onboarding").status_code == 302 and "/login" in c.get("/onboarding").headers["Location"]


def test_save_with_consent_keeps_statistics(app):
    c = app.test_client(); login(c)
    r = c.post("/onboarding", data={"goal": "cefr", "target_level": "B2", "daily_minutes": "10", "interests": ["anime", "tech"],
                                    "age_range": "16-17", "region": "samarkand", "source": "telegram", "consent": "1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/placement")
    p = profile(app)
    assert (p.goal, p.target_level, p.daily_minutes, p.region, p.source) == ("cefr", "B2", 10, "samarkand", "telegram")
    assert p.consent_at and p.completed_at


def test_without_consent_statistics_are_not_stored(app):
    c = app.test_client(); login(c)
    c.post("/onboarding", data={"goal": "cefr", "age_range": "16-17", "region": "samarkand", "source": "telegram"})
    p = profile(app)
    assert p.goal == "cefr" and p.age_range is None and p.region is None and p.source is None and p.consent_at is None


def test_invalid_values_rejected(app):
    c = app.test_client(); login(c)
    assert c.post("/onboarding", data={"interests": ["football", "tech", "music", "travel", "business", "anime", "movies"]}).status_code == 400
    assert c.post("/onboarding", data={"exam_date": "2001-01-01"}).status_code == 400
    c.post("/onboarding", data={"goal": "hack", "target_level": "Z9", "daily_minutes": "999"})
    p = profile(app)
    assert p.goal is None and p.target_level is None and p.daily_minutes is None


def test_skip_and_edit_later(app):
    c = app.test_client(); login(c)
    assert c.post("/onboarding", data={"action": "skip"}).status_code == 302
    p = profile(app); assert p.skipped_at and not p.completed_at
    c.post("/onboarding", data={"goal": "university"})
    p = profile(app); assert p.goal == "university" and p.completed_at and not p.skipped_at


def test_admin_stats_only_for_admin(app):
    c = app.test_client(); login(c)
    assert c.get("/admin/onboarding").status_code == 403
    a = app.test_client(); login(a, "admin@x.uz")
    assert a.get("/admin/onboarding").status_code == 200


def test_deleting_account_deletes_profile(app):
    c = app.test_client(); login(c)
    c.post("/onboarding", data={"goal": "cefr", "consent": "1", "region": "andijan"})
    assert profile(app)
    c.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "password123"})
    with app.app_context():
        assert UserProfile.query.count() == 0


def test_privacy_page_public_and_branding(app):
    c = app.test_client()
    assert c.get("/maxfiylik").status_code == 200
    home = c.get("/").get_data(as_text=True)
    assert "LEVI" in home and "brand/levi-favicon.svg" in home and "CEFR.AI" not in home
