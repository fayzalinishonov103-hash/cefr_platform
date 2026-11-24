"""Registration / login hardening.  Run:  python -m pytest -q test_auth_hardening.py"""
import pytest

from app import create_app
from extensions import db
from models import User

GOOD_PW = "Correct-Horse-9"


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        u = User(name="Stud", email="stud@x.uz"); u.set_password("password123"); db.session.add(u); db.session.commit()
    return app


def count(app, email):
    with app.app_context():
        return User.query.filter_by(email=email).count()


def test_disposable_email_rejected(app):
    r = app.test_client().post("/register", data={"name": "Bot", "email": "x@mailinator.com", "password": GOOD_PW})
    assert r.status_code == 400 and count(app, "x@mailinator.com") == 0


def test_honeypot_blocks_bots_and_creates_nothing(app):
    r = app.test_client().post("/register", data={"name": "Bot", "email": "bot@x.uz", "password": GOOD_PW, "website": "http://spam"})
    assert r.status_code == 400 and count(app, "bot@x.uz") == 0


def test_normal_registration_still_works(app):
    r = app.test_client().post("/register", data={"name": "Ali", "email": "ali@x.uz", "password": GOOD_PW})
    assert r.status_code == 302 and count(app, "ali@x.uz") == 1


def test_remember_me_checkbox(app):
    on, off, legacy = app.test_client(), app.test_client(), app.test_client()
    on.post("/login", data={"email": "stud@x.uz", "password": "password123", "remember_shown": "1", "remember": "1"})
    off.post("/login", data={"email": "stud@x.uz", "password": "password123", "remember_shown": "1"})
    legacy.post("/login", data={"email": "stud@x.uz", "password": "password123"})
    assert on.get_cookie("remember_token") is not None
    assert off.get_cookie("remember_token") is None          # unchecked: signed in until the browser closes
    assert legacy.get_cookie("remember_token") is not None   # old clients keep the old behaviour


def test_sign_out_everywhere_keeps_this_device(app):
    a, b = app.test_client(), app.test_client()
    for c in (a, b):
        c.post("/login", data={"email": "stud@x.uz", "password": "password123"})
        assert c.get("/settings").status_code == 200
    a.post("/settings", data={"action": "signout_all"})
    assert a.get("/settings").status_code == 200              # this device stays signed in
    assert b.get("/settings").status_code == 302              # the other one is signed out


def test_pages_have_the_new_controls(app):
    c = app.test_client()
    login = c.get("/login").get_data(as_text=True)
    reg = c.get("/register").get_data(as_text=True)
    assert 'name="remember"' in login and "data-reveal" in login
    assert "data-reveal" in reg and 'name="website"' in reg and 'id="pwHint"' in reg
