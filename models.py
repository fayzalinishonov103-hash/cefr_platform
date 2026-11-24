"""Database models for the CEFR AI platform."""
import hmac
import secrets
from datetime import datetime, timezone
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager


def _now():
    return datetime.now(timezone.utc)


def _naive_now():
    """Naive UTC, so comparisons behave the same on SQLite and PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_token():
    return secrets.token_hex(16)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)
    is_admin = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    telegram_id = db.Column(db.BigInteger, unique=True, index=True)   # set when the user signs in via Telegram
    # "ab@gmail.com" == "a.b+x@gmail.com": one mailbox = one account (see security.canonical_email)
    email_canon = db.Column(db.String(255), index=True)
    email_verified_at = db.Column(db.DateTime)                        # set by the e-mail code/link, or at Telegram sign-up
    # Part of the session id. Rotating it (password change/reset) signs the user out on every device.
    session_token = db.Column(db.String(32), nullable=False, default=_new_token, server_default="")
    attempts = db.relationship("Attempt", backref="user", lazy="dynamic",
                               order_by="Attempt.finished_at.desc()")

    def get_id(self):
        return f"{self.id}:{self.session_token}"

    @property
    def is_verified(self):
        """True when this account may use the paid AI features. Everybody counts as verified while verification is
        switched off (no SMTP configured); admins always do."""
        return bool(self.email_verified_at) or bool(self.is_admin) or not current_app.config.get("VERIFY_ENABLED")

    def rotate_session(self):
        self.session_token = _new_token()

    def set_password(self, raw: str):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    @property
    def current_level(self):
        """CEFR level of the most recent finished attempt (or None)."""
        last = self.attempts.filter(Attempt.finished_at.isnot(None)).first()
        return last.cefr_level if last else None


class Test(db.Model):
    """A full test for one skill (e.g. one Reading test with 5 parts)."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    skill = db.Column(db.String(20), nullable=False, index=True)  # reading/listening/writing/speaking
    duration_min = db.Column(db.Integer, default=60)
    is_active = db.Column(db.Boolean, default=True)
    parts = db.relationship("Part", backref="test", order_by="Part.number",
                            cascade="all, delete-orphan")


