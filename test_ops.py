"""Pre-launch operations: global AI cap, funnel page, terms page, local assets switch.  Run:  python -m pytest -q test_ops.py"""
import pytest

import security
from app import create_app
from extensions import db
from models import User


def make_app(tmp_path, **extra):
    cfg = {"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}"}
    cfg.update(extra)
    app = create_app(cfg)
    with app.app_context():
        db.create_all()
        for email, admin in (("admin@x.uz", True), ("stud@x.uz", False)):
            u = User(name=email.split("@")[0], email=email, is_admin=admin); u.set_password("password123"); db.session.add(u)
        db.session.commit()
    return app


def login(c, email):
    c.post("/login", data={"email": email, "password": "password123"})


def test_global_ai_cap_stops_everybody_together(tmp_path):
    app = make_app(tmp_path, AI_GLOBAL_DAILY_CAP=3)
    with app.app_context():
        answers = [security.ai_budget_ok(uid, "writing", 100) for uid in (1, 2, 1, 2, 1)]
    assert answers == [True, True, True, False, False]          # 4th call (any user) is over the shared ceiling of 3


def test_global_cap_off_by_default(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        assert all(security.ai_budget_ok(1, "writing", 100) for _ in range(20))


def test_per_user_cap_still_works(tmp_path):
    app = make_app(tmp_path, AI_GLOBAL_DAILY_CAP=1000)
    with app.app_context():
        assert [security.ai_budget_ok(1, "hint", 2) for _ in range(3)] == [True, True, False]


def test_stats_page_has_funnel_for_admins_only(tmp_path):
    app = make_app(tmp_path)
    a, s = app.test_client(), app.test_client()
    login(a, "admin@x.uz"); login(s, "stud@x.uz")
    page = a.get("/admin/onboarding")
    assert page.status_code == 200 and "VORONKA" in page.get_data(as_text=True)
    assert s.get("/admin/onboarding").status_code == 403


def test_terms_page_public_and_linked(tmp_path):
    c = make_app(tmp_path).test_client()
    assert c.get("/shartlar").status_code == 200
    assert "/shartlar" in c.get("/register").get_data(as_text=True)
    assert "OpenAI" in c.get("/maxfiylik").get_data(as_text=True)      # users are told where their texts go


def test_local_assets_replace_the_cdns_when_built(tmp_path):
    local = make_app(tmp_path, TAILWIND_LOCAL=True, FONTS_LOCAL=True, TAILWIND_VERSION=7)
    html = local.test_client().get("/login").get_data(as_text=True)
    assert "css/tailwind.css?v=7" in html and "css/fonts.css" in html
    assert "cdn.tailwindcss.com" not in html and "fonts.googleapis.com" not in html


def test_cdn_is_used_until_assets_are_built(tmp_path):
    app = make_app(tmp_path, TAILWIND_LOCAL=False, FONTS_LOCAL=False)
    html = app.test_client().get("/login").get_data(as_text=True)
    assert "cdn.tailwindcss.com" in html and "css/tailwind.css" not in html
