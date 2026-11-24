"""Admin panel: create, edit, activate and delete Reading and Listening tests in the browser."""
import logging
import os
import uuid
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import current_user
from sqlalchemy import func

from extensions import db, login_manager
from models import User, Test, Part, QuestionGroup, Question, Attempt, WritingPrompt, SpeakingPrompt
from ai_hint import NoApiKey
import importer

log = logging.getLogger(__name__)
MAX_IMPORT_CHARS = 30000

bp = Blueprint("admin", __name__, url_prefix="/admin")

QTYPES = {"gap_fill", "match", "heading", "mcq", "tfng", "map"}
OPTION_TYPES = {"match", "heading", "mcq", "map"}
LEVELS = {"", "A1", "A2", "B1", "B2", "C1", "C2"}
TFNG = [["true", "True"], ["false", "False"], ["ng", "Not Given"]]
SKILLS = {"reading": "READING", "listening": "LISTENING"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg"}
AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "audio")
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "maps")
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def test_to_dict(test):
    """Test -> plain dict for the browser editor (includes the answer key: admin only)."""
    return {
        "id": test.id, "skill": test.skill, "title": test.title, "duration_min": test.duration_min,
        "is_active": test.is_active,
        "parts": [{
            "title": p.title or "", "passage": p.passage or "", "audio_url": p.audio_url or "", "image_url": p.image_url or "",
            "groups": [{
                "qtype": g.qtype, "instruction": g.instruction or "",
                "questions": [{"number": q.number, "text": q.text or "", "options": q.options,
                               "answer": q.answer, "cefr_level": q.cefr_level or ""} for q in g.questions],
            } for g in p.groups],
        } for p in test.parts],
    }


def parse_payload(data):
    """Validate the editor payload. Returns (clean_dict, list_of_error_messages)."""
    errors = []
    skill = str(data.get("skill") or "reading")
    if skill not in SKILLS:
        errors.append("Test turi notoʻgʻri.")
    listening = skill == "listening"
    title = str(data.get("title") or "").strip()
    duration = _int(data.get("duration_min"))
    if not title or len(title) > 150:
        errors.append("Test nomi boʻsh boʻlmasligi va 150 belgidan oshmasligi kerak.")
    if duration is None or not 1 <= duration <= 240:
        errors.append("Davomiylik 1 dan 240 daqiqagacha boʻlishi kerak.")

    parts_in = data.get("parts")
    if not isinstance(parts_in, list) or not 1 <= len(parts_in) <= 10:
        return None, errors + ["1 dan 10 tagacha part boʻlishi kerak."]

    seen, parts, total = set(), [], 0
    for pi, p in enumerate(parts_in, 1):
        passage = str((p or {}).get("passage") or "").strip()     # Listening: the transcript (optional)
        audio_url = str((p or {}).get("audio_url") or "").strip() if listening else ""
        if not listening and not passage:
            errors.append(f"Part {pi}: matn boʻsh.")
        if listening and not audio_url:
            errors.append(f"Part {pi}: audio yuklanmagan.")
        elif audio_url and (len(audio_url) > 255 or not audio_url.startswith(("/static/audio/", "https://"))):
            errors.append(f"Part {pi}: audio havolasi notoʻgʻri (yuklang yoki https:// havola kiriting).")
        image_url = str((p or {}).get("image_url") or "").strip()      # map / diagram: only files uploaded here
        if image_url and (len(image_url) > 255 or not image_url.startswith("/static/maps/")):
            errors.append(f"Part {pi}: rasm havolasi notoʻgʻri (rasmni yuklang).")
            image_url = ""
        groups = []
        for gi, g in enumerate((p or {}).get("groups") or [], 1):
            qtype = (g or {}).get("qtype")
            if qtype not in QTYPES:
                errors.append(f"Part {pi}, guruh {gi}: savol turi notoʻgʻri.")
                continue
            questions = []
            for q in (g.get("questions") or []):
                n = _int(q.get("number"))
                tag = f"{n}-savol" if n else f"Part {pi}, guruh {gi}: raqamsiz savol"
                text = str(q.get("text") or "").strip()
                answer = str(q.get("answer") or "").strip()
                level = str(q.get("cefr_level") or "").strip().upper()
                if n is None or not 1 <= n <= 500:
                    errors.append(f"{tag}: raqam 1 dan 500 gacha boʻlishi kerak.")
                elif n in seen:
                    errors.append(f"{n}-savol raqami takrorlangan.")
                else:
                    seen.add(n)
                if not text:
                    errors.append(f"{tag}: matn boʻsh.")
                if qtype == "gap_fill" and "___" not in text:
                    errors.append(f"{tag}: matnda boʻsh joy belgisi ___ boʻlishi kerak.")
                if not answer or len(answer) > 200:
                    errors.append(f"{tag}: toʻgʻri javob boʻsh yoki juda uzun.")
                if level not in LEVELS:
                    errors.append(f"{tag}: CEFR darajasi notoʻgʻri.")

                options = None
                if qtype == "tfng":
                    options = TFNG
                    if answer.lower() not in {"true", "false", "ng"}:
                        errors.append(f"{tag}: javob True, False yoki Not Given boʻlishi kerak.")
                    answer = answer.lower()
                elif qtype in OPTION_TYPES:
                    raw = q.get("options")
                    options = [[str(o[0]).strip(), str(o[1]).strip()] for o in raw
                               if isinstance(o, (list, tuple)) and len(o) == 2] if isinstance(raw, list) else []
                    values = [v for v, _ in options]
                    if len(options) < 2 or any(not v or not l or len(v) > 10 for v, l in options):
                        errors.append(f"{tag}: kamida 2 ta variant kerak, har biri 'a | matn' koʻrinishida.")
                    elif len({v.lower() for v in values}) != len(values):
                        errors.append(f"{tag}: variant belgilari takrorlangan.")
                    elif answer:
                        lookup = {v.lower(): v for v in values}
                        picked = [lookup.get(a.strip().lower()) for a in answer.split("|")]
                        if None in picked:
                            errors.append(f"{tag}: toʻgʻri javob variantlar ichida yoʻq.")
                        else:
                            answer = "|".join(picked)     # store the option's exact spelling
                questions.append({"number": n, "text": text, "options": options, "answer": answer, "cefr_level": level})
            total += len(questions)
            groups.append({"qtype": qtype, "instruction": str(g.get("instruction") or "").strip(), "questions": questions})
        parts.append({"title": str((p or {}).get("title") or "").strip()[:150], "passage": passage,
                      "audio_url": audio_url, "image_url": image_url, "groups": groups})
    if total == 0:
        errors.append("Kamida bitta savol boʻlishi kerak.")
    return {"skill": skill, "title": title, "duration_min": duration, "is_active": bool(data.get("is_active")),
            "parts": parts}, errors


