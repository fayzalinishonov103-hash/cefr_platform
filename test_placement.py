"""Placement test, practice hub and mobile bottom navigation.  Run:  python -m pytest -q test_placement.py"""
import pytest

import placement
from app import create_app
from extensions import db
from models import User, SkillResult
from placement_data import QUESTIONS


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for email in ("a@x.uz", "b@x.uz"):
            u = User(name=email.split("@")[0], email=email); u.set_password("password123"); db.session.add(u)
        db.session.commit()
    return app


def login(c, email="a@x.uz"):
    return c.post("/login", data={"email": email, "password": "password123"})


def answers(right_levels):
    """Form data: correct answer for questions of `right_levels`, a wrong one for all others."""
    out = {}
    for n, q in enumerate(QUESTIONS, 1):
        out[f"p{n}"] = str(q["answer"] if q["level"] in right_levels else (q["answer"] + 1) % len(q["options"]))
    return out


def test_estimate_level_chain():
    assert placement.estimate_level({"A1": 5, "A2": 3, "B1": 2}) == "A2"
    assert placement.estimate_level({"A1": 2}) == "A0"
    assert placement.estimate_level({"A1": 5, "A2": 1, "B1": 5}) == "A1"      # a broken chain stops the climb
    assert placement.estimate_level({lv: 5 for lv in placement.LEVELS}) == "C1"


def test_grade_ignores_bad_input():
    g = placement.grade({"p1": "abc", "p2": "99", "p3": "-1", "p4": ""})
    assert g["answered"] == 0 and g["skipped"] == 1 and g["level"] == "A0" and g["total"] == 25


def test_full_flow_and_levels(app):
    c = app.test_client(); login(c)
    page = c.get("/placement/test")
    assert page.status_code == 200 and page.get_data(as_text=True).count("<fieldset") == 25
    r = c.post("/placement/submit", data=answers(set(placement.LEVELS)))
    assert r.status_code == 302
    assert "Yuqori daraja" in c.get(r.headers["Location"]).get_data(as_text=True)
    r = c.post("/placement/submit", data=answers({"A1", "A2"}))
    assert "Elementar" in c.get(r.headers["Location"]).get_data(as_text=True)
    r = c.post("/placement/submit", data=answers(set()))
    assert c.get(r.headers["Location"]).status_code == 200
    with app.app_context():
        assert [x.cefr_level for x in SkillResult.query.filter_by(skill="placement").order_by(SkillResult.id)] == ["C1", "A2", "A0"]


def test_empty_submit_saves_nothing(app):
    c = app.test_client(); login(c)
    r = c.post("/placement/submit", data={})
    assert r.status_code == 302 and r.headers["Location"].endswith("/placement/test")
    with app.app_context():
        assert SkillResult.query.filter_by(skill="placement").count() == 0


def test_daily_limit(app):
    c = app.test_client(); login(c)
    for _ in range(placement.PER_DAY):
        assert c.post("/placement/submit", data=answers({"A1"})).headers["Location"].find("/result/") > 0
    assert c.post("/placement/submit", data=answers({"A1"})).headers["Location"].endswith("/placement")
    with app.app_context():
        assert SkillResult.query.filter_by(skill="placement").count() == placement.PER_DAY


def test_result_is_private(app):
    a, b = app.test_client(), app.test_client()
    login(a); login(b, "b@x.uz")
    loc = a.post("/placement/submit", data=answers({"A1"})).headers["Location"]
    assert a.get(loc).status_code == 200 and b.get(loc).status_code == 404


def test_guest_access(app):
    c = app.test_client()
    assert c.get("/placement").status_code == 200
    assert c.get("/placement/test").status_code == 302
    assert c.post("/placement/submit", data=answers({"A1"})).status_code == 302


def test_new_user_lands_on_placement_and_dashboard_banner(app):
    c = app.test_client()
    r = c.post("/register", data={"name": "Ali", "email": "new@x.uz", "password": "tulip-garden-42x"})
    assert r.status_code == 302 and (r.headers["Location"].endswith("/placement") or r.headers["Location"].endswith("/onboarding?r=1"))
    assert "Darajangizni biling" in c.get("/dashboard").get_data(as_text=True)
    c.post("/placement/submit", data=answers({"A1"}))
    assert "Daraja testi natijasi" in c.get("/dashboard").get_data(as_text=True)


def test_practice_hub_and_bottom_nav(app):
    c = app.test_client()
    assert c.get("/practice").status_code == 200
    home = c.get("/").get_data(as_text=True)
    assert 'aria-label="Pastki menyu"' in home and 'aria-label="Mobil menyu"' in home
    login(c)
    assert 'aria-current="page"' in c.get("/practice").get_data(as_text=True)
