"""Admin pages that use AI to draft content: Listening tests (questions + audio) and Speaking tasks."""
import logging

from flask import Blueprint, render_template, request, flash, jsonify
from flask_login import current_user

import generator
import security
from admin import admin_required, parse_payload, AUDIO_DIR, _int
from ai_hint import NoApiKey

bp = Blueprint("admin_ai", __name__, url_prefix="/admin")
log = logging.getLogger(__name__)

MAX_PARTS, MIN_CHARS, MAX_CHARS = 4, 150, 6000
GEN_PER_DAY = 40                      # AI calls per admin per 24 h (each part = 1 call, plus audio)


def _blank_form():
    return {"title": "", "duration": 30, "audio": True,
            "parts": [{"title": "", "script": "", "count": 5} for _ in range(MAX_PARTS)]}


def _read_form():
    form = _blank_form()
    form["title"] = request.form.get("title", "").strip()[:150]
    form["duration"] = _int(request.form.get("duration")) or 30
    form["audio"] = request.form.get("audio") == "1"
    for i in range(MAX_PARTS):
        form["parts"][i] = {"title": request.form.get(f"title_{i}", "").strip()[:150],
                            "script": request.form.get(f"script_{i}", "").strip(),
                            "count": min(max(_int(request.form.get(f"count_{i}")) or 5, 3), 10)}
    return form


@bp.route("/listening/generate", methods=["GET", "POST"])
@admin_required
def listening_generate():
    """Transcripts -> AI questions (+ TTS audio) -> editor draft. Nothing is saved until the admin presses SAVE."""
    if request.method == "GET":
        return render_template("admin_listening_gen.html", form=_blank_form(), max_chars=MAX_CHARS, min_chars=MIN_CHARS)

    form = _read_form()
    filled = [(i, p) for i, p in enumerate(form["parts"]) if p["script"]]

    def back(message, code):
        flash(message, "error")
        return render_template("admin_listening_gen.html", form=form, max_chars=MAX_CHARS, min_chars=MIN_CHARS), code

    if not filled:
        return back("Kamida bitta part uchun transkript kiriting.", 400)
    for i, p in filled:
        if not MIN_CHARS <= len(p["script"]) <= MAX_CHARS:
            return back(f"Part {i + 1}: transkript {MIN_CHARS} dan {MAX_CHARS} gacha belgi boʻlsin (hozir {len(p['script'])}).", 400)

    parts, notes = [], []
    for n, (i, p) in enumerate(filled, start=1):
        if not security.ai_budget_ok(current_user.id, "gen", GEN_PER_DAY):
            return back("Bugungi AI limiti tugadi. Ertaga davom ettiring.", 429)
        try:
            groups, dropped = generator.generate_questions(p["script"], p["count"], p["title"])
        except NoApiKey:
            return back("AI sozlanmagan: .env faylida OPENAI_API_KEY ni kiriting.", 503)
        except generator.GenerationError:
            return back(f"Part {n}: AI yaroqli savollar tuzolmadi. Transkriptni tekshirib, qayta urinib koʻring.", 502)
        except Exception:
            log.exception("Listening question generation failed")
            return back("AI hozir javob bermadi. Kiritganlaringiz saqlab qolindi, qayta urinib koʻring.", 502)
        if dropped:
            notes.append(f"Part {n}: javobi transkriptda topilmagan {dropped} ta savol olib tashlandi.")

        audio_url = ""
        if form["audio"]:
            try:
                audio_url = generator.save_audio(generator.synthesize(p["script"]), AUDIO_DIR)
            except NoApiKey:
                return back("AI sozlanmagan: .env faylida OPENAI_API_KEY ni kiriting.", 503)
            except Exception:
                log.exception("TTS failed")
                notes.append(f"Part {n}: audio yaratilmadi. Muharrirda audioni qoʻlda yuklang.")
        parts.append({"title": p["title"] or f"Part {n}", "passage": p["script"], "audio_url": audio_url, "groups": groups})

    generator.renumber(parts)
    draft = {"id": None, "skill": "listening", "title": form["title"] or "Yangi Listening testi",
             "duration_min": form["duration"], "is_active": False, "parts": parts}
    _, problems = parse_payload(draft)
    return render_template("admin_editor.html", data=draft, finished=0, notice=True, problems=notes + problems)


@bp.route("/speaking/draft", methods=["POST"])
@admin_required
def speaking_draft():
    """JSON in ({part, topic}) -> JSON out ({title, prompt, think_seconds, speak_seconds}); the form is filled, not saved."""
    data = request.get_json(silent=True) or {}
    part, topic = _int(data.get("part")), str(data.get("topic") or "").strip()[:200]
    if part not in generator.SPEAKING_TIMES or len(topic) < 3:
        return jsonify(error="Part (1-3) va mavzu (kamida 3 belgi) kerak."), 400
    if not security.ai_budget_ok(current_user.id, "gen", GEN_PER_DAY):
        return jsonify(error="Bugungi AI limiti tugadi."), 429
    try:
        return jsonify(generator.draft_speaking(part, topic))
    except NoApiKey:
        return jsonify(error="AI sozlanmagan: .env faylida OPENAI_API_KEY ni kiriting."), 503
    except generator.GenerationError:
        return jsonify(error="AI yaroqli topshiriq tuzolmadi. Mavzuni oʻzgartirib koʻring."), 502
    except Exception:
        log.exception("Speaking draft failed")
        return jsonify(error="AI hozir javob bermadi. Qayta urinib koʻring."), 502
