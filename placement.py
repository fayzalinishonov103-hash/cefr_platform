"""Placement test: 25 quick questions (A1-C1) -> estimated level -> a suggested path.

Rules (kept simple and honest: this is a rough estimate, not an exam):
  * 5 questions per level; a level counts as passed with 3 of 5 correct;
  * the result is the last level passed in an unbroken chain starting at A1 (none passed -> "A0");
  * "Bilmayman" is an option on every question, so guessing is not rewarded;
  * the answer key stays on the server; options are shuffled on every page load.
"""
import random
from datetime import timedelta

from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user

import security
from extensions import db
from models import SkillResult
from placement_data import QUESTIONS, LEVELS

bp = Blueprint("placement", __name__)
PASS_AT = 3
PER_DAY = 5                 # finished placement tests per 24 hours
SKIP = "-1"

LEVEL_NAMES = {"A0": "Boshlangʻich (A1 dan past)", "A1": "Boshlovchi", "A2": "Elementar",
               "B1": "Oʻrta", "B2": "Oʻrta-yuqori", "C1": "Yuqori"}
LEVEL_TEXT = {
    "A0": "Siz endi boshlayapsiz. Bu yaxshi: eng tez oʻsish aynan shu bosqichda boʻladi. Eng koʻp ishlatiladigan "
          "soʻzlar va oddiy jumlalardan boshlang.",
    "A1": "Siz oddiy soʻz va jumlalarni bilasiz. Keyingi maqsad: kundalik mavzularda gaplashish va oddiy matnlarni oʻqish.",
    "A2": "Elementar daraja: kundalik vaziyatlarda oʻzingizni tushuntira olasiz. Keyingi maqsad: B1 ga chiqish.",
    "B1": "Oʻrta daraja. Milliy CEFR imtihoniga tayyorgarlikni boshlash uchun yaxshi vaqt.",
    "B2": "Oʻrta-yuqori daraja. Imtihonga yaqinsiz: Writing va Speaking aniqligi ustida ishlang.",
    "C1": "Yuqori daraja. Imtihon formatiga koʻnikish va xatolarni kamaytirish ustida ishlang.",
}


def estimate_level(correct_by_level):
    """{'A1': 4, 'A2': 3, ...} -> last level passed in an unbroken chain from A1 ('A0' if A1 is not passed)."""
    result = "A0"
    for level in LEVELS:
        if correct_by_level.get(level, 0) >= PASS_AT:
            result = level
        else:
            break
    return result


def grade(form):
    """Score the submitted form (fields p1..p25 hold the ORIGINAL option index, or '-1' for 'Bilmayman')."""
    scores = {lv: [0, 0] for lv in LEVELS}
    answered = skipped = 0
    for n, q in enumerate(QUESTIONS, 1):
        scores[q["level"]][1] += 1
        raw = (form.get(f"p{n}") or "").strip()
        if raw == SKIP:
            skipped += 1
        elif raw.isdigit() and int(raw) < len(q["options"]):
            answered += 1
            scores[q["level"]][0] += int(int(raw) == q["answer"])
    level = estimate_level({lv: c for lv, (c, _) in scores.items()})
    return {"level": level, "scores": scores, "answered": answered, "skipped": skipped, "total": len(QUESTIONS)}


def paths(level):
    """Suggested next steps for a level, as [{title, text, url, button}]."""
    vocab = {"title": "Lugʻat daftari", "text": "Har kuni 5–10 ta yangi soʻz oʻrganing va takrorlang.",
             "url": url_for("vocab.index"), "button": "LUGʻATGA OʻTISH"}
    reading = {"title": "Reading mashqi", "text": "Matnlarni oʻqing, noaniq soʻzlarni lugʻatga saqlang.",
               "url": url_for("reading.tests"), "button": "READING"}
    listening = {"title": "Listening mashqi", "text": "Audioni tinglab savollarga javob bering.",
                 "url": url_for("listening.tests"), "button": "LISTENING"}
    writing = {"title": "Writing", "text": "Xat yoki insho yozing, AI xatolaringizni oʻzbek tilida tushuntiradi.",
               "url": url_for("writing.tasks"), "button": "WRITING"}
    speaking = {"title": "Speaking", "text": "Savolga ovozli javob bering va fikr-mulohaza oling.",
                "url": url_for("speaking.tasks"), "button": "SPEAKING"}

    def shadow(lv):
        return {"title": "Shadowing", "text": f"{lv} darajadagi videolarni eshitib, takrorlab gapiring.",
                "url": url_for("shadowing.videos", level=lv), "button": "VIDEOLAR"}

    return {"A0": [vocab, shadow("A1"), reading], "A1": [vocab, shadow("A1"), reading],
            "A2": [vocab, shadow("A2"), reading, listening],
            "B1": [reading, listening, vocab, writing],
            "B2": [reading, listening, writing, speaking],
            "C1": [writing, speaking, reading, listening]}[level]


def _latest(user_id):
    return (SkillResult.query.filter_by(user_id=user_id, skill="placement")
            .order_by(SkillResult.created_at.desc(), SkillResult.id.desc()).first())


@bp.route("/placement")
def intro():
    last = _latest(current_user.id) if current_user.is_authenticated else None
    return render_template("placement_intro.html", last=last, names=LEVEL_NAMES, total=len(QUESTIONS))


@bp.route("/placement/test")
@login_required
def test():
    rng = random.Random()
    items = []
    for n, q in enumerate(QUESTIONS, 1):
        options = list(enumerate(q["options"]))        # (original index, text)
        rng.shuffle(options)
        items.append({"n": n, "text": q["text"], "options": options})
    return render_template("placement_test.html", items=items, total=len(items))


@bp.route("/placement/submit", methods=["POST"])
@login_required
def submit():
    since = security.now() - timedelta(hours=24)
    used = SkillResult.query.filter(SkillResult.user_id == current_user.id, SkillResult.skill == "placement",
                                    SkillResult.created_at >= since).count()
    if used >= PER_DAY:
        flash("Bugun daraja testini koʻp marta topshirdingiz. Ertaga qayta urinib koʻring.", "error")
        return redirect(url_for("placement.intro"))
    result = grade(request.form)
    if result["answered"] == 0:
        flash("Hech bir savolga javob bermadingiz. Bilmaganlarini “Bilmayman” deb belgilang, qolganini tanlang.", "error")
        return redirect(url_for("placement.test"))
    row = SkillResult(user_id=current_user.id, skill="placement", cefr_level=result["level"], feedback=result)
    db.session.add(row)
    db.session.commit()
    return redirect(url_for("placement.result", result_id=row.id))


@bp.route("/placement/result/<int:result_id>")
@login_required
def result(result_id):
    row = db.session.get(SkillResult, result_id)
    if row is None or row.user_id != current_user.id or row.skill != "placement":
        abort(404)
    f = row.feedback
    return render_template("placement_result.html", r=row, f=f, level=f["level"], name=LEVEL_NAMES[f["level"]],
                           text=LEVEL_TEXT[f["level"]], steps=paths(f["level"]), levels=LEVELS)
