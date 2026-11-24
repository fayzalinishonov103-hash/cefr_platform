"""1v1 CEFR Quick Battle (Duel) system. Real-time multiplayer & practice bot match."""
import random
import secrets
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from extensions import db
from models import BattleMatch, User
import gamify

bp = Blueprint("battle", __name__)

BATTLE_QUESTIONS = [
    {"q": "The committee decided to ___ the proposal due to lack of funding.",
     "options": ["turn down", "give in", "take over", "put off"], "answer": "turn down", "level": "B2"},
    {"q": "Had I known about the schedule change, I ___ earlier.",
     "options": ["would arrive", "would have arrived", "had arrived", "arrived"], "answer": "would have arrived", "level": "C1"},
    {"q": "She was completely ___ by the sudden turn of events.",
     "options": ["baffled", "thrilled", "relieved", "glanced"], "answer": "baffled", "level": "C1"},
    {"q": "It is essential that every applicant ___ the documents in person.",
     "options": ["submits", "submit", "submitted", "will submit"], "answer": "submit", "level": "C1"},
    {"q": "The archaeological team made a significant ___ in the desert.",
     "options": ["breakthrough", "breakdown", "breakout", "breakup"], "answer": "breakthrough", "level": "B2"},
    {"q": "He couldn't help ___ when he heard the unexpected joke.",
     "options": ["to laugh", "laughing", "laughed", "laugh"], "answer": "laughing", "level": "B1"},
    {"q": "Under no circumstances ___ allowed to enter the laboratory without a badge.",
     "options": ["visitors are", "are visitors", "visitors were", "have visitors"], "answer": "are visitors", "level": "C1"},
    {"q": "The manager apologized ___ the inconvenience caused to customers.",
     "options": ["for", "about", "to", "with"], "answer": "for", "level": "B1"},
    {"q": "His argument was sound, but it failed to ___ the jury.",
     "options": ["convince", "insist", "admit", "claim"], "answer": "convince", "level": "B2"},
    {"q": "Rarely ___ such extraordinary talent in a candidate so young.",
     "options": ["we see", "have we seen", "we saw", "we have seen"], "answer": "have we seen", "level": "C1"},
    {"q": "The new legislation is aimed ___ reducing carbon emissions.",
     "options": ["at", "on", "for", "to"], "answer": "at", "level": "B2"},
    {"q": "Despite ___ diligently for months, he found the examination challenging.",
     "options": ["study", "having studied", "to study", "studied"], "answer": "having studied", "level": "C1"},
    {"q": "She took up yoga in order to ___ stress after work.",
     "options": ["alleviate", "intensify", "accumulate", "provoke"], "answer": "alleviate", "level": "C1"},
    {"q": "No sooner had the plane landed ___ the passengers stood up.",
     "options": ["than", "when", "that", "then"], "answer": "than", "level": "B2"},
    {"q": "I'd rather you ___ your shoes at the entrance.",
     "options": ["leave", "left", "have left", "will leave"], "answer": "left", "level": "B2"},
    {"q": "The evidence presented in court was wholly ___ to the case.",
     "options": ["irrelevant", "incoherent", "illegitimate", "irrational"], "answer": "irrelevant", "level": "B2"},
    {"q": "They managed to reach the summit in ___ of the heavy blizzard.",
     "options": ["spite", "despite", "although", "even"], "answer": "spite", "level": "B1"},
    {"q": "The company’s profits have increased ___ over the last quarter.",
     "options": ["substantially", "narrowly", "scarcely", "roughly"], "answer": "substantially", "level": "B2"},
    {"q": "If it hadn't been for your assistance, we ___ the deadline.",
     "options": ["would miss", "would have missed", "will miss", "missed"], "answer": "would have missed", "level": "C1"},
    {"q": "You should take an umbrella with you in ___ it starts raining.",
     "options": ["case", "time", "order", "fact"], "answer": "case", "level": "B1"},
]

BOT_NAMES = ["Malika (B2)", "Jasur (C1)", "Azizbek (B2)", "Shahzoda (C1)", "Bobur (B1)"]


@bp.route("/battle")
@login_required
def lobby():
    # User battle stats
    user_id = current_user.id
    wins = BattleMatch.query.filter(BattleMatch.winner_id == user_id).count()
    total = BattleMatch.query.filter((BattleMatch.player1_id == user_id) | (BattleMatch.player2_id == user_id),
                                     BattleMatch.status == "finished").count()
    recent = BattleMatch.query.filter((BattleMatch.player1_id == user_id) | (BattleMatch.player2_id == user_id),
                                      BattleMatch.status == "finished").order_by(BattleMatch.id.desc()).limit(5).all()
    return render_template("battle_lobby.html", wins=wins, total=total, recent=recent)


@bp.route("/battle/start", methods=["POST"])
@login_required
def start_match():
    # Pick 5 random questions
    selected = random.sample(BATTLE_QUESTIONS, 5)
    code = secrets.token_hex(4)
    bot_name = random.choice(BOT_NAMES)
    
    match = BattleMatch(
        code=code,
        player1_id=current_user.id,
        player2_name=bot_name,
        questions=selected,
        status="active"
    )
    db.session.add(match)
    db.session.commit()
    return redirect(url_for("battle.arena", code=code))


@bp.route("/battle/<string:code>")
@login_required
def arena(code):
    match = BattleMatch.query.filter_by(code=code).first_or_404()
    if match.player1_id != current_user.id and match.player2_id != current_user.id:
        # Joining as player 2 if vacant
        if match.player2_id is None:
            match.player2_id = current_user.id
            match.player2_name = current_user.name
            db.session.commit()
    return render_template("battle_arena.html", m=match, q_list=match.questions)


@bp.route("/battle/<string:code>/submit", methods=["POST"])
@login_required
def submit_answer(code):
    match = BattleMatch.query.filter_by(code=code).first_or_404()
    if match.status == "finished":
        return jsonify(ok=True, finished=True)

    data = request.get_json(silent=True) or {}
    score = int(data.get("score", 0))

    # Calculate rival bot score (simulated realistic CEFR performance: 3 to 5 correct)
    bot_score = random.randint(3, 5)

    if match.player1_id == current_user.id:
        match.player1_score = score
        match.player2_score = bot_score
        match.winner_id = current_user.id if score >= bot_score else (match.player2_id or 0)
    else:
        match.player2_score = score
        match.winner_id = current_user.id if score > match.player1_score else match.player1_id

    match.status = "finished"
    db.session.commit()

    # Award gamification XP
    if match.winner_id == current_user.id:
        try:
            gamify.award_xp(current_user.id, 25, "1v1 Jangda gʻalaba qozondi!")
        except Exception:
            pass

    return jsonify(ok=True, winner_id=match.winner_id, p1_score=match.player1_score, p2_score=match.player2_score)
