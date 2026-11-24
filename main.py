"""Public landing page and the user dashboard."""
from flask import Blueprint, render_template, url_for
from flask_login import login_required, current_user
from models import Attempt, SkillResult
import onboarding
import gamify
from progress import dashboard_progress

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/practice")
def practice():
    cards = [("Daraja aniqlash", "25 ta qisqa savol: darajangiz va mos mashqlar.", url_for("placement.intro")),
             ("Reading", "Matnlarni oʻqib, imtihon formatidagi savollarga javob bering.", url_for("reading.tests")),
             ("Listening", "Audioni tinglab, savollarga javob bering.", url_for("listening.tests")),
             ("Writing", "Xat va insho yozing, AI xatolaringizni tushuntiradi.", url_for("writing.tasks")),
             ("Speaking", "Ovozli javob bering, fikr-mulohaza oling.", url_for("speaking.tasks")),
             ("Aqlli mashq va challenge", "Zaif joylaringizga moslangan savollar, kunlik challenge, XP va nishonlar.", url_for("smart.home")),
             ("Xatolar daftari", "Reading va Listening'da xato qilgan savollaringizni qayta ishlang.", url_for("mistakes.index")),
             ("Toʻliq imtihon", "4 skill ketma-ket va oxirida umumiy daraja.", url_for("exam.index")),
             ("Shadowing", "Intervyu va podkastlarni eshitib, takrorlab gapiring.", url_for("shadowing.videos"))]
    return render_template("practice.html", cards=cards)


@bp.route("/dashboard")
@login_required
def dashboard():
    attempts = current_user.attempts.filter(Attempt.finished_at.isnot(None)).limit(20).all()
    writing = (SkillResult.query.filter_by(user_id=current_user.id, skill="writing")
               .order_by(SkillResult.created_at.desc()).limit(10).all())
    speaking = (SkillResult.query.filter_by(user_id=current_user.id, skill="speaking")
                .order_by(SkillResult.created_at.desc()).limit(10).all())
    placement = (SkillResult.query.filter_by(user_id=current_user.id, skill="placement")
                 .order_by(SkillResult.created_at.desc(), SkillResult.id.desc()).first())
    ob_profile = onboarding.profile_of(current_user)
    return render_template("dashboard.html", attempts=attempts, writing=writing, speaking=speaking,
                           prog=dashboard_progress(current_user), placement=placement,
                           gam=gamify.summary(current_user), ob_profile=ob_profile,
                           ob_line=onboarding.summary(ob_profile))
