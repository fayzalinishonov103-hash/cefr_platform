"""Speaking + login throttle tests (AI calls are mocked).  Run:  python -m pytest -q test_speaking.py"""
import io
import pytest

import speaking
import auth
from app import create_app
from extensions import db
from models import User, SpeakingPrompt, SkillResult

GOOD = ('{"on_topic": true, "criteria": {"task_achievement": {"level": "B2", "comment": "ok"},'
        '"fluency": {"level": "B1", "comment": "ok"}, "vocabulary": {"level": "B2", "comment": "ok"},'
        '"grammar": {"level": "B1", "comment": "ok"}}, "strengths": ["a"], "next_steps": ["b"],'
        '"errors": [{"original": "I goed", "correction": "I went", "explanation": "x"},'
        '{"original": "NOT IN TEXT", "correction": "y", "explanation": "z"}]}')
TRANSCRIPT = "Yesterday I goed to the park with my friends and we played football for two hours."


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SPEAKING_PER_DAY": 2,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}", "ADMIN_EMAILS": set()})
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin); u.set_password("password123"); db.session.add(u)
        db.session.add(SpeakingPrompt(part=1, title="T1", prompt="Talk about your day please.", think_seconds=5, speak_seconds=30))
        db.session.commit()
    return app.test_client()


def login(c, email="stud@x.uz"):
    return c.post("/login", data={"email": email, "password": "password123"})


def audio(n=5000):
    return {"audio": (io.BytesIO(b"\x1aE\xdf\xa3" + b"0" * n), "answer.webm", "audio/webm"), "seconds": "20"}


def test_speaking_flow(client, monkeypatch):
    monkeypatch.setattr(speaking, "transcribe", lambda data, name: TRANSCRIPT)
    monkeypatch.setattr(speaking, "ask_grader", lambda s, u: GOOD)
    login(client)
    assert b"T1" in client.get("/speaking").data
    page = client.get("/speaking/1"); assert page.status_code == 200 and b"MediaRecorder" in page.data
    assert client.post("/speaking/1/submit", data={}, content_type="multipart/form-data").status_code == 400
    r = client.post("/speaking/1/submit", data=audio(), content_type="multipart/form-data")
    assert r.status_code == 200, r.data
    res = client.get(r.get_json()["redirect"])
    assert res.status_code == 200 and b"SPEAKING NATIJASI" in res.data and b"I goed" in res.data
    assert b"NOT IN TEXT" not in res.data                       # invented error quotes are dropped
    assert b"SPEAKING NATIJALARI" in client.get("/dashboard").data
    p = client.get("/profile"); assert p.status_code == 200 and b"SPEAKING" in p.data
    with client.application.app_context():
        row = SkillResult.query.filter_by(skill="speaking").one()
        rid = row.id
        assert row.cefr_level in {"B1", "B2"} and row.feedback["text"] == TRANSCRIPT
    client.post("/logout"); login(client, "admin@x.uz")          # another user must not read it
    assert client.get(f"/speaking/result/{rid}").status_code == 404


def test_limits_and_failures(client, monkeypatch):
    login(client)
    monkeypatch.setattr(speaking, "transcribe", lambda d, n: "too short")
    assert client.post("/speaking/1/submit", data=audio(), content_type="multipart/form-data").status_code == 422
    monkeypatch.setattr(speaking, "transcribe", lambda d, n: TRANSCRIPT)
    monkeypatch.setattr(speaking, "ask_grader", lambda s, u: "not json")
    assert client.post("/speaking/1/submit", data=audio(), content_type="multipart/form-data").status_code == 502
    monkeypatch.setattr(speaking, "ask_grader", lambda s, u: GOOD)
    for _ in range(2):                                           # failed attempts above did not use the daily limit
        assert client.post("/speaking/1/submit", data=audio(), content_type="multipart/form-data").status_code == 200
    assert client.post("/speaking/1/submit", data=audio(), content_type="multipart/form-data").status_code == 429
    assert client.post("/speaking/1/submit", data={"audio": (io.BytesIO(b"x"), "a.webm")}, content_type="multipart/form-data").status_code in (400, 429)


def test_admin_speaking_and_isolation(client, monkeypatch):
    login(client, "admin@x.uz")
    assert client.get("/admin/speaking").status_code == 200
    ok = {"part": "2", "title": "New", "prompt": "Describe your best friend.", "think_seconds": "20", "speak_seconds": "60"}
    client.post("/admin/speaking/new", data=ok)
    client.post("/admin/speaking/new", data={**ok, "part": "9"})                      # invalid part is rejected
    with client.application.app_context():
        assert SpeakingPrompt.query.count() == 2
    client.post("/logout"); login(client)
    assert client.get("/admin/speaking").status_code == 403


def test_login_throttle(client):
    for _ in range(auth.LOGIN_MAX_FAILS):
        assert client.post("/login", data={"email": "stud@x.uz", "password": "wrong"}).status_code == 401
    assert client.post("/login", data={"email": "stud@x.uz", "password": "wrong"}).status_code == 429
    assert client.post("/login", data={"email": "stud@x.uz", "password": "password123"}).status_code == 429   # locked for this key
    assert client.post("/login", data={"email": "admin@x.uz", "password": "password123"}).status_code == 302   # others unaffected


def test_examiner_respond_fallback(client, monkeypatch):
    login(client)
    monkeypatch.setattr(speaking, "transcribe", lambda d, n: "I really enjoy reading books and exploring new technologies in my leisure time.")
    monkeypatch.setattr(speaking, "ask_grader", lambda s, u: "This is non-json plain text response from AI")
    
    r = client.post("/speaking/examiner/respond", data={"audio": (io.BytesIO(b"\x1aE\xdf\xa3" + b"0" * 5000), "turn.webm", "audio/webm"),
                                                        "last_question": "Tell me about your hobbies."},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert "Thank you" in data["examiner_reply"]
    assert "Javobingizni misollar bilan boyiting" in data["fluency_tip"]

