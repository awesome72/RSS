from pathlib import Path

from src.opml import parse_opml

OPML_PATH = Path(__file__).resolve().parent.parent / "feeds" / "stocks-kr-us-feeds.opml"


def test_parses_real_opml_into_feeds_with_expected_categories():
    feeds = parse_opml(str(OPML_PATH))
    assert len(feeds) > 0
    assert all(f.url.startswith("http") for f in feeds)

    categories = {f.category for f in feeds}
    for expected in ["국내 증시", "미국 증시", "매크로·공시", "반도체·기술", "전쟁·지정학"]:
        assert expected in categories


def test_needs_confirm_detected_from_title(tmp_path):
    opml = tmp_path / "sample.opml"
    opml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0"><body>
          <outline text="카테고리">
            <outline type="rss" title="정상 피드" xmlUrl="https://example.com/a.xml"/>
            <outline type="rss" title="의심 피드 (확인 필요)" xmlUrl="https://example.com/b.xml"/>
          </outline>
        </body></opml>""",
        encoding="utf-8",
    )

    feeds = parse_opml(str(opml))
    by_title = {f.title: f for f in feeds}

    assert by_title["정상 피드"].needs_confirm is False
    assert by_title["의심 피드 (확인 필요)"].needs_confirm is True
    assert by_title["정상 피드"].category == "카테고리"
