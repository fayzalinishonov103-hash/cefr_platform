"""Mock exam tests.  Run:  python -m pytest -q test_exam.py"""
from datetime import timedelta

import pytest

import exam as exam_mod
import security
from app import create_app
from extensions import db
from models import User, Test as TestModel, Attempt, SkillResult, ExamSession


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for key in ("a", "b"):
            u = User(name=key, email=f"{key}@x.uz"); u.set_password("password123"); db.session.add(u)
        for skill in ("reading", "listening"):
            db.session.add(TestModel(title=f"{skill} test", skill=skill, is_active=True))
        db.session.commit()
    return app


def sign_in(app, key="a"):
    c = app.test_client()
    assert c.post("/login", data={"email": f"{key}@x.uz", "password": "password123"}).status_code == 302
    return c


def uid(key="a"):
    """User id; call inside an app context."""
    return User.query.filter_by(email=f"{key}@x.uz").first().id


def add_result(app, key, skill, score, when=None):
    """A finished Reading/Listening attempt or a Writing/Speaking result for user `key`."""
    with app.app_context():
        user_id = uid(key)
        when = when or security.now()
        level = "B2" if score >= 51 else "B1"
        if skill in ("reading", "listening"):
            t = TestModel.query.filter_by(skill=skill).first()
            db.session.add(Attempt(user_id=user_id, test_id=t.id, finished_at=when, scaled_score=score, cefr_level=level,
                                   raw_score=1, max_score=1, answers={}))
        else:
            db.session.add(SkillResult(user_id=user_id, skill=skill, scaled_score=score, cefr_level=level,
                                       feedback={"title": "task"}, created_at=when))
        db.session.commit()


def test_overall_needs_all_four_and_averages():
    r = {k: {"score": s} for k, s in (("reading", 60), ("listening", 40), ("writing", 50))}
    assert exam_mod.overall(r) == (None, None)
    r["speaking"] = {"score": 50}
    assert exam_mod.overall(r) == (50.0, "B1")          # 51 would be B2


def test_full_exam_flow(app):
    c = sign_in(app)
    assert "IMTIHONNI BOSHLASH" in c.get("/exam").get_data(as_text=True)
    r = c.post("/exam/start"); assert r.status_code == 302
    page = c.get(r.headers["Location"]); html = page.get_data(as_text=True)
    assert page.status_code == 200 and "0 / 4" in html
    assert "Toʻliq imtihon davom etmoqda" in c.get("/reading").get_data(as_text=True)          # banner on other pages
    c.post("/exam/start")                                                                         # no second open exam
    with app.app_context():
        assert ExamSession.query.count() == 1

    for skill, score in (("reading", 60.0), ("listening", 50.0), ("writing", 40.0)):
        add_result(app, "a", skill, score)
    assert "3 / 4" in c.get(r.headers["Location"]).get_data(as_text=True)
    add_result(app, "a", "speaking", 50.0)
    done = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "IMTIHON NATIJASI" in done and "50.0 / 75" in done and "B1" in done
    with app.app_context():
        e = ExamSession.query.one()
        assert e.finished_at and e.overall_score == 50.0 and e.overall_level == "B1" and set(e.results) == {"reading", "listening", "writing", "speaking"}
    add_result(app, "a", "reading", 75.0)                                                          # later activity must not rewrite history
    assert "50.0 / 75" in c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Toʻliq imtihon davom etmoqda" not in c.get("/reading").get_data(as_text=True)         # banner gone
    assert "OLDINGI IMTIHONLAR" in c.get("/exam").get_data(as_text=True)


def test_results_before_start_do_not_count(app):
    add_result(app, "a", "reading", 70.0, when=security.now() - timedelta(hours=2))
    c = sign_in(app)
    loc = c.post("/exam/start").headers["Location"]
    assert "0 / 4" in c.get(loc).get_data(as_text=True)


def test_latest_result_per_skill_counts(app):
    c = sign_in(app)
    loc = c.post("/exam/start").headers["Location"]
    add_result(app, "a", "reading", 30.0, when=security.now() + timedelta(seconds=1))
    add_result(app, "a", "reading", 70.0, when=security.now() + timedelta(seconds=2))
    with app.app_context():
        e = ExamSession.query.one()
        with app.test_request_context():                  # stage_results builds URLs
            assert exam_mod.stage_results(e.user_id, e.started_at)["reading"]["score"] == 70.0


def test_ownership_cancel_and_limits(app):
    a, b = sign_in(app, "a"), sign_in(app, "b")
    loc = a.post("/exam/start").headers["Location"]
    assert b.get(loc).status_code == 404 and b.post(loc + "/cancel").status_code == 404
    assert a.post(loc + "/cancel").status_code == 302
    assert a.get(loc).status_code == 404                                                           # cancelled exams are gone
    for _ in range(exam_mod.STARTS_PER_DAY - 1):                                                    # 1 already used above
        a.post("/exam/start")
        with app.app_context():
            ExamSession.query.filter_by(finished_at=None, cancelled=False).update({"cancelled": True}); db.session.commit()
    a.post("/exam/start")
    with app.app_context():
        assert ExamSession.query.filter_by(user_id=uid("a")).count() == exam_mod.STARTS_PER_DAY


def test_anonymous_is_redirected(app):
    c = app.test_client()
    assert c.get("/exam").status_code == 302 and c.post("/exam/start").status_code == 302
