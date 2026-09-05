"""Discord Embed 빌드 + 웹훅 전송 (rate limit 준수)."""

from __future__ import annotations

import time

import httpx

CATEGORY_COLOR = {
    "국내 증시": 0x2A9D99,
    "미국 증시": 0x62AEF0,
    "매크로·공시": 0x391C57,
    "반도체·기술": 0x1AAE39,
    "전쟁·지정학": 0x523410,
}
DEFAULT_CATEGORY_COLOR = 0x615D59

MAX_EMBEDS_PER_MESSAGE = 10
MAX_DESCRIPTION_LEN = 4096
MAX_CONTENT_LEN = 2000
# Discord caps the *sum* of all embed text in one message at 6000 chars.
# Google News bypass links alone run 300+ chars, so leave real headroom.
MAX_TOTAL_EMBED_LEN = 5500


def _build_category_embed(category: str, articles: list[dict]) -> dict:
    lines = [f"• [{a['title']}]({a['link']}) — {a.get('outlet', '')}" for a in articles]

    description = "\n".join(lines)
    if len(description) > MAX_DESCRIPTION_LEN:
        kept, total = [], 0
        for i, line in enumerate(lines):
            note = f"…외 {len(lines) - i}건 생략"
            if total + len(line) + 1 + len(note) + 1 > MAX_DESCRIPTION_LEN:
                kept.append(note)
                break
            kept.append(line)
            total += len(line) + 1
        description = "\n".join(kept)

    return {
        "title": category[:256],
        "description": description,
        "color": CATEGORY_COLOR.get(category, DEFAULT_CATEGORY_COLOR),
    }


def _pack_messages(embeds: list[dict]) -> list[list[dict]]:
    """embeds-per-message(10)와 총 글자수(6000) 제한을 모두 지키며 묶는다."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0

    for embed in embeds:
        embed_len = len(embed["title"]) + len(embed["description"])
        if current and (len(current) >= MAX_EMBEDS_PER_MESSAGE or current_len + embed_len > MAX_TOTAL_EMBED_LEN):
            chunks.append(current)
            current, current_len = [], 0
        current.append(embed)
        current_len += embed_len

    if current:
        chunks.append(current)
    return chunks


def build_digest_messages(groups: dict[str, list[dict]], collected: int) -> list[dict]:
    """카테고리별 헤드라인 다이제스트 메시지들(헤더 + embed 청크)을 만든다. AI 요약 없음 — 제목/출처/링크만."""
    headline_count = sum(len(articles) for articles in groups.values())
    header = (
        f"📬 **일일 다이제스트** — 수집 {collected}건 · "
        f"헤드라인 {headline_count}건 · {len(groups)}개 카테고리"
    )[:MAX_CONTENT_LEN]

    embeds = [_build_category_embed(category, articles) for category, articles in groups.items()]

    messages = []
    for i, chunk in enumerate(_pack_messages(embeds)):
        msg = {"embeds": chunk}
        if i == 0:
            msg["content"] = header
        messages.append(msg)

    if not messages:
        messages.append({"content": header})

    return messages


def build_log_message(stats: dict) -> dict:
    failed = stats.get("failed", [])
    disabled = stats.get("newly_disabled", [])

    lines = [
        f"총 피드: {stats.get('total_feeds', 0)}",
        f"성공: {stats.get('success', 0)}",
        f"신규 기사: {stats.get('new_articles', stats.get('raw_entries', 0))}",
    ]
    if stats.get("skipped_disabled"):
        lines.append(f"비활성화되어 건너뜀: {stats['skipped_disabled']}")
    if failed:
        lines.append("")
        lines.append("**실패한 피드:**")
        for f in failed[:20]:
            lines.append(f"- {f['feed']}: {f['error'][:100]}")
    if disabled:
        lines.append("")
        lines.append("**이번에 비활성화된 피드 (3회 연속 실패):**")
        for name in disabled:
            lines.append(f"- {name}")

    color = 0xE74C3C if failed else 0x2ECC71
    embed = {
        "title": stats.get("run_title", "실행 로그"),
        "description": "\n".join(lines)[:MAX_DESCRIPTION_LEN],
        "color": color,
    }
    return {"embeds": [embed]}


def send(webhook_url: str, payload: dict, dry_run: bool) -> None:
    if dry_run or not webhook_url:
        import json

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    with httpx.Client() as client:
        for attempt in range(3):
            resp = client.post(webhook_url, json=payload, timeout=15)
            if resp.status_code == 429:
                retry_after = float(resp.json().get("retry_after", 1))
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            break
    time.sleep(1)  # 5초에 5회 제한 준수


def send_all(webhook_url: str, messages: list[dict], dry_run: bool) -> None:
    for msg in messages:
        send(webhook_url, msg, dry_run)
