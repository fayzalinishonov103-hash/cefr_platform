"""End-to-end smoke test for the Listening flow.  Run:  python -m pytest -q test_listening.py"""
import io
import subprocess
import pytest

from app import create_app
from extensions import db
from models import User, Test as TestModel


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}", "ADMIN_EMAILS": set()})
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin)
            u.set_password("password123")
            db.session.add(u)
        db.session.commit()
    return app.test_client()


def login(c, email):
    c.post("/login", data={"email": email, "password": "password123"})


def tone_mp3(path):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(path)], check=True)


def payload(audio):
    q = lambda n, a: {"number": n, "text": f"Question {n}?", "answer": a, "cefr_level": "B1",
                      "options": [["a", "One"], ["b", "Two"]]}
    return {"skill": "listening", "title": "L1", "duration_min": 20, "is_active": True, "parts": [
        {"title": "P1", "passage": "Transcript one.", "audio_url": audio,
         "groups": [{"qtype": "mcq", "instruction": "Choose.", "questions": [q(1, "a"), q(2, "b")]}]}]}


def test_full_flow(client, tmp_path):
    mp3 = tmp_path / "a.mp3"; tone_mp3(mp3)
    login(client, "admin@x.uz")
    up = client.post("/admin/audio", data={"file": (io.BytesIO(mp3.read_bytes()), "a.mp3")}, content_type="multipart/form-data")
    assert up.status_code == 200, up.data
    url = up.get_json()["url"]
    assert client.post("/admin/audio", data={"file": (io.BytesIO(b"x"), "evil.html")}, content_type="multipart/form-data").status_code == 400
    assert client.post("/admin/tests/save", json=payload("")).status_code == 400          # audio required
    assert client.post("/admin/tests/save", json=payload("javascript:alert(1)")).status_code == 400
    assert client.post("/admin/tests/save", json=payload(url)).status_code == 200
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/tests/new?skill=listening").status_code == 200
    client.post("/logout")

    login(client, "stud@x.uz")
    assert b"L1" in client.get("/listening").data
    with client.application.app_context():
        tid = TestModel.query.filter_by(skill="listening").first().id
    r = client.post(f"/listening/{tid}/start"); assert r.status_code == 302
    page = client.get(r.headers["Location"])
    assert page.status_code == 200 and url.encode() in page.data and b"data-audio-play" in page.data
    assert b"Transcript one" not in page.data                      # transcript must not leak during the test
    assert b'data-hint-box="' not in page.data                        # no AI hint box in Listening
    attempt_url = r.headers["Location"]
    hint = client.post(attempt_url + "/hint", json={"part": 1})
    assert hint.status_code == 400
    sub = client.post(attempt_url + "/submit", data={"q1": "a", "q2": "a"})
    res = client.get(sub.headers["Location"])
    assert res.status_code == 200 and b"LISTENING NATIJASI" in res.data and b"Transcript one" in res.data
    assert client.get("/profile").status_code == 200 and b"LISTENING" in client.get("/profile").data
    assert client.get("/dashboard").status_code == 200
    # Listening must not count as Reading in the profile
    from skills import skills_profile
    with client.application.app_context():
        u = User.query.filter_by(email="stud@x.uz").first()
        p = skills_profile(u)
        assert p["counts"] == {"reading": 0, "listening": 1, "writing": 0, "speaking": 0}
        assert p["latest"]["listening"] == 37.5
