"""Discord Embed 빌드 + 웹훅 전송 (rate limit 준수)."""

from __future__ import annotations

import time

import httpx

IMPACT_COLOR = {
    "높음": 0xE74C3C,
    "중간": 0xF1C40F,
    "낮음": 0x95A5A6,
}

MAX_EMBEDS_PER_MESSAGE = 10
MAX_DESCRIPTION_LEN = 4096
MAX_CONTENT_LEN = 2000


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_digest_messages(topics: list[dict], stats: dict, ai_ok: bool) -> list[dict]:
    """다이제스트 메시지들(헤더 + embed 청크)을 만든다."""
    header = (
        f"📬 **일일 다이제스트** — 수집 {stats.get('collected', 0)}건 · "
        f"토픽 {len(topics)}개"
        + ("" if ai_ok else " · ⚠️ AI 요약 실패, 헤드라인으로 대체")
    )
    header = header[:MAX_CONTENT_LEN]

    embeds = []
    for topic in topics:
        sources = topic.get("sources", [])
        footer_text = " · ".join(s.get("outlet", "") for s in sources if s.get("outlet"))
        description = topic.get("summary", "")[:MAX_DESCRIPTION_LEN]
        embed = {
            "title": topic.get("title", "")[:256],
            "description": description,
            "color": IMPACT_COLOR.get(topic.get("impact", "중간"), IMPACT_COLOR["중간"]),
            "fields": [
                {"name": "분류", "value": topic.get("category", "기타"), "inline": True},
                {"name": "영향도", "value": topic.get("impact", "중간"), "inline": True},
            ],
        }
        if sources:
            link = sources[0].get("url", "")
            if link:
                embed["url"] = link
        if footer_text:
            embed["footer"] = {"text": footer_text[:2048]}
        embeds.append(embed)

    messages = []
    for i, chunk in enumerate(_chunk(embeds, MAX_EMBEDS_PER_MESSAGE)):
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
