"""Security tests: password policy, persistent rate limits, session invalidation, redirects, headers.
Run:  python -m pytest -q test_security.py"""
import io
import pytest

import security
from app import create_app
from extensions import db
from models import User, ShadowVideo, ShadowMark, AuthAttempt, UsageLog


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin)
            u.set_password("password123"); db.session.add(u)
        db.session.commit()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(c, email="stud@x.uz", pw="password123"):
    return c.post("/login", data={"email": email, "password": pw})


GOOD_PW = "tulip-garden-42x"


def test_password_policy():
    v = security.validate_password
    assert v("short1") and v("a" * 200) and v("password123") and v("1234567890") and v("aaaaaaaaaaaa")
    assert v("studentpass99", email="student@x.uz")            # contains the email name
    assert v(GOOD_PW, email="stud@x.uz", name="Ali") is None


def test_safe_next():
    d = "/dashboard"
    assert security.safe_next("/reading", d) == "/reading"
    for bad in ("//evil.com", "/\\evil.com", "https://evil.com", "evil.com", "", None, "/a\nb", "/\\/evil.com"):
        assert security.safe_next(bad, d) == d


def test_register_rules(client):
    def reg(email, pw, name="Ali"):
        return client.post("/register", data={"name": name, "email": email, "password": pw})
    assert reg("new@x.uz", "short").status_code == 400
    assert reg("new@x.uz", "password123").status_code == 400
    assert reg("tg1@telegram.local", GOOD_PW).status_code == 400
    assert reg("new@x.uz", GOOD_PW, name="x" * 81).status_code == 400
    assert reg("not-an-email", GOOD_PW).status_code == 400
    assert reg("new@x.uz", GOOD_PW).status_code == 302


def test_admin_never_granted_at_registration(app):
    app.config["ADMIN_EMAILS"] = {"boss@x.uz"}                 # the old mechanism must be gone
    c = app.test_client()
    c.post("/register", data={"name": "Boss", "email": "boss@x.uz", "password": GOOD_PW})
    with app.app_context():
        assert User.query.filter_by(email="boss@x.uz").first().is_admin is False
    assert c.get("/admin/").status_code == 403


def test_login_throttle_is_persistent_and_not_a_lockout_for_others(app, client):
    for _ in range(security.LOGIN_PAIR_MAX):
        assert client.post("/login", data={"email": "stud@x.uz", "password": "wrong"}).status_code == 401
    assert login(client).status_code == 429                    # correct password is refused while blocked
    with app.app_context():                                    # stored in the database, not in memory
        assert AuthAttempt.query.filter_by(kind="login_fail").count() == security.LOGIN_PAIR_MAX
    assert login(client, "admin@x.uz").status_code == 302      # other accounts unaffected


def test_unknown_email_looks_like_wrong_password(client):
    r = client.post("/login", data={"email": "nobody@x.uz", "password": "whatever123"})
    assert r.status_code == 401 and "Email yoki parol" in r.get_data(as_text=True)


def test_password_change_signs_out_other_devices(app):
    a, b = app.test_client(), app.test_client()
    login(a); login(b)
    assert a.get("/dashboard").status_code == 200 and b.get("/dashboard").status_code == 200
    a.post("/settings", data={"action": "password", "old": "password123", "new": GOOD_PW, "again": GOOD_PW})
    assert a.get("/dashboard").status_code == 200              # the device that changed it stays signed in
    assert b.get("/dashboard").status_code == 302              # the other one is signed out
    assert login(app.test_client(), pw=GOOD_PW).status_code == 302


def test_weak_new_password_rejected(app):
    c = app.test_client(); login(c)
    c.post("/settings", data={"action": "password", "old": "password123", "new": "password1234", "again": "password1234"})
    assert login(app.test_client(), pw="password123").status_code == 302      # unchanged


def test_forgot_is_throttled_but_looks_the_same(client):
    seen = set()
    for _ in range(8):
        r = client.post("/forgot", data={"email": "stud@x.uz"}, follow_redirects=True)
        seen.add("roʻyxatdan oʻtgan boʻlsa" in r.get_data(as_text=True))
    assert seen == {True}


def test_delete_account_removes_shadow_marks(app):
    c = app.test_client(); login(c)
    with app.app_context():
        from models import BattleMatch
        v = ShadowVideo(youtube_id="dQw4w9WgXcQ", title="V"); db.session.add(v); db.session.flush()
        uid = User.query.filter_by(email="stud@x.uz").first().id
        admin_id = User.query.filter_by(email="admin@x.uz").first().id
        bm = BattleMatch(code="TEST1", player1_id=uid, player2_id=admin_id, status="finished")
        db.session.add(bm)
        db.session.add_all([ShadowMark(user_id=uid, video_id=v.id, kind="seen"), UsageLog(user_id=uid, kind="hint")])
        db.session.commit()
    r = c.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "password123"})
    assert r.status_code == 302
    with app.app_context():
        from models import BattleMatch
        assert User.query.filter_by(email="stud@x.uz").count() == 0
        assert ShadowMark.query.count() == 0 and UsageLog.query.count() == 0
        assert BattleMatch.query.count() == 0


def test_security_headers(client):
    r = client.get("/login")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["Cache-Control"] == "no-store"


def test_cost_cap_counts_failed_calls(app):
    with app.app_context():
        uid = User.query.filter_by(email="stud@x.uz").first().id
        assert all(security.ai_budget_ok(uid, "speaking", 3) for _ in range(3))
        assert security.ai_budget_ok(uid, "speaking", 3) is False


def test_audio_upload_checks_signature(app):
    c = app.test_client(); login(c, "admin@x.uz")
    fake = c.post("/admin/audio", data={"file": (io.BytesIO(b"<script>alert(1)</script>" * 4), "a.mp3")},
                  content_type="multipart/form-data")
    assert fake.status_code == 400
