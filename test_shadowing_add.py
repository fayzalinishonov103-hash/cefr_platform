"""The "Shadowingga qo'shish" button on the public shadowing page.  Run:  python -m pytest -q test_shadowing_add.py"""
import pytest

from app import create_app
from extensions import db
from models import User, ShadowVideo


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin); u.set_password("password123"); db.session.add(u)
        db.session.commit()
    return app


def login(c, email):
    c.post("/login", data={"email": email, "password": "password123"})


def test_button_is_visible_to_admins_only(app):
    a, s, anon = app.test_client(), app.test_client(), app.test_client()
    login(a, "admin@x.uz"); login(s, "stud@x.uz")
    assert "SHADOWINGGA QOʻSHISH" in a.get("/shadowing").get_data(as_text=True)
    assert "SHADOWINGGA QOʻSHISH" not in s.get("/shadowing").get_data(as_text=True)
    assert "SHADOWINGGA QOʻSHISH" not in anon.get("/shadowing").get_data(as_text=True)


def test_admin_adds_video_and_returns_to_the_shadowing_page(app):
    a = app.test_client(); login(a, "admin@x.uz")
    r = a.post("/admin/shadowing/new", data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "Demo talk",
                                             "kind": "talk", "level": "B2", "back": "list"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/shadowing")
    with app.app_context():
        assert ShadowVideo.query.filter_by(youtube_id="dQw4w9WgXcQ").count() == 1


def test_students_cannot_add_videos(app):
    s = app.test_client(); login(s, "stud@x.uz")
    r = s.post("/admin/shadowing/new", data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "x", "kind": "talk", "level": "B2"})
    assert r.status_code in (302, 403)
    with app.app_context():
        assert ShadowVideo.query.count() == 0
