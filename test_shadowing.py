from shadowing import parse_youtube_id


def test_parse_youtube_links():
    vid = "dQw4w9WgXcQ"
    assert parse_youtube_id(f"https://www.youtube.com/watch?v={vid}") == vid
    assert parse_youtube_id(f"https://youtu.be/{vid}?t=10") == vid
    assert parse_youtube_id(f"https://www.youtube.com/watch?feature=share&v={vid}&t=5") == vid
    assert parse_youtube_id(f"https://youtube.com/shorts/{vid}") == vid
    assert parse_youtube_id(vid) == vid


def test_reject_other_sites_and_garbage():
    assert parse_youtube_id("https://evil.com/?v=dQw4w9WgXcQ") is None
    assert parse_youtube_id("hello") is None
    assert parse_youtube_id("") is None


def test_parse_word_lines():
    from shadowing import parse_word_lines
    rows = parse_word_lines("reluctant | istamaydigan | She was reluctant.\n\n  take   for granted | e'tiborsiz qoldirmoq\n | no word\nplain")
    assert rows == [("reluctant", "istamaydigan", "She was reluctant."),
                    ("take for granted", "e'tiborsiz qoldirmoq", ""),
                    ("plain", "", "")]
    assert len(parse_word_lines("\n".join(f"w{i}" for i in range(80)))) == 50
