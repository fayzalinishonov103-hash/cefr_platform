"""Tests for Smart Audio Dictation module."""
from app import create_app
from extensions import db
from models import User
from dictation_data import get_all_phrases, get_phrase_by_id
from listening import _diff_dictation


def test_dictation_data():
    phrases = get_all_phrases()
    assert len(phrases) >= 15
    p1 = get_phrase_by_id(1)
    assert p1 is not None
    assert "going to" in p1["feature"] or "Reduction" in p1["feature"]


def test_dictation_diff_algorithm():
    target = "I should have called you before leaving."
    # Exact match
    res_exact = _diff_dictation(target, "I should have called you before leaving")
    assert res_exact["accuracy"] == 100
    assert res_exact["is_passed"] is True

    # Partial match / connected speech confusion (should of)
    res_partial = _diff_dictation(target, "I should of called you before leaving")
    assert res_partial["is_passed"] is True  # 6 out of 7 is ~86%
    assert any(t["status"] == "missed" and t["word"] == "have" for t in res_partial["target_tokens"])
    assert any(t["status"] == "wrong" and t["word"] == "of" for t in res_partial["user_tokens"])


def test_dictation_routes(tmp_path):
    from datetime import datetime, timezone
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'dict.db'}"})
    with app.app_context():
        db.create_all()
        u = User(name="Student", email="student@test.uz", email_verified_at=datetime.now(timezone.utc))
        u.set_password("pass1234")
        db.session.add(u)
        db.session.commit()

        client = app.test_client()
        # Public dictation page
        resp = client.get("/listening/dictation")
        assert resp.status_code == 200
        assert b"Smart Audio Diktant" in resp.data

        # Filter by level
        resp_c1 = client.get("/listening/dictation?level=C1")
        assert resp_c1.status_code == 200

        # Submit check
        p1 = get_phrase_by_id(1)
        check_resp = client.post("/listening/dictation/check",
                                 json={"phrase_id": p1["id"], "user_text": p1["text"]})
        assert check_resp.status_code == 200
        data = check_resp.get_json()
        assert data["ok"] is True
        assert data["accuracy"] == 100
        assert data["is_passed"] is True

        # Audio route
        resp_audio = client.get(f"/listening/dictation/audio/{p1['id']}")
        assert resp_audio.status_code == 302
        assert "phrase_1.mp3" in resp_audio.headers["Location"]

