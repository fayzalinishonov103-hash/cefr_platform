"""Tests for progress/streak, account settings, admin statistics, error pages and mobile navigation."""
import io
from datetime import date, datetime, timedelta, timezone

import pytest

import progress
from app import create_app
from extensions import db
from models import User, Test as TestModel, Part, QuestionGroup, Question, Attempt, SkillResult, VocabWord, HintLog


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}", "ADMIN_EMAILS": set()})
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin); u.set_password("password123"); db.session.add(u)
        db.session.commit()
    return app.test_client()


def login(c, email="stud@x.uz", pw="password123"):
    return c.post("/login", data={"email": email, "password": pw})


def test_streaks_logic():
    d = date(2026, 11, 14)
    days = {d - timedelta(days=i): 1 for i in (0, 1, 2, 5, 6, 7, 8)}        # 3-day run now, 4-day run before
    assert progress.streaks(days, d) == (3, 4)
    assert progress.streaks({d - timedelta(days=1): 1}, d)[0] == 1            # yesterday still keeps it alive
    assert progress.streaks({d - timedelta(days=2): 1}, d)[0] == 0            # a gap breaks it
    assert progress.streaks({}, d) == (0, 0)


def test_uzbek_day_boundary():
    # 20:00 UTC is already the next calendar day in Uzbekistan (UTC+5)
    assert progress.local_date(datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)) == date(2026, 11, 14)


def test_dashboard_progress_and_recommendation(client):
    login(client)
    page = client.get("/dashboard"); assert page.status_code == 200 and b"BUGUNGI REJA" in page.data
    assert "Birinchi mashq" in page.get_data(as_text=True)
    with client.application.app_context():
        u = User.query.filter_by(email="stud@x.uz").first()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for skill, score in (("writing", 60.0), ("speaking", 30.0)):
            db.session.add(SkillResult(user_id=u.id, skill=skill, scaled_score=score, cefr_level="B1", feedback={"title": "t"}, created_at=now))
        db.session.add(VocabWord(user_id=u.id, word="reliable", next_review=now - timedelta(days=1)))
        db.session.commit()
        p = progress.dashboard_progress(u)
        assert p["streak"] == 1 and p["today"] == 2 and p["vocab_due"] == 1
        assert p["next"]["endpoint"] == "reading.tests"                       # first skill never tried
    assert b"1 TA SO" in client.get("/dashboard").data


def test_settings_password_and_delete(client):
    login(client)
    assert client.get("/settings").status_code == 200
    client.post("/settings", data={"action": "name", "name": "New Name"})
    client.post("/settings", data={"action": "password", "old": "WRONG", "new": "newpassword1", "again": "newpassword1"})
    client.post("/logout")
    assert login(client, pw="password123").status_code == 302                # wrong "old" password: nothing changed
    client.post("/settings", data={"action": "password", "old": "password123", "new": "newpassword1", "again": "newpassword1"})
    client.post("/logout")
    assert login(client, pw="password123").status_code == 401
    assert login(client, pw="newpassword1").status_code == 302
    with client.application.app_context():
        u = User.query.filter_by(email="stud@x.uz").first()
        assert u.name == "New Name"
        t = TestModel(title="x", skill="reading"); db.session.add(t); db.session.flush()
        at = Attempt(user_id=u.id, test_id=t.id); db.session.add(at); db.session.flush()
        db.session.add_all([HintLog(attempt_id=at.id, part_number=1, hint="h"), VocabWord(user_id=u.id, word="w"),
                            SkillResult(user_id=u.id, skill="writing", feedback={})])
        db.session.commit()
    client.post("/settings", data={"action": "delete", "confirm": "nope"})
    with client.application.app_context():
        assert User.query.filter_by(email="stud@x.uz").count() == 1          # wrong confirmation word: nothing deleted
    client.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "WRONG"})
    with client.application.app_context():
        assert User.query.filter_by(email="stud@x.uz").count() == 1          # wrong password: nothing deleted
    r = client.post("/settings", data={"action": "delete", "confirm": "ochirish", "password": "newpassword1"})
    assert r.status_code == 302
    with client.application.app_context():
        assert User.query.filter_by(email="stud@x.uz").count() == 0
        assert Attempt.query.count() == SkillResult.query.count() == VocabWord.query.count() == HintLog.query.count() == 0
    assert login(client).status_code == 401


def test_last_admin_cannot_delete_self(client):
    login(client, "admin@x.uz")
    client.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "password123"})
    with client.application.app_context():
        assert User.query.filter_by(email="admin@x.uz").count() == 1


def make_quiz(app, n_attempts):
    with app.app_context():
        t = TestModel(title="Quiz", skill="reading", is_active=True); db.session.add(t); db.session.flush()
        p = Part(test_id=t.id, number=1, title="P", passage="x"); db.session.add(p); db.session.flush()
        g = QuestionGroup(part_id=p.id, qtype="mcq", instruction="i"); db.session.add(g); db.session.flush()
        for n, key in ((1, "a"), (2, "b")):
            db.session.add(Question(group_id=g.id, number=n, text=f"Q{n}", options=[["a", "A"], ["b", "B"]], answer=key, cefr_level="B1"))
        u = User.query.filter_by(email="stud@x.uz").first()
        for _ in range(n_attempts):       # everybody answers q1 right and q2 wrong with "a"
            db.session.add(Attempt(user_id=u.id, test_id=t.id, finished_at=datetime.now(timezone.utc),
                                   answers={"q1": "a", "q2": "a"}, raw_score=1, max_score=2, scaled_score=37.5, cefr_level="B1"))
        db.session.commit()
        return t.id


def test_admin_stats_and_users(client):
    tid = make_quiz(client.application, 6)
    login(client, "admin@x.uz")
    page = client.get(f"/admin/tests/{tid}/stats"); html = page.get_data(as_text=True)
    assert page.status_code == 200 and "Juda qiyin" in html and "Juda oson" in html and "100%" in html
    assert client.get("/admin/users").status_code == 200
    assert b"stud" in client.get("/admin/users?q=STUD").data and b"Hech kim" in client.get("/admin/users?q=zzz").data
    client.post("/logout"); login(client)
    assert client.get(f"/admin/tests/{tid}/stats").status_code == 403 and client.get("/admin/users").status_code == 403


def test_few_attempts_not_flagged(client):
    tid = make_quiz(client.application, 2)
    login(client, "admin@x.uz")
    assert "Juda qiyin" not in client.get(f"/admin/tests/{tid}/stats").get_data(as_text=True)


def test_errors_health_and_mobile_nav(client):
    assert client.get("/health").get_json() == {"ok": True}
    r = client.get("/no-such-page"); assert r.status_code == 404 and "Sahifa topilmadi" in r.get_data(as_text=True)
    home = client.get("/").get_data(as_text=True)
    assert 'aria-label="Mobil menyu"' in home and "LISTENING" in home.split('aria-label="Mobil menyu"')[1]
    login(client)
    assert 'aria-label="Sozlamalar"' in client.get("/").get_data(as_text=True)      # settings is an icon button now