def apply_clean(test, clean):
    """Replace the test's whole structure with the validated data."""
    test.title, test.duration_min, test.is_active = clean["title"], clean["duration_min"], clean["is_active"]
    test.parts.clear()
    db.session.flush()
    for number, p in enumerate(clean["parts"], 1):
        part = Part(number=number, title=p["title"], passage=p["passage"], audio_url=p["audio_url"] or None,
                    image_url=p["image_url"] or None)
        for order, g in enumerate(p["groups"]):
            group = QuestionGroup(order=order, qtype=g["qtype"], instruction=g["instruction"])
            for q in sorted(g["questions"], key=lambda x: x["number"]):
                group.questions.append(Question(number=q["number"], text=q["text"], options=q["options"],
                                                answer=q["answer"], cefr_level=q["cefr_level"] or None))
            part.groups.append(group)
        test.parts.append(part)


# ------------------------------------------------------------------ routes
@bp.route("/")
@admin_required
def index():
    counts = dict(db.session.query(Attempt.test_id, func.count(Attempt.id))
                  .filter(Attempt.finished_at.isnot(None)).group_by(Attempt.test_id).all())
    rows = []
    for t in Test.query.filter(Test.skill.in_(list(SKILLS))).order_by(Test.id.desc()):
        questions = sum(len(g.questions) for p in t.parts for g in p.groups)
        rows.append({"test": t, "questions": questions, "attempts": counts.get(t.id, 0)})
    stats = {"users": User.query.count(), "tests": len(rows),
             "attempts": Attempt.query.filter(Attempt.finished_at.isnot(None)).count()}
    return render_template("admin_index.html", rows=rows, stats=stats)


