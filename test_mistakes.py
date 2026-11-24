"""Mistakes notebook.  Run:  python -m pytest -q test_mistakes.py"""
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from extensions import db
from models import (User, Test as TestModel, Part, QuestionGroup, Question, Attempt, MistakeFixed, ExamSession)

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for key in ("a", "b"):
            u = User(name=key, email=f"{key}@x.uz"); u.set_password("password123"); db.session.add(u)
        t = TestModel(title="Reading T", skill="reading", is_active=True); db.session.add(t); db.session.flush()
        p = Part(test_id=t.id, number=1, title="P1", passage="First paragraph.\n\nSecond paragraph."); db.session.add(p); db.session.flush()
        g1 = QuestionGroup(part_id=p.id, qtype="mcq", instruction="Choose.", order=0)
        g2 = QuestionGroup(part_id=p.id, qtype="gap_fill", instruction="Fill.", order=1)
        db.session.add_all([g1, g2]); db.session.flush()
        db.session.add_all([
            Question(group_id=g1.id, number=1, text="Q one?", options=[["a", "A"], ["b", "B"]], answer="a", cefr_level="B1"),
            Question(group_id=g2.id, number=2, text="The ___ is red.", answer="boat|ship", cefr_level="B2"),
            Question(group_id=g1.id, number=3, text="Q three?", options=[["a", "A"], ["b", "B"]], answer="b", cefr_level="B1")])
        lt = TestModel(title="Listening T", skill="listening", is_active=True); db.session.add(lt); db.session.flush()
        lp = Part(test_id=lt.id, number=1, title="L1", passage="secret transcript", audio_url="/static/audio/x.mp3"); db.session.add(lp); db.session.flush()
        lg = QuestionGroup(part_id=lp.id, qtype="mcq", instruction="Choose.", order=0); db.session.add(lg); db.session.flush()
        db.session.add(Question(group_id=lg.id, number=1, text="L question?", options=[["a", "A"], ["b", "B"]], answer="b", cefr_level="A2"))
        db.session.commit()
    return app


def make_attempt(app, email, title, answers, when):
    with app.app_context():
        u = User.query.filter_by(email=email).one()
        t = TestModel.query.filter_by(title=title).one()
        a = Attempt(user_id=u.id, test_id=t.id, finished_at=when, answers=answers, raw_score=0, max_score=1,
                    scaled_score=10, cefr_level="A2")
        db.session.add(a); db.session.commit()
        return a.id


def login(c, email="a@x.uz"):
    assert c.post("/login", data={"email": email, "password": "password123"}).status_code == 302
    return c


def qid(app, number, title="Reading T"):
    with app.app_context():
        return (Question.query.join(QuestionGroup).join(Part).join(TestModel)
                .filter(TestModel.title == title, Question.number == number).one().id)


def test_wrong_and_empty_questions_are_listed(app):
    make_attempt(app, "a@x.uz", "Reading T", {"q1": "a", "q2": "car"}, NOW - timedelta(hours=2))
    c = login(app.test_client())
    page = c.get("/mistakes").get_data(as_text=True)
    assert "2" in page and "The ___ is red." in page and "Q three?" in page and "Q one?" not in page
    assert "car" in page                                                  # the student's wrong answer is shown


def test_newest_attempt_decides(app):
    make_attempt(app, "a@x.uz", "Reading T", {"q1": "a", "q2": "car", "q3": "a"}, NOW - timedelta(hours=3))
    make_attempt(app, "a@x.uz", "Reading T", {"q1": "a", "q2": "boat", "q3": "b"}, NOW - timedelta(hours=1))
    page = login(app.test_client()).get("/mistakes").get_data(as_text=True)
    assert "Hozircha xato yo" in page                                    # everything was right the second time


def test_practice_fixes_only_correct_answers_and_keeps_key_hidden(app):
    make_attempt(app, "a@x.uz", "Reading T", {}, NOW - timedelta(hours=2))
    c = login(app.test_client())
    q2, q3, q1 = qid(app, 2), qid(app, 3), qid(app, 1)
    page = c.get("/mistakes/practice").get_data(as_text=True)
    assert f'name="m{q1}"' in page and f'name="m{q2}"' in page and "boat" not in page and "ship" not in page
    r = c.post("/mistakes/practice", data={f"m{q2}": "Ship", f"m{q3}": "a", f"m{q1}": ""})
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "1 / 3" in body
    with app.app_context():
        assert [m.question_id for m in MistakeFixed.query.all()] == [q2]
    left = c.get("/mistakes").get_data(as_text=True)
    assert "The ___ is red." not in left and "Q three?" in left          # fixed one is gone, the wrong one stays


def test_a_new_wrong_answer_brings_the_question_back(app):
    make_attempt(app, "a@x.uz", "Reading T", {"q1": "a", "q3": "b"}, NOW - timedelta(hours=2))
    c = login(app.test_client())
    q2 = qid(app, 2)
    c.post("/mistakes/practice", data={f"m{q2}": "boat"})
    assert "The ___ is red." not in c.get("/mistakes").get_data(as_text=True)
    make_attempt(app, "a@x.uz", "Reading T", {"q1": "a", "q2": "wrong", "q3": "b"}, NOW + timedelta(minutes=10))
    assert "The ___ is red." in c.get("/mistakes").get_data(as_text=True)


def test_skill_filter_and_listening_audio(app):
    make_attempt(app, "a@x.uz", "Listening T", {"q1": "a"}, NOW - timedelta(hours=1))
    c = login(app.test_client())
    assert "L question?" in c.get("/mistakes?skill=listening").get_data(as_text=True)
    assert "L question?" not in c.get("/mistakes?skill=reading").get_data(as_text=True)
    page = c.get("/mistakes/practice?skill=listening").get_data(as_text=True)
    assert "/static/audio/x.mp3" in page and "secret transcript" not in page


def test_cannot_answer_other_students_questions(app):
    make_attempt(app, "a@x.uz", "Reading T", {}, NOW - timedelta(hours=1))
    b = login(app.test_client(), "b@x.uz")                                # b has no mistakes at all
    r = b.post("/mistakes/practice", data={f"m{qid(app, 2)}": "boat"})
    assert r.status_code == 400
    with app.app_context():
        assert MistakeFixed.query.count() == 0


def test_bad_input_and_anonymous(app):
    anon = app.test_client()
    assert anon.get("/mistakes").status_code == 302 and anon.post("/mistakes/practice", data={}).status_code == 302
    c = login(app.test_client())
    assert c.post("/mistakes/practice", data={}).status_code == 400
    assert c.post("/mistakes/practice", data={"m99999": "x", "junk": "1"}).status_code == 400
    assert c.get("/mistakes?skill=%27%3Cscript%3E").status_code == 200


def test_account_deletion_removes_exam_and_notebook_rows(app):
    make_attempt(app, "a@x.uz", "Reading T", {}, NOW - timedelta(hours=1))
    c = login(app.test_client())
    c.post("/mistakes/practice", data={f"m{qid(app, 2)}": "boat"})
    with app.app_context():
        uid = User.query.filter_by(email="a@x.uz").one().id
        db.session.add(ExamSession(user_id=uid)); db.session.commit()
    c.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "password123"})
    with app.app_context():
        assert User.query.filter_by(email="a@x.uz").count() == 0
        assert ExamSession.query.count() == 0 and MistakeFixed.query.count() == 0
