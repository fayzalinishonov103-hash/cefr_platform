"""Shadowing: a gallery of YouTube interviews, podcasts and clips. We store only the link and title; the thumbnail
is YouTube's own image and a click opens the video on YouTube, so nothing is copied or hosted on our server."""
import json
import logging
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

import security
from extensions import db
from models import ShadowVideo, ShadowWord, ShadowMark
from admin import admin_required, LEVELS
from vocab import _save as save_vocab_word

log = logging.getLogger(__name__)

bp = Blueprint("shadowing", __name__)
admin_bp = Blueprint("admin_shadowing", __name__, url_prefix="/admin/shadowing")

KINDS = {"interview": "Intervyu", "podcast": "Podkast", "movie": "Kino / serial", "talk": "Nutq"}
_ID = r"[A-Za-z0-9_-]{11}"
_PATTERNS = [
    re.compile(r"(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:[^#]*&)?v=(" + _ID + ")"),
    re.compile(r"youtu\.be/(" + _ID + ")"),
    re.compile(r"youtube\.com/(?:shorts|embed|live|v)/(" + _ID + ")"),
]


def parse_youtube_id(text):
    """Accepts a YouTube link in any common form (or the bare 11-character id); returns the id or None."""
    text = (text or "").strip()
    if re.fullmatch(_ID, text):
        return text
    for pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def thumbnail_url(video_id):
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def watch_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_meta(video_id):
    """Title and channel from YouTube's public oEmbed endpoint (no API key). Returns {} on any failure."""
    url = "https://www.youtube.com/oembed?format=json&url=" + quote(watch_url(video_id), safe="")
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"title": str(data.get("title", ""))[:200], "channel": str(data.get("author_name", ""))[:120]}
    except Exception as exc:          # offline, private video, embedding disabled ...
        log.info("oEmbed lookup failed for %s: %s", video_id, exc)
        return {}


MARK_KINDS = {"seen", "fav"}
MAX_BULK_WORDS = 50


def parse_word_lines(text):
    """'word | translation | example' per line (tab also works). Returns [(word, meaning, example)], at most 50."""
    rows = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in re.split(r"\||\t", line)]
        word = " ".join(parts[0].split())[:80] if parts and parts[0] else ""
        if not word:
            continue
        meaning = parts[1][:200] if len(parts) > 1 else ""
        example = parts[2][:300] if len(parts) > 2 else ""
        rows.append((word, meaning, example))
        if len(rows) >= MAX_BULK_WORDS:
            break
    return rows


def _back(default):
    """Where to return after a form post; only same-site paths are accepted."""
    return security.safe_next(request.form.get("back", ""), default)


def _visible_video(video_id):
    video = db.get_or_404(ShadowVideo, video_id)
    if not (video.is_active or (current_user.is_authenticated and current_user.is_admin)):
        abort(404)
    return video


def _marks_for(user):
    """{video_id: {'seen', 'fav'}} for the signed-in student (empty for guests)."""
    out = {}
    if user.is_authenticated:
        for m in ShadowMark.query.filter_by(user_id=user.id):
            out.setdefault(m.video_id, set()).add(m.kind)
    return out


# ------------------------------------------------------------------ public
@bp.route("/shadowing")
def videos():
    kind = request.args.get("kind", "")
    level = request.args.get("level", "")
    fav = request.args.get("fav") == "1" and current_user.is_authenticated
    query = ShadowVideo.query.filter_by(is_active=True)
    if kind in KINDS:
        query = query.filter_by(kind=kind)
    else:
        kind = ""
    if level in LEVELS - {""}:
        query = query.filter_by(level=level)
    else:
        level = ""
    marks = _marks_for(current_user)
    items = query.order_by(ShadowVideo.id.desc()).all()
    if fav:
        items = [v for v in items if "fav" in marks.get(v.id, ())]
    return render_template("shadowing_list.html", items=items, kinds=KINDS, kind=kind, level=level, fav=fav,
                           levels=sorted(LEVELS - {""}), marks=marks, thumb=thumbnail_url, watch=watch_url)


@bp.route("/shadowing/<int:video_id>")
def detail(video_id):
    video = _visible_video(video_id)
    return render_template("shadowing_detail.html", v=video, kinds=KINDS, marks=_marks_for(current_user),
                           thumb=thumbnail_url, watch=watch_url)


@bp.route("/shadowing/<int:video_id>/mark/<kind>", methods=["POST"])
@login_required
def mark(video_id, kind):
    video = _visible_video(video_id)
    if kind not in MARK_KINDS:
        abort(404)
    existing = ShadowMark.query.filter_by(user_id=current_user.id, video_id=video.id, kind=kind).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(ShadowMark(user_id=current_user.id, video_id=video.id, kind=kind))
    db.session.commit()
    return redirect(_back(url_for("shadowing.videos")))