@bp.route("/tests/new")
@admin_required
def new_test():
    skill = request.args.get("skill", "reading")
    if skill not in SKILLS:
        abort(404)
    blank = {"id": None, "skill": skill, "title": "", "duration_min": 45 if skill == "listening" else 60,
             "is_active": False, "parts": [
        {"title": "", "passage": "", "audio_url": "",
         "groups": [{"qtype": "mcq" if skill == "listening" else "gap_fill", "instruction": "", "questions": []}]}]}
    return render_template("admin_editor.html", data=blank, finished=0)


@bp.route("/tests/<int:test_id>/edit")
@admin_required
def edit_test(test_id):
    test = db.get_or_404(Test, test_id)
    finished = Attempt.query.filter(Attempt.test_id == test.id, Attempt.finished_at.isnot(None)).count()
    return render_template("admin_editor.html", data=test_to_dict(test), finished=finished)


@bp.route("/tests/save", methods=["POST"])
@admin_required
def save():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(errors=["Notoʻgʻri soʻrov."]), 400
    clean, errors = parse_payload(data)
    if errors:
        return jsonify(errors=errors), 400
    test_id = _int(data.get("id"))
    test = db.session.get(Test, test_id) if test_id else Test(skill=clean["skill"])
    if test is None or test.skill != clean["skill"]:
        return jsonify(errors=["Test topilmadi."]), 404
    if test.id is None:
        db.session.add(test)
    apply_clean(test, clean)
    db.session.commit()
    flash("Test saqlandi.", "ok")
    return jsonify(ok=True, redirect=url_for("admin.index"))


@bp.route("/tests/<int:test_id>/toggle", methods=["POST"])
@admin_required
def toggle(test_id):
    test = db.get_or_404(Test, test_id)
    test.is_active = not test.is_active
    db.session.commit()
    flash("Test yoqildi." if test.is_active else "Test oʻchirib qoʻyildi (foydalanuvchilarga koʻrinmaydi).", "ok")
    return redirect(url_for("admin.index"))


@bp.route("/tests/<int:test_id>/delete", methods=["POST"])
@admin_required
def delete(test_id):
    test = db.get_or_404(Test, test_id)
    if Attempt.query.filter_by(test_id=test.id).count():
        flash("Bu testni topshirgan foydalanuvchilar bor, shuning uchun oʻchirib boʻlmaydi. Uni yashirib qoʻying.", "error")
    else:
        db.session.delete(test)
        db.session.commit()
        flash("Test oʻchirildi.", "ok")
    return redirect(url_for("admin.index"))


@bp.route("/import", methods=["GET", "POST"])
@admin_required
def import_test():
    """Paste raw test text -> AI draft -> open it in the editor for review (nothing is saved yet)."""
    if request.method == "GET":
        return render_template("admin_import.html", text="", title="", duration=60)

    text = request.form.get("text", "").strip()
    title = request.form.get("title", "").strip()[:150]
    duration = _int(request.form.get("duration")) or 60

    def back(message, code):
        flash(message, "error")
        return render_template("admin_import.html", text=text, title=title, duration=duration), code

    if len(text) < 200:
        return back("Matn juda qisqa. Passage, savollar va javob kalitini toʻliq qoʻying.", 400)
    if len(text) > MAX_IMPORT_CHARS:
        return back(f"Matn juda uzun (>{MAX_IMPORT_CHARS} belgi). Testni ikkiga boʻlib import qiling.", 400)
    try:
        reply = importer.ask_json(importer.SYSTEM, text)
    except NoApiKey:
        return back("AI sozlanmagan: .env faylida OPENAI_API_KEY ni kiriting.", 503)
    except Exception:
        log.exception("AI import failed")
        return back("AI hozir javob bermadi. Matn saqlab qolindi, qayta urinib koʻring.", 502)

    raw = importer.parse_json(reply)
    if raw is None:
        return back("AI javobini oʻqib boʻlmadi. Qayta urinib koʻring.", 502)
    draft = importer.normalize(raw, title, duration)
    draft["skill"] = "reading"
    _, problems = parse_payload(draft)          # shown to the admin; the draft is kept either way
    return render_template("admin_editor.html", data=draft, finished=0, notice=True, problems=problems)


# ------------------------------------------------------------------ statistics
STATS_MIN_ATTEMPTS = 5      # a question is only flagged once at least this many students answered


