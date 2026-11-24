"""E-mail confirmation (code + link), unique mailboxes, AI gate.  Run:  python -m pytest -q test_verify.py"""
import re

import pytest

import mailer
from app import create_app
from extensions import db
from models import User

GOOD_PW = "Correct-Horse-9"


@pytest.fixture()
def sent(monkeypatch):
    box = []
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, body: box.append((to, subject, body)) or True)
    return box


def make_app(tmp_path, enabled=True):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "VERIFY_ENABLED": enabled,
                      "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_BOT_USERNAME": "",
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
    return app


def register(c, email="ali@x.uz"):
    return c.post("/register", data={"name": "Ali", "email": email, "password": GOOD_PW})


def code_of(sent):
    return re.search(r"kodi: (\d{6})", sent[-1][2]).group(1)


def verified(app, email="ali@x.uz"):
    with app.app_context():
        return bool(User.query.filter_by(email=email).first().email_verified_at)


def test_register_sends_a_code_and_starts_unverified(tmp_path, sent):
    app = make_app(tmp_path); c = app.test_client()
    assert register(c).status_code == 302
    assert len(sent) == 1 and sent[0][0] == "ali@x.uz" and re.search(r"\d{6}", sent[0][2])
    assert not verified(app)


def test_unverified_accounts_cannot_reach_the_ai_pages_but_can_use_the_rest(tmp_path, sent):
    c = make_app(tmp_path).test_client(); register(c)
    for path in ("/writing/1", "/speaking/1"):
        r = c.get(path)
        assert r.status_code == 302 and "/tasdiqlash" in r.headers["Location"]
    assert c.get("/reading").status_code == 200 and c.get("/dashboard").status_code == 200


def test_correct_code_unlocks_everything(tmp_path, sent):
    app = make_app(tmp_path); c = app.test_client(); register(c)
    r = c.post("/tasdiqlash", data={"code": code_of(sent)})
    assert r.status_code == 302 and verified(app)
    assert c.get("/writing/1").status_code == 404            # past the gate (there is just no such task in an empty database)


def test_wrong_codes_are_rate_limited(tmp_path, sent):
    app = make_app(tmp_path); c = app.test_client(); register(c)
    assert c.post("/tasdiqlash", data={"code": "000000"}).status_code == 400
    for _ in range(4):
        c.post("/tasdiqlash", data={"code": "000000"})
    assert c.post("/tasdiqlash", data={"code": code_of(sent)}).status_code == 429     # even the right code waits now
    assert not verified(app)


def test_link_in_the_email_verifies(tmp_path, sent):
    app = make_app(tmp_path); c = app.test_client(); register(c)
    path = re.search(r"(/tasdiqlash/havola/\S+)", sent[0][2]).group(1)
    assert c.get(path).status_code == 302 and verified(app)
    assert app.test_client().get("/tasdiqlash/havola/not-a-real-token").status_code == 302


def test_resend_is_limited_to_three_per_hour(tmp_path, sent):
    c = make_app(tmp_path).test_client(); register(c)
    for _ in range(3):
        c.post("/tasdiqlash/yuborish")
    assert len(sent) == 3                                    # the sign-up mail + 2 resends; the 3rd resend is refused


def test_one_mailbox_one_account(tmp_path, sent):
    app = make_app(tmp_path)
    assert register(app.test_client(), "a.b+first@gmail.com").status_code == 302
    assert register(app.test_client(), "ab@gmail.com").status_code == 400
    assert register(app.test_client(), "AB+second@googlemail.com").status_code == 400
    assert register(app.test_client(), "other@x.uz").status_code == 302


def test_nothing_changes_while_verification_is_off(tmp_path, sent):
    app = make_app(tmp_path, enabled=False); c = app.test_client(); register(c)
    assert sent == [] and c.get("/writing/1").status_code == 404


def test_register_page_is_short_and_telegram_has_no_duplicate(tmp_path, sent):
    page = make_app(tmp_path).test_client().get("/register").get_data(as_text=True)
    assert 'name="interests"' not in page and page.count("telegram-widget.js") == 0
