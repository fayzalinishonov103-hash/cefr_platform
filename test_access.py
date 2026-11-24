"""Access-control matrix. It walks EVERY route of the app, so a new route without protection fails here.
Run:  python -m pytest -q test_access.py"""
import re
from datetime import datetime, timezone

import pytest

from app import create_app
from extensions import db
from models import (User, Test as TestModel, Part, QuestionGroup, Question, Attempt, WritingPrompt, SpeakingPrompt,
                    SkillResult, VocabWord, ShadowVideo)

# Pages anybody may open without signing in (GET only). Everything else must redirect to login or refuse.
PUBLIC_GET = {"/", "/login", "/register", "/forgot", "/health", "/reading", "/listening", "/writing", "/speaking",
              "/shadowing", "/practice", "/placement", "/maxfiylik", "/shartlar",
              "/listening/dictation", "/certificate/verify/<string:cert_id>"}
PUBLIC_ANY_METHOD = {"/login", "/register", "/forgot", "/auth/telegram", "/reset/<token>"}   # auth endpoints themselves


@pytest.fixture()
def world(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "PROPAGATE_EXCEPTIONS": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        users = {}
        for key, admin in (("admin", True), ("a", False), ("b", False)):
            u = User(name=key, email=f"{key}@x.uz", is_admin=admin); u.set_password("password123")
            db.session.add(u); users[key] = u
        t = TestModel(title="T", skill="reading", is_active=True); db.session.add(t); db.session.flush()
        p = Part(test_id=t.id, number=1, title="P", passage="x"); db.session.add(p); db.session.flush()
        g = QuestionGroup(part_id=p.id, qtype="mcq", instruction="i"); db.session.add(g); db.session.flush()
        db.session.add(Question(group_id=g.id, number=1, text="q", options=[["a", "A"], ["b", "B"]], answer="a", cefr_level="B1"))
        db.session.flush()
        attempt = Attempt(user_id=users["a"].id, test_id=t.id, finished_at=datetime.now(timezone.utc), answers={"q1": "a"},
                          raw_score=1, max_score=1, scaled_score=75, cefr_level="C1")
        db.session.add_all([attempt, WritingPrompt(title="w", prompt="p" * 20, task_type="essay", min_words=50, max_words=300),
                            SpeakingPrompt(part=1, title="s", prompt="p" * 20),
                            VocabWord(user_id=users["a"].id, word="owned"),
                            ShadowVideo(youtube_id="abcdefghijk", title="v", kind="talk", level="B1")])
        db.session.flush()
        results = {k: SkillResult(user_id=users["a"].id, skill=k, scaled_score=40, cefr_level="B1", feedback={})
                   for k in ("writing", "speaking", "placement")}
        db.session.add_all(results.values()); db.session.commit()
        ids = {"attempt": attempt.id, **{k: r.id for k, r in results.items()}}
    return app, ids


def sign_in(app, email):
    c = app.test_client()
    assert c.post("/login", data={"email": email, "password": "password123"}).status_code == 302
    return c


def concrete(rule):
    url = re.sub(r"<int:\w+>", "1", rule.rule)
    return re.sub(r"<(?:string:)?\w+>", "x", url)


def routes(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield rule, method


def call(client, method, url):
    return client.open(url, method=method, data={} if method == "POST" else None)


def test_anonymous_cannot_use_protected_routes(world):
    app, _ = world
    client = app.test_client()
    open_ = []
    for rule, method in routes(app):
        status = call(client, method, concrete(rule)).status_code
        if status in (200, 201):
            open_.append((method, rule.rule))
    allowed = ({("GET", r) for r in PUBLIC_GET} | {("GET", "/shadowing/<int:video_id>")}      # public gallery detail
               | {(m, r) for r in PUBLIC_ANY_METHOD for m in ("GET", "POST")})
    unexpected = [x for x in open_ if x not in allowed]
    assert not unexpected, f"reachable without signing in: {unexpected}"


def test_student_cannot_reach_admin(world):
    app, _ = world
    student = sign_in(app, "a@x.uz")
    leaks = []
    for rule, method in routes(app):
        if rule.rule.startswith("/admin"):
            status = call(student, method, concrete(rule)).status_code
            if status != 403:
                leaks.append((method, rule.rule, status))
    assert not leaks, f"admin routes not refusing a normal student with 403: {leaks}"


def test_admin_routes_open_for_admin(world):
    app, _ = world
    admin = sign_in(app, "admin@x.uz")
    assert admin.get("/admin/").status_code == 200 and admin.get("/admin/users").status_code == 200


def test_students_cannot_touch_each_others_data(world):
    app, ids = world
    intruder = sign_in(app, "b@x.uz")
    forbidden = [("GET", f"/attempt/{ids['attempt']}"), ("GET", f"/attempt/{ids['attempt']}/result"),
                 ("POST", f"/attempt/{ids['attempt']}/submit"), ("POST", f"/attempt/{ids['attempt']}/hint"),
                 ("GET", f"/writing/result/{ids['writing']}"), ("GET", f"/speaking/result/{ids['speaking']}"),
                 ("GET", f"/placement/result/{ids['placement']}"),
                 ("POST", "/vocab/1/delete"), ("POST", "/vocab/1/review")]
    bad = [(m, u, call(intruder, m, u).status_code) for m, u in forbidden if call(intruder, m, u).status_code not in (403, 404)]
    assert not bad, f"another student's data is reachable: {bad}"
    with app.app_context():
        assert VocabWord.query.filter_by(word="owned").count() == 1          # the POST delete did not work either
    owner = sign_in(app, "a@x.uz")
    assert owner.get(f"/attempt/{ids['attempt']}/result").status_code == 200   # sanity: the owner CAN open it


def test_no_get_route_changes_data(world):
    """State changes must be POST (CSRF-protected). A GET route that writes would be exploitable through <img src>."""
    app, _ = world
    client = sign_in(app, "a@x.uz")
    with app.app_context():
        before = (Attempt.query.count(), SkillResult.query.count(), VocabWord.query.count())
    for rule, method in routes(app):
        if method == "GET" and not rule.rule.startswith("/admin") and rule.rule not in ("/auth/telegram", "/reset/<token>"):
            call(client, "GET", concrete(rule))
    with app.app_context():
        assert (Attempt.query.count(), SkillResult.query.count(), VocabWord.query.count()) == before
