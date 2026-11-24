"""Check the AI Writing grader against REAL essays graded by a person, before opening the site to the public.

1) Put 10-20 real student essays into a CSV (see tools/eval_writing_template.csv). Columns:
      id, task_type (essay | formal_letter | informal_letter), task, min_words, max_words, text, human_level (A1..C2)
   human_level = the level a teacher/examiner you trust gives the essay.
2) Run (uses OPENAI_API_KEY from .env; makes real, paid API calls):
      python tools/eval_writing.py my_essays.csv --repeat 2
3) Read the summary and eval_results.csv. What to look at:
      - within-one-level %: how often the AI is at most one CEFR level away from the teacher
      - bias: positive = the AI is too generous (the dangerous direction for exam prep)
      - consistency: same essay graded twice should land on the same level
"""
import argparse
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()

ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]


def summarize(rows):
    """rows: dicts with human, ai (levels) and ai2 (optional second run). Returns summary numbers."""
    n = len(rows)
    diffs = [ORDER.index(r["ai"]) - ORDER.index(r["human"]) for r in rows]
    out = {"n": n, "exact": sum(d == 0 for d in diffs) / n, "within_one": sum(abs(d) <= 1 for d in diffs) / n,
           "bias_levels": sum(diffs) / n, "too_generous": sum(d > 0 for d in diffs), "too_strict": sum(d < 0 for d in diffs)}
    second = [r for r in rows if r.get("ai2")]
    if second:
        out["consistent"] = sum(r["ai"] == r["ai2"] for r in second) / len(second)
    return out


def grade_once(writing, row):
    prompt = SimpleNamespace(task_type=row["task_type"], prompt=row["task"], min_words=int(row["min_words"]), max_words=int(row["max_words"]))
    reply = writing.ask_grader(writing.SYSTEM, writing._user_message(prompt, row["text"]))
    raw = writing.parse_json(reply)
    grade = writing.normalize_grade(raw, row["text"], prompt.min_words) if raw else None
    return grade["level"] if grade else "ERR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--repeat", type=int, default=1, help="2 = grade every essay twice to measure consistency")
    args = ap.parse_args()
    import writing                                    # imported here so --help works without the app's packages
    results, failed = [], 0
    with open(args.csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            human = row["human_level"].strip().upper()
            if human not in ORDER:
                print(f"{row['id']}: human_level notoʻgʻri ({human}), oʻtkazib yuborildi"); continue
            ai = grade_once(writing, row)
            ai2 = grade_once(writing, row) if args.repeat > 1 else ""
            if ai == "ERR":
                failed += 1; print(f"{row['id']}: AI javobi yaroqsiz"); continue
            results.append({"id": row["id"], "human": human, "ai": ai, "ai2": ai2 if ai2 != "ERR" else ""})
            print(f"{row['id']}: oʻqituvchi {human} | AI {ai}" + (f" / {ai2}" if ai2 else ""))
    if not results:
        sys.exit("Natija yoʻq.")
    with open("eval_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "human", "ai", "ai2"]); w.writeheader(); w.writerows(results)
    s = summarize(results)
    print(f"\nInshollar: {s['n']} (xato javoblar: {failed})")
    print(f"Aniq mos: {s['exact']:.0%} | Bir daraja ichida: {s['within_one']:.0%}")
    print(f"Moyillik: {s['bias_levels']:+.2f} daraja (musbat = AI haddan ortiq saxiy); AI yuqori: {s['too_generous']}, AI past: {s['too_strict']}")
    if "consistent" in s:
        print(f"Barqarorlik (bir inshoga ikki marta bir xil daraja): {s['consistent']:.0%}")
    print("Natijalar eval_results.csv da.")


if __name__ == "__main__":
    main()