def question_stats(test):
    """Per-question correct rate over all finished attempts. Helps to spot a wrong answer key or a bad question."""
    from collections import Counter
    from grading import is_correct, _show
    attempts = Attempt.query.filter(Attempt.test_id == test.id, Attempt.finished_at.isnot(None)).all()
    n = len(attempts)
    rows = []
    for part in test.parts:
        for group in part.groups:
            for q in group.questions:
                ok, wrong = 0, Counter()
                for a in attempts:
                    given = (a.answers or {}).get(f"q{q.number}", "")
                    if is_correct(given, q.answer):
                        ok += 1
                    elif given:
                        wrong[given.strip().lower()] += 1
                pct = round(100 * ok / n) if n else None
                flag = ""
                if n >= STATS_MIN_ATTEMPTS and pct is not None:
                    if pct < 20:
                        flag = "Juda qiyin: javob kaliti notoʻgʻri boʻlishi mumkin, tekshiring."
                    elif pct > 95:
                        flag = "Juda oson: ajrata olmaydi."
                top = wrong.most_common(1)
                rows.append({"number": q.number, "part": part.number, "text": q.text or "", "level": q.cefr_level or "—",
                             "key": _show(q, q.answer.split("|")[0]), "pct": pct, "flag": flag,
                             "common_wrong": f"{_show(q, top[0][0])} ({top[0][1]})" if top else "—"})
    scores = [a.scaled_score for a in attempts if a.scaled_score is not None]
    return {"attempts": n, "avg": round(sum(scores) / len(scores), 1) if scores else None, "rows": rows}


@bp.route("/tests/<int:test_id>/stats")
@admin_required
def test_stats(test_id):
    test = db.get_or_404(Test, test_id)
    return render_template("admin_test_stats.html", test=test, s=question_stats(test), min_n=STATS_MIN_ATTEMPTS)


