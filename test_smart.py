"""Smart practice, daily challenge, XP, badges and the leaderboard.  Run:  python -m pytest -q test_smart.py"""
from datetime import timedelta

import pytest

import gamify
import security
import smart
from app import create_app
from extensions import db
from models import (User, Test as TestModel, Part, QuestionGroup, Question, Attempt, PracticeSet, PracticeLog, XpEvent,
                    Badge, LeaderboardMember, MistakeFixed)


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"})
    with app.app_context():
        db.create_all()
        for key in ("a", "b"):
            u = User(name=key, email=f"{key}@x.uz"); u.set_password("password123"); db.session.add(u)
        t = TestModel(title="Bank", skill="reading", is_active=True); db.session.add(t); db.session.flush()
        n = 0
        for number, qtype, level, answer, opts in ((1, "mcq", "A2", "a", [["a", "A"], ["b", "B"]]),
                                                    (2, "tfng", "B2", "true", [["true", "True"], ["false", "False"], ["ng", "Not Given"]])):
            p = Part(test_id=t.id, number=number, title=f"P{number}", passage=f"Passage {number}.\n\nSecond paragraph."); db.session.add(p); db.session.flush()
            g = QuestionGroup(part_id=p.id, qtype=qtype, instruction=f"Do {qtype}"); db.session.add(g); db.session.flush()
            for _ in range(6):
                n += 1
                db.session.add(Question(group_id=g.id, number=n, text=f"Question {n}", options=opts, answer=answer, cefr_level=level))
        db.session.commit()
    return app


def sign_in(app, key="a"):
    c = app.test_client()
    assert c.post("/login", data={"email": f"{key}@x.uz", "password": "password123"}).status_code == 302
    return c


def uid(key="a"):
    return User.query.filter_by(email=f"{key}@x.uz").first().id


def seed_history(app, wrong_qtype="tfng", key="a"):
    """A finished attempt where every question of `wrong_qtype` was wrong and the others were right."""
    with app.app_context():
        t = TestModel.query.first()
        answers, raw = {}, 0
        for q in Question.query.all():
            ok = q.group.qtype != wrong_qtype
            answers[f"q{q.number}"] = q.answer if ok else "false" if q.answer == "true" else "b"
            raw += ok
        db.session.add(Attempt(user_id=uid(key), test_id=t.id, finished_at=security.now() - timedelta(days=3), answers=answers,
                               raw_score=raw, max_score=12, scaled_score=40, cefr_level="B1"))
        db.session.commit()


def qids(app, qtype=None):
    with app.app_context():
        return [q.id for q in Question.query.order_by(Question.number) if qtype is None or q.group.qtype == qtype]


def answers_form(app, ps_id, right=True):
    with app.app_context():
        ps = db.session.get(PracticeSet, ps_id)
        out = {}
        for q in Question.query.filter(Question.id.in_(ps.question_ids)):
            out[f"s{q.id}"] = q.answer if right else "zzz"
        return out


# ------------------------------------------------------------------ engine
def test_picks_the_weak_question_type(app):
    seed_history(app, wrong_qtype="tfng")
    with app.app_context():
        picked = smart.build_set(db.session.get(User, uid()), "any", 6)
        assert len(picked) == 6 and {g.qtype for _q, g, *_ in picked} == {"tfng"}          # weak type -> its part
        assert any("True / False / Not Given" in t and "xato" in t for _q, _g, _p, _t, tags in picked for t in tags)


def test_recent_correct_answers_are_not_repeated(app):
    seed_history(app, wrong_qtype="tfng")
    mcq_ids = set(qids(app, "mcq"))
    with app.app_context():
        for qid in mcq_ids:                                                  # just answered every mcq correctly, a minute ago
            db.session.add(PracticeLog(user_id=uid(), question_id=qid, qtype="mcq", level="A2", correct=True, created_at=security.now()))
        db.session.commit()
        picked = smart.build_set(db.session.get(User, uid()), "any", 6)
        assert not {q.id for q, *_ in picked} & mcq_ids


def test_wrong_before_is_brought_back(app):
    seed_history(app, wrong_qtype="tfng")
    with app.app_context():
        picked = smart.build_set(db.session.get(User, uid()), "any", 6)
        assert all("Qayta takrorlash" in tags for *_x, tags in picked)        # wrong 3 days ago -> due again


