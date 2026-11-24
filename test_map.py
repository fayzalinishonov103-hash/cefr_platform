"""Map labelling (a picture in a part + 'map' questions).  Run:  python -m pytest -q test_map.py"""
import io
import os
import sqlite3
import zlib
import struct

import pytest
from sqlalchemy import text

import admin
from app import create_app
from extensions import db
from models import User, Test as TestModel, Part, Attempt


def png_bytes():
    """A real 8x8 PNG, built by hand (no imaging library needed)."""
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    size = 48                                                    # a small gradient: a bit like a real map, and big enough to be believable
    raw = b"".join(b"\x00" + b"".join(bytes(((x * 5) % 256, (y * 5) % 256, (x * y) % 256)) for x in range(size)) for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(admin, "IMAGE_DIR", str(tmp_path / "maps"))
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for key, adm in (("admin", True), ("stud", False)):
            u = User(name=key, email=f"{key}@x.uz", is_admin=adm); u.set_password("password123"); db.session.add(u)
        db.session.commit()
    app.maps_dir = tmp_path / "maps"
    return app


def sign_in(app, key):
    c = app.test_client()
    assert c.post("/login", data={"email": f"{key}@x.uz", "password": "password123"}).status_code == 302
    return c


def upload(c, data, name="map.png"):
    return c.post("/admin/image", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


def payload(image_url, skill="listening"):
    letters = [[c, c] for c in "ABCDEFGH"]
    return {"skill": skill, "title": "Map test", "duration_min": 20, "is_active": True, "parts": [
        {"title": "Part 1", "passage": "Transcript: the library is next to the park.", "audio_url": "/static/audio/x.mp3" if skill == "listening" else "",
         "image_url": image_url, "groups": [{"qtype": "map", "instruction": "Choose A-H.", "questions": [
             {"number": 1, "text": "the library", "options": letters, "answer": "c", "cefr_level": "A2"},
             {"number": 2, "text": "the cafe", "options": letters, "answer": "F", "cefr_level": "B1"}]}]}]}


def test_upload_accepts_real_images_only(app):
    admin_c = sign_in(app, "admin")
    r = upload(admin_c, png_bytes())
    assert r.status_code == 200 and r.get_json()["url"].startswith("/static/maps/") and r.get_json()["url"].endswith(".png")
    assert len(os.listdir(app.maps_dir)) == 1
    assert upload(admin_c, b"\xff\xd8\xff" + b"0" * 200, "x.jpg").get_json()["url"].endswith(".jpg")
    assert upload(admin_c, b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 200, "x.webp").get_json()["url"].endswith(".webp")
    evil = [(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "map.svg"),
            (b"<html><script>alert(1)</script></html>", "map.png"),                # a .png NAME does not make it a png
            (b"GIF89a" + b"0" * 200, "map.gif"), (b"", "empty.png"), (b"\x89PNG\r\n\x1a\n", "tiny.png"),
            (b"\x89PNG\r\n\x1a\n" + b"<script>alert(1)</script>" * 10, "no-header.png")]
    for data, name in evil:
        assert upload(admin_c, data, name).status_code == 400, name
    assert upload(admin_c, png_bytes() + b"0" * (admin.MAX_IMAGE_BYTES + 1)).status_code == 413
    assert admin_c.post("/admin/image", data={}, content_type="multipart/form-data").status_code == 400
    assert len(os.listdir(app.maps_dir)) == 3                                         # nothing bad was written to disk


def test_only_admin_can_upload(app):
    assert upload(app.test_client(), png_bytes()).status_code in (302, 401, 403)
    assert upload(sign_in(app, "stud"), png_bytes()).status_code == 403


def test_image_url_validation(app):
    admin_c = sign_in(app, "admin")
    for bad in ("https://evil.example/m.png", "javascript:alert(1)", "/static/audio/a.mp3", "/static/maps/" + "x" * 300):
        r = admin_c.post("/admin/tests/save", json=payload(bad))
        assert r.status_code == 400 and any("rasm havolasi" in e for e in r.get_json()["errors"]), bad
    assert admin_c.post("/admin/tests/save", json=payload("")).status_code == 200            # the picture is optional


def test_map_test_end_to_end(app):
    admin_c = sign_in(app, "admin")
    url = upload(admin_c, png_bytes()).get_json()["url"]
    saved = admin_c.post("/admin/tests/save", json=payload(url)); assert saved.status_code == 200, saved.data
    with app.app_context():
        part = Part.query.one(); tid = part.test_id
        assert part.image_url == url and part.groups[0].qtype == "map" and part.groups[0].questions[1].answer == "F"

    editor = admin_c.get(f"/admin/tests/{tid}/edit").get_data(as_text=True)               # the editor gets the picture back
    assert url in editor and '"map"' in editor

    student = sign_in(app, "stud")
    loc = student.post(f"/listening/{tid}/start").headers["Location"]
    page = student.get(loc).get_data(as_text=True)
    assert f'src="{url}"' in page                                                          # the map is shown in the part
    assert page.count('<option value="') >= 2 * 8                                           # a letter A-H dropdown per question
    assert ">A</option>" in page and ">A. A</option>" not in page                           # shows "A", not "A. A"
    assert "the library" in page
    assert "Transcript: the library" not in page                                            # transcript stays hidden during the test

    res = student.post(loc + "/submit", data={"q1": "C", "q2": "A"})
    result = student.get(res.headers["Location"]).get_data(as_text=True)
    assert "XARITA / RASMLAR" in result and url in result
    with app.app_context():
        a = Attempt.query.one()
        assert a.raw_score == 1 and a.max_score == 2                                         # "C" matches key "c"; "A" is wrong


def test_picture_also_works_in_reading(app):
    admin_c = sign_in(app, "admin")
    url = upload(admin_c, png_bytes()).get_json()["url"]
    assert admin_c.post("/admin/tests/save", json=payload(url, skill="reading")).status_code == 200
    with app.app_context():
        tid = TestModel.query.one().id
    student = sign_in(app, "stud")
    loc = student.post(f"/reading/{tid}/start").headers["Location"]
    assert f'src="{url}"' in student.get(loc).get_data(as_text=True)


def test_map_question_shows_its_map_in_mistakes_practice(app):
    admin_c = sign_in(app, "admin")
    url = upload(admin_c, png_bytes()).get_json()["url"]
    admin_c.post("/admin/tests/save", json=payload(url))
    with app.app_context():
        tid = TestModel.query.one().id
    student = sign_in(app, "stud")
    loc = student.post(f"/listening/{tid}/start").headers["Location"]
    student.post(loc + "/submit", data={"q1": "A", "q2": "A"})                              # both wrong
    page = student.get("/mistakes/practice?skill=listening")
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and url in html and "the library" in html


def test_old_database_gets_the_column(tmp_path):
    """A database made before maps existed (no part.image_url) is upgraded on start, and keeps its data."""
    path = tmp_path / "old.db"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})
    with app.app_context():
        t = TestModel(title="old", skill="listening"); db.session.add(t); db.session.flush()
        db.session.add(Part(test_id=t.id, number=1, title="p", passage="x", audio_url="/static/audio/a.mp3")); db.session.commit()
        db.session.execute(text('ALTER TABLE "part" DROP COLUMN image_url')); db.session.commit()      # make it "old"
    con = sqlite3.connect(path); assert "image_url" not in [r[1] for r in con.execute("PRAGMA table_info(part)")]; con.close()
    app2 = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})              # starts, migrates
    with app2.app_context():
        part = Part.query.one()
        assert part.title == "p" and part.audio_url == "/static/audio/a.mp3" and part.image_url is None
    create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})                       # running it again is harmless
