import time

from src import state as st


def test_normalize_url_strips_utm_and_fragment():
    url = "https://example.com/a?utm_source=x&id=1#top"
    assert st.normalize_url(url) == "https://example.com/a?id=1"


def test_hash_url_is_deterministic_and_utm_insensitive():
    a = "https://example.com/a?utm_source=x&id=1"
    b = "https://example.com/a?id=1&utm_medium=y"
    assert st.hash_url(a) == st.hash_url(b)


def test_mark_seen_and_is_seen_roundtrip():
    seen: dict = {}
    st.mark_seen(seen, "https://example.com/a")
    assert st.is_seen(seen, "https://example.com/a")
    assert not st.is_seen(seen, "https://example.com/b")


def test_prune_seen_drops_only_old_entries():
    now = time.time()
    seen = {
        "old": {"url": "https://example.com/old", "first_seen": now - 40 * 86400},
        "new": {"url": "https://example.com/new", "first_seen": now},
    }
    pruned = st.prune_seen(seen, retention_days=30)
    assert "new" in pruned
    assert "old" not in pruned


def test_record_result_disables_any_feed_after_three_consecutive_failures():
    health: dict = {}
    url = "https://example.com/feed.xml"

    assert st.record_result(health, url, success=False) is False
    assert st.record_result(health, url, success=False) is False
    assert st.record_result(health, url, success=False) is True
    assert health[url]["disabled"] is True


def test_record_result_resets_streak_on_success():
    health: dict = {}
    url = "https://example.com/feed.xml"

    st.record_result(health, url, success=False)
    st.record_result(health, url, success=False)
    st.record_result(health, url, success=True)

    assert health[url]["consecutive_fail"] == 0
    assert health[url]["disabled"] is False