def test_mastery_is_pulled_to_a_prior_and_weighs_recent_more():
    now = security.now()
    one_lucky = [{"qid": 1, "qtype": "mcq", "level": "B1", "correct": True, "when": now}]
    assert smart.mastery(one_lucky, now)["type"]["mcq"]["acc"] < 0.9              # one right answer is not "mastered"
    mixed = [{"qid": 1, "qtype": "mcq", "level": "B1", "correct": True, "when": now},
             {"qid": 2, "qtype": "mcq", "level": "B1", "correct": False, "when": now - timedelta(days=180)}]
    assert smart.mastery(mixed, now)["type"]["mcq"]["acc"] > 0.6                  # the old mistake counts for little


def test_level_index_and_empty_bank(app):
    assert [smart.level_index(x) for x in ("A1", "C2", None, "B1 dan past")] == [0, 5, 2, 1]
    with app.app_context():
        for model in (Question, QuestionGroup, Part):
            model.query.delete()
        db.session.commit()
        assert smart.build_set(db.session.get(User, uid()), "any", 8) == []
    c = sign_in(app)
    r = c.post("/smart/start", data={"skill": "any"})
    assert r.status_code == 302 and "/smart" in r.headers["Location"]
    with app.app_context():
        assert PracticeSet.query.count() == 0


# ------------------------------------------------------------------ the session flow
def test_session_flow_xp_and_no_double_payout(app):
    c = sign_in(app)
    r = c.post("/smart/start", data={"skill": "reading"}); loc = r.headers["Location"]
    page = c.get(loc); html = page.get_data(as_text=True)
    assert page.status_code == 200 and "Passage" in html and "MATNNI" in html
    ps_id = int(loc.rsplit("/", 1)[1])
    assert c.post("/smart/start", data={"skill": "reading"}).headers["Location"] == loc          # resumes the same open session
    form = answers_form(app, ps_id)
    n = len(form)
    form["s999999"] = "forged"                                                                    # a question that was never issued
    res = c.post(f"/smart/{ps_id}/submit", data=form)
    assert res.status_code == 302 and res.headers["Location"].endswith(f"/smart/{ps_id}/result")
    with app.app_context():
        ps = db.session.get(PracticeSet, ps_id)
        assert ps.correct == n and ps.total == n and PracticeLog.query.count() == n
        assert gamify.total_xp(uid()) == n * 10                                                   # 5 per answer + 5 per correct
    again = c.post(f"/smart/{ps_id}/submit", data=form)                                           # replay / double click
    assert again.status_code == 302
    with app.app_context():
        assert gamify.total_xp(uid()) == n * 10 and PracticeLog.query.count() == n
    result = c.get(f"/smart/{ps_id}/result").get_data(as_text=True)
    assert f"{n} / {n}" in result and f"+{n * 10}" in result
    assert c.get(loc).status_code == 302                                                          # a finished session redirects to its result


def test_other_users_cannot_touch_a_session(app):
    a, b = sign_in(app, "a"), sign_in(app, "b")
    loc = a.post("/smart/start", data={"skill": "any"}).headers["Location"]
    sid = loc.rsplit("/", 1)[1]
    for method, url in (("get", loc), ("post", f"/smart/{sid}/submit"), ("get", f"/smart/{sid}/result")):
        assert getattr(b, method)(url).status_code == 404
    with app.app_context():
        assert PracticeLog.query.count() == 0


def test_wrong_answers_and_mistakes_notebook(app):
    seed_history(app, wrong_qtype="tfng")
    c = sign_in(app)
    from mistakes import collect
    with app.app_context():
        before = len(collect(uid()))
    assert before == 6                                                                            # the six tfng questions
    loc = c.post("/smart/start", data={"skill": "reading"}).headers["Location"]
    c.post(f"/smart/{loc.rsplit('/', 1)[1]}/submit", data=answers_form(app, int(loc.rsplit('/', 1)[1])))   # all correct
    with app.app_context():
        assert len(collect(uid())) < before and MistakeFixed.query.count() == before - len(collect(uid()))


