from src import state as st
from src.collector import Article, dedupe_and_filter, select_digest_groups


def _article(title, link, category="국내 증시", description=""):
    return Article(
        title=title, link=link, outlet="테스트", category=category, published="", description=description
    )


def test_dedupe_and_filter_skips_seen_short_and_muted_articles():
    seen: dict = {}
    st.mark_seen(seen, "https://example.com/seen")

    articles = [
        _article("이미 본 기사입니다", "https://example.com/seen"),
        _article("짧음", "https://example.com/short"),
        _article("부고 기사 테스트입니다", "https://example.com/muted"),
        _article("정상적인 새 기사 제목입니다", "https://example.com/fresh"),
    ]
    config = {"min_title_length": 10, "keywords_mute": ["부고"]}

    fresh = dedupe_and_filter(articles, seen, config)

    assert [a.link for a in fresh] == ["https://example.com/fresh"]


def test_select_digest_groups_prevents_category_starvation():
    """회귀 테스트: 실제로 겪었던 버그 — 카테고리 하나가 슬롯을 독점해선 안 된다."""
    pending = (
        [{"title": f"국내 기사 {i}", "category": "국내 증시", "description": ""} for i in range(50)]
        + [{"title": f"미국 기사 {i}", "category": "미국 증시", "description": ""} for i in range(3)]
        + [{"title": f"전쟁 기사 {i}", "category": "전쟁·지정학", "description": ""} for i in range(2)]
    )

    groups = select_digest_groups(pending, boost_keywords=[], max_headlines=10, max_per_category=15)

    assert "미국 증시" in groups
    assert "전쟁·지정학" in groups
    assert sum(len(a) for a in groups.values()) == 10


def test_select_digest_groups_respects_per_category_cap():
    pending = [{"title": f"기사 {i}", "category": "국내 증시", "description": ""} for i in range(30)]
    groups = select_digest_groups(pending, boost_keywords=[], max_headlines=100, max_per_category=5)
    assert len(groups["국내 증시"]) == 5


def test_select_digest_groups_boosts_keyword_matches_first():
    pending = [
        {"title": "일반 기사", "category": "국내 증시", "description": ""},
        {"title": "반도체 훈풍 기사", "category": "국내 증시", "description": ""},
    ]
    groups = select_digest_groups(pending, boost_keywords=["반도체"], max_headlines=1, max_per_category=5)
    assert groups["국내 증시"][0]["title"] == "반도체 훈풍 기사"