class Part(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey("test.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)          # 1..5
    title = db.Column(db.String(150))
    passage = db.Column(db.Text)                             # pre-formatted HTML/text from backend
    audio_url = db.Column(db.String(255))                    # used by Listening
    image_url = db.Column(db.String(255))                    # optional picture for the part: a map, a diagram (uploaded file)
    groups = db.relationship("QuestionGroup", backref="part", order_by="QuestionGroup.order",
                             cascade="all, delete-orphan")


class QuestionGroup(db.Model):
    """A block of questions sharing one instruction and one type."""
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    order = db.Column(db.Integer, default=0)
    qtype = db.Column(db.String(20), nullable=False)         # gap_fill/matching/heading/mcq/tfng
    instruction = db.Column(db.Text)
    questions = db.relationship("Question", backref="group", order_by="Question.number",
                                cascade="all, delete-orphan")


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("question_group.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)           # 1..35 across the test
    text = db.Column(db.Text)
    options = db.Column(db.JSON)                             # list for mcq/matching, else None
    answer = db.Column(db.String(200), nullable=False)       # answer key (never sent to the browser)
    cefr_level = db.Column(db.String(2))                     # A1..C2 difficulty tag


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    test_id = db.Column(db.Integer, db.ForeignKey("test.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=_now)
    finished_at = db.Column(db.DateTime)
    answers = db.Column(db.JSON)                             # {"1": "boat", "2": "B", ...}
    raw_score = db.Column(db.Integer)
    max_score = db.Column(db.Integer)
    scaled_score = db.Column(db.Float)                       # 0-75 scale
    cefr_level = db.Column(db.String(20))
    test = db.relationship("Test")


class SkillResult(db.Model):
    """AI-graded result for Writing/Speaking (used in a later stage)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    skill = db.Column(db.String(20), nullable=False)
    scaled_score = db.Column(db.Float)
    cefr_level = db.Column(db.String(20))
    feedback = db.Column(db.JSON)                            # per-criterion scores and comments
    created_at = db.Column(db.DateTime, default=_now)


@login_manager.user_loader
def load_user(user_id):
    """Session ids look like '<id>:<token>'. Old-format ids or a rotated token mean: not signed in."""
    try:
        raw_id, token = str(user_id).split(":", 1)
        user = db.session.get(User, int(raw_id))
    except (ValueError, TypeError):
        return None
    if user is None or not token or not user.session_token:
        return None
    return user if hmac.compare_digest(token, user.session_token) else None


class AuthAttempt(db.Model):
    """One failed login / forgot-password / registration request. Lives in the database so that the limits
    hold across all gunicorn workers and restarts."""
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    email = db.Column(db.String(120), index=True)
    created_at = db.Column(db.DateTime, default=_naive_now, index=True)


class UsageLog(db.Model):
    """Every paid AI call a user triggers (successful or not): the hard cost cap counts these."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    kind = db.Column(db.String(16), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_naive_now, index=True)


class HintLog(db.Model):
    """One AI hint given during an attempt (used for per-part limits and review)."""
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id"), nullable=False, index=True)
    part_number = db.Column(db.Integer, nullable=False)
    question_number = db.Column(db.Integer)                  # None = whole part
    hint = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_now)


class WritingPrompt(db.Model):
    """A Writing task (letter / essay) that students can practise."""
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(20), nullable=False)     # informal_letter / formal_letter / essay
    title = db.Column(db.String(150), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    min_words = db.Column(db.Integer, default=50)
    max_words = db.Column(db.Integer, default=100)
    minutes = db.Column(db.Integer, default=20)              # suggested time (not enforced)
    is_active = db.Column(db.Boolean, default=True)


class VocabWord(db.Model):
    """A word the student saved to the personal vocabulary notebook (Leitner-style review)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    word = db.Column(db.String(80), nullable=False)
    meaning = db.Column(db.String(200))                      # translation / note, optional
    context = db.Column(db.String(300))                      # sentence or hint it came from, optional
    box = db.Column(db.Integer, nullable=False, default=0)   # 0..4, higher = better known
    next_review = db.Column(db.DateTime, default=_now)
    created_at = db.Column(db.DateTime, default=_now)


class SpeakingPrompt(db.Model):
    """A Speaking task the student answers by recording their voice."""
    id = db.Column(db.Integer, primary_key=True)
    part = db.Column(db.Integer, nullable=False, default=1)  # 1 = questions, 2 = monologue, 3 = discussion
    title = db.Column(db.String(150), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    think_seconds = db.Column(db.Integer, default=30)        # preparation time before recording starts
    speak_seconds = db.Column(db.Integer, default=60)        # recording stops automatically after this
    is_active = db.Column(db.Boolean, default=True)


class ShadowVideo(db.Model):
    """A YouTube video listed for shadowing practice. Only the link data is stored; the video stays on YouTube."""
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(11), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False)
    channel = db.Column(db.String(120), default="")
    kind = db.Column(db.String(20), nullable=False, default="interview")   # interview / podcast / movie / talk
    level = db.Column(db.String(2), default="")                            # A1..C2 or empty
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)
    words = db.relationship("ShadowWord", backref="video", cascade="all, delete-orphan", order_by="ShadowWord.id")


class ShadowWord(db.Model):
    """A hand-written vocabulary item for one shadowing video (added by the admin)."""
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("shadow_video.id"), nullable=False, index=True)
    word = db.Column(db.String(80), nullable=False)
    meaning = db.Column(db.String(200), default="")
    example = db.Column(db.String(300), default="")


class ShadowMark(db.Model):
    """A student's personal mark on a video: kind is 'seen' or 'fav'."""
    __table_args__ = (db.UniqueConstraint("user_id", "video_id", "kind", name="uq_shadow_mark"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey("shadow_video.id"), nullable=False, index=True)
    kind = db.Column(db.String(8), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)


class ExamSession(db.Model):
    """A full mock exam: one Reading, one Listening, one Writing and one Speaking result, then an overall level.
    The sub-results are the student's normal attempts made after `started_at`; nothing is copied until the end."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=_naive_now, nullable=False)
    finished_at = db.Column(db.DateTime)
    cancelled = db.Column(db.Boolean, default=False, nullable=False)
    overall_score = db.Column(db.Float)
    overall_level = db.Column(db.String(20))
    results = db.Column(db.JSON)          # snapshot taken when the exam is completed


class MistakeFixed(db.Model):
    """A question the student answered correctly again in the mistakes notebook.
    No foreign key on purpose: editing a test in the admin replaces its questions, and that must never be blocked."""
    __table_args__ = (db.UniqueConstraint("user_id", "question_id", name="uq_mistake_fixed"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    question_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_naive_now, nullable=False)


class PracticeSet(db.Model):
    """One adaptive practice session (kind 'smart') or the day's challenge (kind 'daily'), issued to ONE user.
    The ids are stored so a submit can only answer questions that were really issued. No foreign keys on question ids:
    editing a test in the admin replaces its questions, and old sessions must keep working."""
    __table_args__ = (db.UniqueConstraint("user_id", "kind", "day", name="uq_practice_daily"),)   # day is NULL for 'smart'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(8), nullable=False)
    skill = db.Column(db.String(10), nullable=False, default="any")
    day = db.Column(db.Date)                                  # Uzbekistan calendar day, only for 'daily'
    question_ids = db.Column(db.JSON, nullable=False)
    reasons = db.Column(db.JSON)                              # {question_id: [short tags explaining why it was chosen]}
    created_at = db.Column(db.DateTime, default=_naive_now, nullable=False)
    finished_at = db.Column(db.DateTime)
    correct = db.Column(db.Integer)
    total = db.Column(db.Integer)


class PracticeLog(db.Model):
    """One answered question in an adaptive session. Feeds the mastery model next to the real test attempts."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, nullable=False, index=True)
    qtype = db.Column(db.String(20), nullable=False)
    level = db.Column(db.String(4))
    correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=_naive_now, nullable=False, index=True)


class XpEvent(db.Model):
    """Experience points. (user, reason, ref) is unique, so replaying a request can never pay out twice."""
    __table_args__ = (db.UniqueConstraint("user_id", "reason", "ref", name="uq_xp_once"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(16), nullable=False)         # test / writing / speaking / smart / daily / bonus
    ref = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=_naive_now, nullable=False, index=True)


class Badge(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "code", name="uq_badge"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    code = db.Column(db.String(24), nullable=False)
    created_at = db.Column(db.DateTime, default=_naive_now, nullable=False)


class LeaderboardMember(db.Model):
    """A student who chose to appear on the weekly leaderboard, under a nickname (never the real name or e-mail)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    nickname = db.Column(db.String(20), nullable=False)
    nick_key = db.Column(db.String(20), nullable=False, unique=True)     # lower-case, for uniqueness
    created_at = db.Column(db.DateTime, default=_naive_now, nullable=False)


class UserProfile(db.Model):
    """Answers of the post-registration onboarding. One row per user, created when they finish OR skip it.

    goal / target_level / daily_minutes / interests personalise the plan. age_range / region / source are
    statistics only and are stored ONLY when the user ticked the consent box (consent_at is set then).
    No exact birth date, phone number or address is ever collected."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    goal = db.Column(db.String(16))
    target_level = db.Column(db.String(8))                   # B1 / B2 / C1 / "" (not decided)
    exam_date = db.Column(db.Date)
    daily_minutes = db.Column(db.Integer)
    interests = db.Column(db.JSON)                           # list of option codes
    age_range = db.Column(db.String(8))
    region = db.Column(db.String(24))
    source = db.Column(db.String(16))
    consent_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)                    # None when the user skipped
    skipped_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=_naive_now, onupdate=_naive_now, nullable=False)


class BattleMatch(db.Model):
    """1v1 CEFR Quick Duel match between two students or against an AI practice rival."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, index=True, nullable=False)
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    player2_name = db.Column(db.String(80), default="Bot Rival")
    player1_score = db.Column(db.Integer, default=0)
    player2_score = db.Column(db.Integer, default=0)
    winner_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default="active")   # active, finished
    questions = db.Column(db.JSON)                        # list of 5 questions [{"q": ..., "options": [...], "answer": ...}]
    created_at = db.Column(db.DateTime, default=_now)
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])