@bp.route("/shadowing/<int:video_id>/word/<int:word_id>/save", methods=["POST"])
@login_required
def save_word(video_id, word_id):
    video = _visible_video(video_id)
    w = db.session.get(ShadowWord, word_id)
    if w is None or w.video_id != video.id:
        abort(404)
    item, problem = save_vocab_word(w.word, w.meaning, w.example)
    flash(problem or f"“{w.word}” daftarga qoʻshildi.", "error" if (problem and item is None) else "ok")
    return redirect(url_for("shadowing.detail", video_id=video.id))


@bp.route("/shadowing/<int:video_id>/words/save-all", methods=["POST"])
@login_required
def save_all_words(video_id):
    video = _visible_video(video_id)
    added = skipped = 0
    for w in video.words:
        item, problem = save_vocab_word(w.word, w.meaning, w.example)
        if problem is None:
            added += 1
        else:
            skipped += 1
            if item is None:          # notebook full: stop instead of failing on every word
                break
    flash(f"{added} ta soʻz daftarga qoʻshildi" + (f", {skipped} tasi allaqachon bor edi yoki sigʻmadi." if skipped else "."), "ok")
    return redirect(url_for("shadowing.detail", video_id=video.id))


# ------------------------------------------------------------------ admin
@admin_bp.route("/")
@admin_required
def manage():
    items = ShadowVideo.query.order_by(ShadowVideo.id.desc()).all()
    return render_template("admin_shadowing.html", items=items, kinds=KINDS, levels=sorted(LEVELS - {""}),
                           thumb=thumbnail_url, watch=watch_url)


@admin_bp.route("/new", methods=["POST"])
@admin_required
def new():
    f = request.form
    video_id = parse_youtube_id(f.get("url"))
    kind, level = f.get("kind", ""), f.get("level", "")
    if not video_id:
        flash("YouTube havolasi notoʻgʻri. Masalan: https://www.youtube.com/watch?v=...", "error")
    elif kind not in KINDS or level not in LEVELS:
        flash("Turi yoki darajasi notoʻgʻri.", "error")
    elif ShadowVideo.query.filter_by(youtube_id=video_id).first():
        flash("Bu video allaqachon qoʻshilgan.", "error")
    else:
        meta = fetch_meta(video_id)
        title = f.get("title", "").strip()[:200] or meta.get("title", "")
        channel = f.get("channel", "").strip()[:120] or meta.get("channel", "")
        if not title:
            flash("Sarlavhani avtomatik olib boʻlmadi. Uni qoʻlda yozing.", "error")
        else:
            db.session.add(ShadowVideo(youtube_id=video_id, title=title, channel=channel, kind=kind, level=level))
            db.session.commit()
            flash("Video qoʻshildi.", "ok")
    return redirect(url_for("shadowing.videos") if f.get("back") == "list" else url_for("admin_shadowing.manage"))


@admin_bp.route("/<int:video_id>/toggle", methods=["POST"])
@admin_required
def toggle(video_id):
    item = db.get_or_404(ShadowVideo, video_id)
    item.is_active = not item.is_active
    db.session.commit()
    return redirect(url_for("admin_shadowing.manage"))


@admin_bp.route("/<int:video_id>/delete", methods=["POST"])
@admin_required
def delete(video_id):
    video = db.get_or_404(ShadowVideo, video_id)
    ShadowMark.query.filter_by(video_id=video.id).delete()
    db.session.delete(video)            # its words are removed with it (cascade)
    db.session.commit()
    flash("Video oʻchirildi.", "ok")
    return redirect(url_for("admin_shadowing.manage"))


@admin_bp.route("/<int:video_id>/words", methods=["GET", "POST"])
@admin_required
def words(video_id):
    video = db.get_or_404(ShadowVideo, video_id)
    if request.method == "POST":
        rows = parse_word_lines(request.form.get("lines"))
        have = {w.word.lower() for w in video.words}
        added = 0
        for word, meaning, example in rows:
            if word.lower() in have:
                continue
            have.add(word.lower())
            db.session.add(ShadowWord(video_id=video.id, word=word, meaning=meaning, example=example))
            added += 1
        db.session.commit()
        flash(f"{added} ta soʻz qoʻshildi." if added else "Yangi soʻz topilmadi. Format: soʻz | tarjima | misol", "ok" if added else "error")
        return redirect(url_for("admin_shadowing.words", video_id=video.id))
    return render_template("admin_shadowing_words.html", v=video, thumb=thumbnail_url)


@admin_bp.route("/<int:video_id>/words/<int:word_id>/delete", methods=["POST"])
@admin_required
def word_delete(video_id, word_id):
    w = db.session.get(ShadowWord, word_id)
    if w is None or w.video_id != video_id:
        abort(404)
    db.session.delete(w)
    db.session.commit()
    return redirect(url_for("admin_shadowing.words", video_id=video_id))
