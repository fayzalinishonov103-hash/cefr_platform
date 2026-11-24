"""Skills profile (Reading + Writing side by side, overall CEFR, growth chart) and weak-area analysis."""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from cefr import scaled_to_level
from grading import is_correct, LEVEL_ORDER
from models import Attempt, SkillResult, Test

bp = Blueprint("skills", __name__)

QTYPE_LABELS = {"gap_fill": "Gap fill (boʻsh joyni toʻldirish)", "match": "Matching information",
                "heading": "Matching headings", "mcq": "Multiple choice", "tfng": "True / False / Not Given",
                "map": "Map labelling (xarita)"}
MIN_SAMPLE = 3          # a weak-area verdict needs at least this many answered questions
ATTEMPTS_LOOKBACK = 20


def _test_history(user, skill):
    """Finished attempts of one test skill (reading / listening), oldest first."""
    rows = (Attempt.query.join(Test, Test.id == Attempt.test_id)
            .filter(Attempt.user_id == user.id, Attempt.finished_at.isnot(None),
                    Attempt.scaled_score.isnot(None), Test.skill == skill)
            .order_by(Attempt.finished_at.asc()).all())
    return [(a.finished_at, a.scaled_score) for a in rows]


def _skill_history(user, skill):
    rows = (SkillResult.query.filter_by(user_id=user.id, skill=skill)
            .order_by(SkillResult.created_at.asc()).all())
    return [(r.created_at, r.scaled_score) for r in rows if r.scaled_score is not None]


def _writing_history(user):
    return _skill_history(user, "writing")


def build_chart(series, width=640, height=220, pad=28):
    """Server-side SVG coordinates: {name: [(date, score), ...]} -> {name: {points, dots}}. X is the attempt order."""
    longest = max((len(v) for v in series.values()), default=0)
    out = {}
    for name, values in series.items():
        dots = []
        for i, (when, score) in enumerate(values):
            x = pad + ((width - 2 * pad) * i / (longest - 1) if longest > 1 else (width - 2 * pad) / 2)
            y = height - pad - (height - 2 * pad) * (score / 75)
            dots.append({"x": round(x, 1), "y": round(y, 1), "score": score, "date": when.strftime("%d.%m")})
        out[name] = {"dots": dots, "points": " ".join(f"{d['x']},{d['y']}" for d in dots)}
    return out


def skills_profile(user):
    history = {"reading": _test_history(user, "reading"), "listening": _test_history(user, "listening"),
               "writing": _writing_history(user), "speaking": _skill_history(user, "speaking")}
    latest = {k: (v[-1][1] if v else None) for k, v in history.items()}
    known = [v for v in latest.values() if v is not None]
    overall = round(sum(known) / len(known), 1) if known else None
    return {
        "latest": latest, "levels": {k: scaled_to_level(v) if v is not None else None for k, v in latest.items()},
        "counts": {k: len(v) for k, v in history.items()},
        "overall": overall, "overall_level": scaled_to_level(overall) if overall is not None else None,
        "chart": build_chart({k: v[-10:] for k, v in history.items()}),
        "chart_size": (640, 220, 28),
    }


def weak_areas(user, skill="reading"):
    """Wrong-answer rate by question type and by question level over the latest finished attempts of one skill."""
    attempts = (Attempt.query.join(Test, Test.id == Attempt.test_id)
                .filter(Attempt.user_id == user.id, Attempt.finished_at.isnot(None), Test.skill == skill)
                .order_by(Attempt.finished_at.desc()).limit(ATTEMPTS_LOOKBACK).all())
    by_type, by_level = {}, {}
    for a in attempts:
        answers = a.answers or {}
        for part in a.test.parts:
            for group in part.groups:
                for q in group.questions:
                    ok = is_correct(answers.get(f"q{q.number}", ""), q.answer)
                    for bucket, key in ((by_type, group.qtype), (by_level, q.cefr_level or "?")):
                        row = bucket.setdefault(key, [0, 0])
                        row[1] += 1
                        row[0] += int(ok)

    def rows(bucket, label, order=None):
        keys = [k for k in (order or sorted(bucket)) if k in bucket]
        items = [{"key": k, "label": label(k), "ok": bucket[k][0], "total": bucket[k][1],
                  "wrong_pct": round(100 * (bucket[k][1] - bucket[k][0]) / bucket[k][1]),
                  "enough": bucket[k][1] >= MIN_SAMPLE} for k in keys]
        return items

    types = rows(by_type, lambda k: QTYPE_LABELS.get(k, k))
    levels = rows(by_level, lambda k: k, LEVEL_ORDER + ["?"])
    ranked = sorted((t for t in types if t["enough"] and t["wrong_pct"] >= 25), key=lambda t: -t["wrong_pct"])
    insights = [f"{t['label']} savollarida {t['wrong_pct']}% xato qilyapsiz ({t['total'] - t['ok']}/{t['total']})." for t in ranked[:3]]
    hard = [l for l in levels if l["enough"] and l["wrong_pct"] >= 50 and l["key"] != "?"]
    insights += [f"{l['label']} darajadagi savollarda {l['wrong_pct']}% xato bor, shu darajani mashq qiling." for l in hard[:2]]
    return {"types": sorted(types, key=lambda t: -t["wrong_pct"]), "levels": levels, "insights": insights,
            "attempts": len(attempts)}


@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", p=skills_profile(current_user), w=weak_areas(current_user))