@bp.route("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip().lower()[:80]
    query = User.query
    if q:
        query = query.filter(db.or_(func.lower(User.email).contains(q), func.lower(User.name).contains(q)))
    people = query.order_by(User.id.desc()).limit(200).all()
    done = dict(db.session.query(Attempt.user_id, func.count(Attempt.id))
                .filter(Attempt.finished_at.isnot(None)).group_by(Attempt.user_id).all())
    return render_template("admin_users.html", people=people, done=done, q=q, total=User.query.count())


# ------------------------------------------------------------------ audio upload
def _looks_like_audio(head: bytes) -> bool:
    """Check the real file signature, not just the extension (mp3, wav, ogg, m4a)."""
    return bool(head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
                or (head[:4] == b"RIFF" and head[8:12] == b"WAVE") or head[:4] == b"OggS" or head[4:8] == b"ftyp")


@bp.route("/audio", methods=["POST"])
@admin_required
def upload_audio():
    """Save one audio file for a Listening part and return its public URL."""
    f = request.files.get("file")
    ext = os.path.splitext(f.filename or "")[1].lower() if f else ""
    if not f or ext not in AUDIO_EXTS:
        return jsonify(error="Faqat mp3, m4a, wav yoki ogg fayl yuklang."), 400
    head = f.stream.read(16)
    f.stream.seek(0)
    if not _looks_like_audio(head):
        return jsonify(error="Fayl haqiqiy audio emas (mp3, m4a, wav yoki ogg boʻlishi kerak)."), 400
    os.makedirs(AUDIO_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    f.save(os.path.join(AUDIO_DIR, name))
    return jsonify(url=f"/static/audio/{name}")


def _image_ext(data):
    """File type from the CONTENT (never from the file name). SVG is refused on purpose: it can carry scripts."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":      # a real PNG starts with its header chunk
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


@bp.route("/image", methods=["POST"])
@admin_required
def upload_image():
    """Save one picture (a map or a diagram) for a test part and return its URL."""
    f = request.files.get("file")
    data = f.read(MAX_IMAGE_BYTES + 1) if f else b""
    if not data:
        return jsonify(error="Rasm tanlanmadi."), 400
    if len(data) > MAX_IMAGE_BYTES:
        return jsonify(error="Rasm juda katta (5 MB gacha)."), 413
    ext = _image_ext(data)
    if ext is None or len(data) < 100:
        return jsonify(error="Faqat PNG, JPG yoki WebP rasm yuklang."), 400
    os.makedirs(IMAGE_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(IMAGE_DIR, name), "wb") as fh:
        fh.write(data)
    return jsonify(url=f"/static/maps/{name}")


# ------------------------------------------------------------------ writing prompts
WRITING_TYPES = {"informal_letter", "formal_letter", "essay"}


@bp.route("/writing")
@admin_required
def writing_prompts():
    from writing import TASK_LABELS
    prompts = WritingPrompt.query.order_by(WritingPrompt.id.desc()).all()
    return render_template("admin_writing.html", prompts=prompts, labels=TASK_LABELS)


@bp.route("/writing/new", methods=["POST"])
@admin_required
def writing_new():
    f = request.form
    lo, hi, minutes = _int(f.get("min_words")), _int(f.get("max_words")), _int(f.get("minutes"))
    title, prompt = f.get("title", "").strip(), f.get("prompt", "").strip()
    if (f.get("task_type") not in WRITING_TYPES or not title or len(title) > 150 or len(prompt) < 20
            or None in (lo, hi, minutes) or not (10 <= lo <= hi <= 1000) or not 1 <= minutes <= 120):
        flash("Maʼlumotlar notoʻgʻri: sarlavha, matn (kamida 20 belgi) va soʻz chegaralarini tekshiring.", "error")
    else:
        db.session.add(WritingPrompt(task_type=f["task_type"], title=title, prompt=prompt,
                                     min_words=lo, max_words=hi, minutes=minutes))
        db.session.commit()
        flash("Topshiriq qoʻshildi.", "ok")
    return redirect(url_for("admin.writing_prompts"))


@bp.route("/writing/<int:prompt_id>/toggle", methods=["POST"])
@admin_required
def writing_toggle(prompt_id):
    item = db.get_or_404(WritingPrompt, prompt_id)
    item.is_active = not item.is_active
    db.session.commit()
    return redirect(url_for("admin.writing_prompts"))


@bp.route("/writing/<int:prompt_id>/delete", methods=["POST"])
@admin_required
def writing_delete(prompt_id):
    db.session.delete(db.get_or_404(WritingPrompt, prompt_id))   # results keep their own copy of the task
    db.session.commit()
    flash("Topshiriq oʻchirildi.", "ok")
    return redirect(url_for("admin.writing_prompts"))


# ------------------------------------------------------------------ speaking prompts
@bp.route("/speaking")
@admin_required
def speaking_prompts():
    from speaking import PART_LABELS
    prompts = SpeakingPrompt.query.order_by(SpeakingPrompt.id.desc()).all()
    return render_template("admin_speaking.html", prompts=prompts, labels=PART_LABELS)


@bp.route("/speaking/new", methods=["POST"])
@admin_required
def speaking_new():
    f = request.form
    part, think, speak = _int(f.get("part")), _int(f.get("think_seconds")), _int(f.get("speak_seconds"))
    title, prompt = f.get("title", "").strip(), f.get("prompt", "").strip()
    if (part not in (1, 2, 3) or not title or len(title) > 150 or len(prompt) < 10
            or think is None or speak is None or not (0 <= think <= 300) or not (15 <= speak <= 300)):
        flash("Maʼlumotlar notoʻgʻri: sarlavha, matn (kamida 10 belgi) va vaqtlarni tekshiring.", "error")
    else:
        db.session.add(SpeakingPrompt(part=part, title=title, prompt=prompt, think_seconds=think, speak_seconds=speak))
        db.session.commit()
        flash("Topshiriq qoʻshildi.", "ok")
    return redirect(url_for("admin.speaking_prompts"))


@bp.route("/speaking/<int:prompt_id>/toggle", methods=["POST"])
@admin_required
def speaking_toggle(prompt_id):
    item = db.get_or_404(SpeakingPrompt, prompt_id)
    item.is_active = not item.is_active
    db.session.commit()
    return redirect(url_for("admin.speaking_prompts"))


@bp.route("/speaking/<int:prompt_id>/delete", methods=["POST"])
@admin_required
def speaking_delete(prompt_id):
    db.session.delete(db.get_or_404(SpeakingPrompt, prompt_id))   # results keep their own copy of the task
    db.session.commit()
    flash("Topshiriq oʻchirildi.", "ok")
    return redirect(url_for("admin.speaking_prompts"))
