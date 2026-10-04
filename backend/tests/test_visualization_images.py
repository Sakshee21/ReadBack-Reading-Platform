from scripts.visualization_images import CHAPTER_IMAGE_RE, detect_image_type, entry_key

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
GIF = b"GIF89a" + b"0" * 100
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 100


def test_detects_real_image_types():
    assert detect_image_type(JPEG) == ".jpg"
    assert detect_image_type(PNG) == ".png"
    assert detect_image_type(GIF) == ".gif"
    assert detect_image_type(WEBP) == ".webp"


def test_rejects_non_images():
    # an HTML error page served with a 200 is the realistic failure mode
    assert detect_image_type(b"<!DOCTYPE html><html>404</html>") is None
    assert detect_image_type(b"") is None


def test_entry_key_identifies_session_without_db_ids():
    entry = {
        "book_gutenberg_id": 74,
        "chapter_index": 3,
        "micro_session_index": 1,
        "source_url": "http://example.test/x.jpg",
    }
    assert entry_key(entry) == (74, 3, 1)


def test_chapter_image_regex_extracts_chapter_number():
    html = '<img src="images/03-033.jpg" alt="x"> <img src="images/cover.jpg">'
    matches = CHAPTER_IMAGE_RE.findall(html)
    assert matches == [("images/03-033.jpg", "03")]


def test_chapter_image_regex_ignores_unnumbered_art():
    html = '<img src="images/frontispiece.jpg"><img src="images/spine.jpg">'
    assert CHAPTER_IMAGE_RE.findall(html) == []
