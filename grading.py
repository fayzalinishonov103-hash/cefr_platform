"""Answer-key grading for Reading tests (runs on the server only)."""
import re

LEVEL_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]


def _norm(text) -> str:
    """Lower-case, collapse spaces, drop a trailing full stop."""
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip(".")


def is_correct(given, key: str) -> bool:
    """`key` may hold several accepted answers separated by '|'."""
    return _norm(given) in {_norm(k) for k in key.split("|")}


def _show(question, value: str) -> str:
    """Human-friendly text for a stored answer value."""
    if not value:
        return "—"
    labels = {v: l for v, l in (question.options or [])}
    if value in labels:
        if len(value) == 1:
            return value.upper() if labels[value].strip().lower() == value.lower() else f"{value.upper()}. {labels[value]}"
        return labels[value]
    return value


def grade(test, answers: dict) -> dict:
    """Compare `answers` ({"q1": "boat", ...}) with the key of every question."""
    review, levels = [], {}
    for part in test.parts:
        for group in part.groups:
            for q in group.questions:
                given = answers.get(f"q{q.number}", "")
                ok = is_correct(given, q.answer)
                key_first = q.answer.split("|")[0]
                review.append({
                    "number": q.number, "part": part.number, "text": q.text or "",
                    "given": _show(q, given), "correct": _show(q, key_first),
                    "ok": ok, "empty": not given, "level": q.cefr_level,
                })
                bucket = levels.setdefault(q.cefr_level or "?", [0, 0])
                bucket[1] += 1
                bucket[0] += int(ok)
    raw = sum(r["ok"] for r in review)
    by_level = [(lv, *levels[lv]) for lv in LEVEL_ORDER if lv in levels]
    return {"raw": raw, "max": len(review), "review": review, "by_level": by_level}
