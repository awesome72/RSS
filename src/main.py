"""CLI 엔트리포인트.

python -m src.main collect            # 2시간마다: 수집 + 대기열 적재
python -m src.main digest              # 하루 1회: AI 요약 후 다이제스트 발송
python -m src.main health              # 피드 생존 확인만, 전송 없음
python -m src.main <sub> --dry-run     # Discord 전송 대신 stdout 출력
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import yaml

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from . import discord as dc
from . import state as st
from .collector import collect_all, dedupe_and_filter
from .opml import parse_opml
from .summarizer import summarize

ROOT = Path(__file__).resolve().parent.parent
OPML_PATH = ROOT / "feeds" / "stocks-kr-us-feeds.opml"
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _env(name: str) -> str:
    return os.environ.get(name, "")


def cmd_collect(dry_run: bool) -> None:
    config = load_config()
    feeds = parse_opml(str(OPML_PATH))

    seen = st.load_seen()
    first_run = len(seen) == 0

    articles, stats = asyncio.run(collect_all(feeds, config))
    fresh = dedupe_and_filter(articles, seen, config)

    for article in articles:
        st.mark_seen(seen, article.link)
    seen = st.prune_seen(seen, config.get("seen_retention_days", 30))
    st.save_seen(seen)

    if first_run:
        stats["new_articles"] = 0
        stats["run_title"] = "초기화 실행 (첫 실행)"
        print(
            f"[collect] 첫 실행 감지: seen.json을 {len(seen)}건으로 채우고 "
            "이번 회차는 전송을 건너뜁니다.",
            file=sys.stderr,
        )
    else:
        pending = st.load_pending()
        pending.extend(a.to_dict() for a in fresh)
        st.save_pending(pending)
        stats["new_articles"] = len(fresh)
        stats["run_title"] = "수집 실행 로그"

    dc.send(_env("DISCORD_WEBHOOK_LOG"), dc.build_log_message(stats), dry_run)


def cmd_digest(dry_run: bool) -> None:
    config = load_config()
    pending = st.load_pending()

    if not pending:
        log_stats = {
            "total_feeds": 0,
            "success": 0,
            "new_articles": 0,
            "run_title": "다이제스트 실행 로그 — 신규 기사 없음",
        }
        dc.send(_env("DISCORD_WEBHOOK_LOG"), dc.build_log_message(log_stats), dry_run)
        print("[digest] 대기 중인 신규 기사가 없어 다이제스트를 건너뜁니다.", file=sys.stderr)
        return

    boost_keywords = config.get("keywords_boost", [])

    def boost_score(article: dict) -> int:
        text = article["title"] + article.get("description", "")
        return -sum(1 for kw in boost_keywords if kw in text)

    pending_sorted = sorted(pending, key=boost_score)

    result, ai_ok = summarize(pending_sorted, config)
    max_topics = config.get("digest", {}).get("max_topics", 7)
    topics = result.get("topics", [])[:max_topics]

    messages = dc.build_digest_messages(topics, {"collected": len(pending)}, ai_ok)
    dc.send_all(_env("DISCORD_WEBHOOK_DIGEST"), messages, dry_run)

    log_stats = {
        "total_feeds": 0,
        "success": len(pending),
        "new_articles": len(pending),
        "run_title": "다이제스트 실행 로그" + ("" if ai_ok else " — AI 요약 실패, 폴백 사용"),
    }
    dc.send(_env("DISCORD_WEBHOOK_LOG"), dc.build_log_message(log_stats), dry_run)

    if not dry_run:
        st.clear_pending()


def cmd_health(dry_run: bool) -> None:
    config = load_config()
    feeds = parse_opml(str(OPML_PATH))
    _, stats = asyncio.run(collect_all(feeds, config))

    health = st.load_health()
    print(f"{'FEED':<45} {'STATUS':<8} {'SUCCESS':<8} {'FAIL':<6} {'DISABLED'}")
    for feed in feeds:
        h = health.get(feed.url, {"success": 0, "fail": 0, "disabled": False})
        status = "DISABLED" if h["disabled"] else ("OK" if h["success"] else "FAIL")
        print(f"{feed.title[:45]:<45} {status:<8} {h['success']:<8} {h['fail']:<6} {h['disabled']}")

    print()
    print(f"총 {stats['total_feeds']}개 피드 중 {stats['success']}개 성공, {len(stats['failed'])}개 실패")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.main")
    parser.add_argument("--dry-run", action="store_true", default=False)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("collect", "digest", "health"):
        p = sub.add_parser(name)
        p.add_argument("--dry-run", action="store_true", default=False)

    args = parser.parse_args()
    dry_run = args.dry_run

    if args.command == "collect":
        cmd_collect(dry_run)
    elif args.command == "digest":
        cmd_digest(dry_run)
    elif args.command == "health":
        cmd_health(dry_run)


if __name__ == "__main__":
    main()
