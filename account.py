"""Account settings: change name, change password, delete the account and all its data."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask import session
from flask_login import login_required, current_user, logout_user, login_user

import security
from extensions import db
from models import (User, Attempt, HintLog, SkillResult, VocabWord, ShadowMark, UsageLog, AuthAttempt, ExamSession,
                    MistakeFixed, PracticeSet, PracticeLog, XpEvent, Badge, LeaderboardMember, UserProfile,
                    BattleMatch)

bp = Blueprint("account", __name__)
DELETE_WORD = "OCHIRISH"


def _is_telegram(user):
    return user.email.endswith("@telegram.local")


def _password_ok(raw):
    """Check the current password; wrong guesses are counted so this form cannot be used to brute-force it."""
    if current_user.check_password(raw):
        return True
    security.record("pwcheck", current_user.email)
    return False


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "name":
            name = " ".join(request.form.get("name", "").split())
            if not 1 <= len(name) <= 80:
                flash("Ism 1 dan 80 gacha belgidan iborat boʻlsin.", "error")
            else:
                current_user.name = name
                db.session.commit()
                flash("Ism saqlandi.", "ok")
        elif action == "password" and not _is_telegram(current_user):
            old, new, again = (request.form.get(k, "")[:1024] for k in ("old", "new", "again"))
            if security.limited("pwcheck", 900, ip_max=30, email=current_user.email, email_max=5):
                flash("Juda koʻp urinish. 15 daqiqadan keyin qayta urinib koʻring.", "error")
            elif not _password_ok(old):
                flash("Joriy parol notoʻgʻri.", "error")
            elif (problem := security.validate_password(new, current_user.email, current_user.name)):
                flash(problem, "error")
            elif new != again:
                flash("Yangi parollar bir xil emas.", "error")
            else:
                user = current_user._get_current_object()
                user.set_password(new)
                user.rotate_session()                  # signs out every other device ...
                db.session.commit()
                session.clear()
                login_user(user, remember=True)        # ... but keeps this one signed in
                flash("Parol almashtirildi. Boshqa qurilmalardan chiqarildingiz.", "ok")
        elif action == "signout_all":
            user = current_user._get_current_object()
            user.rotate_session()                      # every other browser and phone is signed out
            db.session.commit()
            session.clear()
            login_user(user, remember=True)            # this device stays signed in
            flash("Boshqa barcha qurilmalardan chiqarildingiz.", "ok")
        elif action == "delete":
            if request.form.get("confirm", "").strip().upper() != DELETE_WORD:
                flash(f"Hisobni oʻchirish uchun {DELETE_WORD} soʻzini yozing.", "error")
            elif not _is_telegram(current_user) and not _password_ok(request.form.get("password", "")[:1024]):
                flash("Hisobni oʻchirish uchun joriy parolingizni kiriting.", "error")
            elif current_user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
                flash("Siz yagona adminsiz. Avval boshqa foydalanuvchini admin qiling.", "error")
            else:
                uid = current_user.id
                attempt_ids = [a for (a,) in db.session.query(Attempt.id).filter(Attempt.user_id == uid)]
                if attempt_ids:
                    HintLog.query.filter(HintLog.attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
                Attempt.query.filter_by(user_id=uid).delete(synchronize_session=False)
                SkillResult.query.filter_by(user_id=uid).delete(synchronize_session=False)
                VocabWord.query.filter_by(user_id=uid).delete(synchronize_session=False)
                ShadowMark.query.filter_by(user_id=uid).delete(synchronize_session=False)
                ExamSession.query.filter_by(user_id=uid).delete(synchronize_session=False)
                MistakeFixed.query.filter_by(user_id=uid).delete(synchronize_session=False)
                UsageLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
                for model in (PracticeSet, PracticeLog, XpEvent, Badge, LeaderboardMember, UserProfile):
                    model.query.filter_by(user_id=uid).delete(synchronize_session=False)
                BattleMatch.query.filter(
                    (BattleMatch.player1_id == uid) | (BattleMatch.player2_id == uid)
                ).delete(synchronize_session=False)
                user = db.session.get(User, uid)
                AuthAttempt.query.filter_by(email=user.email).delete(synchronize_session=False)
                logout_user()
                db.session.delete(user)
                db.session.commit()
                flash("Hisobingiz va barcha maʼlumotlaringiz oʻchirildi.", "ok")
                return redirect(url_for("main.index"))
        return redirect(url_for("account.settings"))
    return render_template("settings.html", telegram=_is_telegram(current_user), word=DELETE_WORD)
