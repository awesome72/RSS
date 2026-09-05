"""피드 수집, 중복 제거, 정규화."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict

import feedparser
import httpx

from .opml import Feed
from . import state as st


@dataclass
class Article:
    title: str
    link: str
    outlet: str
    category: str
    published: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


def _entry_field(entry, *names: str, default: str = "") -> str:
    for name in names:
        value = entry.get(name)
        if value:
            return value
    return default


async def _fetch_one(
    client: httpx.AsyncClient,
    feed: Feed,
    sem: asyncio.Semaphore,
    timeout: float,
) -> tuple[Feed, list, Exception | None]:
    async with sem:
        try:
            resp = await client.get(feed.url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            parsed = await asyncio.to_thread(feedparser.parse, resp.content)
            if parsed.bozo and not parsed.entries:
                raise parsed.bozo_exception or ValueError("feed parse failed")
            return feed, parsed.entries, None
        except Exception as exc:  # noqa: BLE001 - 개별 피드 실패는 기록만 하고 계속 진행
            return feed, [], exc


async def collect_all(
    feeds: list[Feed],
    config: dict,
) -> tuple[list[Article], dict]:
    """모든 피드를 병렬 수집한다. 개별 실패는 건너뛰고 stats에 기록한다."""

    feed_cfg = config.get("feed", {})
    timeout = float(feed_cfg.get("timeout_seconds", 10))
    max_concurrency = int(feed_cfg.get("max_concurrency", 8))
    user_agent = feed_cfg.get("user_agent", "rss-discord-newsletter/1.0")

    health = st.load_health()
    active_feeds = [f for f in feeds if not st.is_disabled(health, f.url)]

    sem = asyncio.Semaphore(max_concurrency)
    articles: list[Article] = []
    stats = {
        "total_feeds": len(feeds),
        "skipped_disabled": len(feeds) - len(active_feeds),
        "success": 0,
        "failed": [],
        "newly_disabled": [],
        "raw_entries": 0,
    }

    async with httpx.AsyncClient(headers={"User-Agent": user_agent}) as client:
        tasks = [_fetch_one(client, feed, sem, timeout) for feed in active_feeds]
        results = await asyncio.gather(*tasks)

    for feed, entries, error in results:
        success = error is None
        newly_disabled = st.record_result(health, feed.url, success)
        if newly_disabled:
            stats["newly_disabled"].append(feed.title)
        if not success:
            stats["failed"].append({"feed": feed.title, "error": str(error)})
            continue

        stats["success"] += 1
        stats["raw_entries"] += len(entries)
        for entry in entries:
            link = _entry_field(entry, "link")
            if not link:
                continue
            title = _entry_field(entry, "title")
            description = _entry_field(entry, "summary", "description")
            published = _entry_field(entry, "published", "updated")
            articles.append(
                Article(
                    title=title,
                    link=link,
                    outlet=feed.title,
                    category=feed.category,
                    published=published,
                    description=description,
                )
            )

    current_urls = {f.url for f in feeds}
    health = {url: v for url, v in health.items() if url in current_urls}
    st.save_health(health)
    return articles, stats


def dedupe_and_filter(articles: list[Article], seen: dict, config: dict) -> list[Article]:
    min_title_length = int(config.get("min_title_length", 0))
    mute_keywords = config.get("keywords_mute", [])

    fresh: list[Article] = []
    for article in articles:
        if st.is_seen(seen, article.link):
            continue
        if len(article.title) < min_title_length:
            continue
        if any(kw in article.title or kw in article.description for kw in mute_keywords):
            continue
        fresh.append(article)
    return fresh


def select_digest_groups(
    pending: list[dict],
    boost_keywords: list[str],
    max_headlines: int,
    max_per_category: int,
) -> dict[str, list[dict]]:
    """다이제스트에 포함할 기사를 카테고리별로 고른다.

    boost 점수로 전체를 정렬한 뒤 앞에서부터 max_headlines개를 자르면 기사量이 많은
    카테고리가 슬롯을 독점해 다른 카테고리가 통째로 빠질 수 있다 (실제로 발생했던 버그).
    대신 카테고리별로 라운드로빈으로 한 건씩 배분해 모든 카테고리가 최소한의 지분을
    갖도록 보장한다.
    """

    def boost_score(article: dict) -> int:
        text = article["title"] + article.get("description", "")
        return -sum(1 for kw in boost_keywords if kw in text)

    by_category: dict[str, list[dict]] = {}
    for article in sorted(pending, key=boost_score):
        by_category.setdefault(article.get("category", "기타"), []).append(article)
    for articles in by_category.values():
        del articles[max_per_category:]

    groups: dict[str, list[dict]] = {cat: [] for cat in by_category}
    total = 0
    progressed = True
    while total < max_headlines and progressed:
        progressed = False
        for cat, queue in by_category.items():
            if total >= max_headlines:
                break
            if queue:
                groups[cat].append(queue.pop(0))
                total += 1
                progressed = True

    return {cat: articles for cat, articles in groups.items() if articles}
