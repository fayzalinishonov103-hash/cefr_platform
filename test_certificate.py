"""Tests for CEFR Certificate generation and verification."""
from datetime import datetime, timezone
from app import create_app
from extensions import db
from models import User, Test, Attempt, ExamSession


def test_certificate_flow(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'cert.db'}"})
    with app.app_context():
        db.create_all()
        u = User(name="Fayzali", email="fayzali@test.uz", email_verified_at=datetime.now(timezone.utc))
        u.set_password("pass1234")
        db.session.add(u)
        db.session.commit()

        t = Test(title="Reading Mock 1", skill="reading", is_active=True)
        db.session.add(t)
        db.session.commit()

        att = Attempt(user_id=u.id, test_id=t.id, finished_at=datetime.now(timezone.utc),
                      raw_score=30, max_score=35, scaled_score=68, cefr_level="B2")
        exam = ExamSession(user_id=u.id, finished_at=datetime.now(timezone.utc),
                           overall_score=71, overall_level="C1",
                           results={"reading": {"score": 72, "level": "C1"},
                                    "listening": {"score": 68, "level": "B2"},
                                    "writing": {"score": 70, "level": "C1"},
                                    "speaking": {"score": 74, "level": "C1"}})
        db.session.add_all([att, exam])
        db.session.commit()

        client = app.test_client()
        # Anonymous cannot access student's certificate directly
        assert client.get(f"/certificate/attempt/{att.id}").status_code == 302
        assert client.get(f"/certificate/exam/{exam.id}").status_code == 302

        # Public verification endpoint works anonymously
        verify_resp = client.get("/certificate/verify/LEVI-TEST-12345")
        assert verify_resp.status_code == 200
        assert b"LEVI-TEST-12345" in verify_resp.data

        # Login and view certificates
        client.post("/login", data={"email": "fayzali@test.uz", "password": "pass1234"})
        resp_att = client.get(f"/certificate/attempt/{att.id}")
        assert resp_att.status_code == 200
        assert b"Fayzali" in resp_att.data
        assert b"B2" in resp_att.data

        resp_exam = client.get(f"/certificate/exam/{exam.id}")
        assert resp_exam.status_code == 200
        assert b"Fayzali" in resp_exam.data
        assert b"C1" in resp_exam.data
        assert b"MULTILEVEL FULL MOCK EXAM" in resp_exam.data