def test_get_requests_do_not_create_anything(app):
    c = sign_in(app)
    assert c.get("/smart").status_code == 200 and c.get("/leaderboard").status_code == 200
    assert c.get("/smart/daily").status_code == 405 and c.get("/smart/start").status_code == 405
    with app.app_context():
        assert PracticeSet.query.count() == 0


def test_deleted_questions_do_not_break_a_session(app):
    c = sign_in(app)
    loc = c.post("/smart/start", data={"skill": "reading"}).headers["Location"]
    sid = int(loc.rsplit("/", 1)[1])
    with app.app_context():
        ps = db.session.get(PracticeSet, sid)
        victim = ps.question_ids[0]
        db.session.delete(db.session.get(Question, victim)); db.session.commit()                   # an admin edit replaced it
    assert c.get(loc).status_code == 200
    form = answers_form(app, sid)
    assert c.post(f"/smart/{sid}/submit", data=form).status_code == 302
    with app.app_context():
        ps = db.session.get(PracticeSet, sid)
        assert ps.total == len(form) and ps.finished_at
        for q in list(Question.query.filter(Question.id.in_(ps.question_ids))):
            db.session.delete(q)
        db.session.commit()
    assert c.get(f"/smart/{sid}/result").status_code == 200                                         # old results still render


# ------------------------------------------------------------------ daily challenge
def test_daily_challenge_is_stable_once_a_day_and_pays_a_bonus(app):
    c = sign_in(app)
    first = c.post("/smart/daily").headers["Location"]
    assert c.post("/smart/daily").headers["Location"] == first                                      # same set again
    sid = int(first.rsplit("/", 1)[1])
    with app.app_context():
        ps = db.session.get(PracticeSet, sid)
        assert ps.kind == "daily" and len(ps.question_ids) == smart.DAILY_SIZE and ps.day is not None
        before = list(ps.question_ids)
    c.post(f"/smart/{sid}/submit", data=answers_form(app, sid))
    with app.app_context():
        total = gamify.total_xp(uid())
        assert total == 5 * 10 + gamify.XP_DAILY_BONUS + gamify.XP_DAILY_STREAK_STEP * 1        # 50 + 20 + streak(1 day)*3
        assert db.session.get(PracticeSet, sid).question_ids == before
    assert c.post("/smart/daily").headers["Location"].endswith(f"/smart/{sid}/result")            # done today -> shows the result
    with app.app_context():
        assert PracticeSet.query.filter_by(kind="daily").count() == 1
        from progress import activity_counter, today_local
        assert activity_counter(db.session.get(User, uid()))[today_local()] >= 1                    # keeps the streak alive


def test_no_bonus_for_a_bad_daily(app):
    c = sign_in(app)
    sid = int(c.post("/smart/daily").headers["Location"].rsplit("/", 1)[1])
    c.post(f"/smart/{sid}/submit", data=answers_form(app, sid, right=False))
    with app.app_context():
        assert gamify.total_xp(uid()) == 5 * smart.DAILY_SIZE                                      # effort XP only


# ------------------------------------------------------------------ XP, levels, badges
def test_levels_and_award_once(app):
    assert [gamify.level_info(x)["level"] for x in (0, 49, 50, 199, 200, 449, 450, 800)] == [1, 1, 2, 2, 3, 3, 4, 5]
    assert gamify.level_info(100)["pct"] == 33 and gamify.level_info(100)["to_next"] == 100
    with app.app_context():
        assert gamify.award(uid(), 10, "test", "1") is True and gamify.award(uid(), 10, "test", "1") is False
        assert gamify.award(uid(), 0, "test", "2") is False and gamify.total_xp(uid()) == 10


def test_finishing_a_test_gives_xp_and_badge_and_hook_errors_are_swallowed(app, monkeypatch):
    c = sign_in(app)
    with app.app_context():
        tid = TestModel.query.first().id
    loc = c.post(f"/reading/{tid}/start").headers["Location"]
    with app.app_context():
        form = {f"q{q.number}": q.answer for q in Question.query.filter(Question.number <= 6)}
    res = c.post(loc + "/submit", data=form)
    assert res.status_code == 302
    with app.app_context():
        assert gamify.total_xp(uid()) == 3 * 6 and "first_test" in {b.code for b in Badge.query.filter_by(user_id=uid())}
    def boom(*a, **k): raise RuntimeError("db hiccup")
    monkeypatch.setattr(gamify, "award", boom)
    loc2 = c.post(f"/reading/{tid}/start").headers["Location"]
    assert c.post(loc2 + "/submit", data=form).status_code == 302                                   # the test still finishes


def test_badges_are_idempotent(app):
    with app.app_context():
        gamify.award(uid(), 800, "bonus", "x")
        first = gamify.check_badges(uid())
        assert "level_5" in first and gamify.check_badges(uid()) == []
        assert Badge.query.filter_by(user_id=uid(), code="level_5").count() == 1


# ------------------------------------------------------------------ leaderboard
def test_leaderboard_is_opt_in_nickname_only(app):
    a, b = sign_in(app, "a"), sign_in(app, "b")
    with app.app_context():
        gamify.award(uid("a"), 100, "bonus", "1"); gamify.award(uid("b"), 300, "bonus", "1")
        gamify.award(uid("a"), 999, "bonus", "old")
        XpEvent.query.filter_by(user_id=uid("a"), ref="old").update({"created_at": security.now() - timedelta(days=9)})
        db.session.commit()
    page = a.get("/leaderboard").get_data(as_text=True)
    assert "REYTINGGA QOʻSHILISH" in page and "a@x.uz" not in page
    for bad in ("ab", "x" * 21, "has space", "a@b.co", "эмодзи", "", "<script>"):
        a.post("/leaderboard/join", data={"nickname": bad})
    with app.app_context():
        assert LeaderboardMember.query.count() == 0
    a.post("/leaderboard/join", data={"nickname": "Alice_1"})
    b.post("/leaderboard/join", data={"nickname": "alice_1"})                                        # same name, other case
    with app.app_context():
        assert LeaderboardMember.query.count() == 1
    b.post("/leaderboard/join", data={"nickname": "Bobby"})
    html = a.get("/leaderboard").get_data(as_text=True)
    table = html[html.index("ENG YAXSHILAR"):]                                                       # the ranking table only
    assert table.index("Bobby") < table.index("Alice_1")                                             # 300 XP beats 100 XP
    assert "#1</td>" in table and table.index("#1</td>") < table.index("Bobby")
    assert "999 XP" not in html and "1099 XP" not in html and "a@x.uz" not in html and "b@x.uz" not in html                      # old XP excluded; no real data shown
    a.post("/leaderboard/leave")
    with app.app_context():
        assert LeaderboardMember.query.filter_by(user_id=uid("a")).count() == 0
    assert "Alice_1" not in b.get("/leaderboard").get_data(as_text=True)


# ------------------------------------------------------------------ privacy
def test_account_deletion_removes_everything_new(app):
    c = sign_in(app)
    sid = int(c.post("/smart/daily").headers["Location"].rsplit("/", 1)[1])
    c.post(f"/smart/{sid}/submit", data=answers_form(app, sid))
    c.post("/leaderboard/join", data={"nickname": "Gone_Soon"})
    with app.app_context():
        assert all(m.query.count() for m in (PracticeSet, PracticeLog, XpEvent, LeaderboardMember))
    c.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "WRONG"})
    with app.app_context():
        assert User.query.filter_by(email="a@x.uz").count() == 1                                      # wrong password: nothing deleted
    assert c.post("/settings", data={"action": "delete", "confirm": "OCHIRISH", "password": "password123"}).status_code == 302
    with app.app_context():
        assert not any(m.query.count() for m in (PracticeSet, PracticeLog, XpEvent, Badge, LeaderboardMember))
        assert User.query.filter_by(email="a@x.uz").count() == 0


def test_pages_render_with_real_data(app):
    seed_history(app, wrong_qtype="tfng")
    c = sign_in(app)
    home = c.get("/smart").get_data(as_text=True)
    assert "ZAIF" in home and "True / False / Not Given" in home and "12 ta javob" in home and "Birinchi qadam" in home
    dash = c.get("/dashboard").get_data(as_text=True)
    assert "KUNLIK CHALLENGE VA XP" in dash and "BOSHLASH" in dash
    assert "Aqlli mashq" in c.get("/practice").get_data(as_text=True)
