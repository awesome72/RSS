"""Anthropic API를 이용한 클러스터링·요약 (다이제스트당 1회 호출)."""

from __future__ import annotations

import json
import os

DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """\
당신은 금융 뉴스 편집자입니다. 아래 기사 목록을 분석해 반드시 JSON만 반환하세요.
마크다운 코드펜스나 설명 문장을 절대 포함하지 마세요.

절대 규칙:
- 원문 문장을 그대로 베끼지 마세요. 항상 당신 자신의 언어로 다시 표현하세요.
- 인용이 꼭 필요하면 15단어 미만으로, 출처당 1회만 사용하세요.

작업:
1. 같은 사건을 다루는 기사들을 하나의 토픽으로 클러스터링
2. 상위 5~7개 토픽만 선별 (영향도와 중요도 기준)
3. 토픽마다 한국어 2~3문장으로 요약 (미국 기사도 한국어로 번역·요약)
4. 각 토픽에 카테고리 태그 부여: 국내증시 / 미국증시 / 매크로 / 산업
5. 각 토픽에 영향도 부여: 높음 / 중간 / 낮음

출력 스키마:
{
  "topics": [
    {
      "title": "토픽 한 줄 제목",
      "category": "미국증시",
      "impact": "높음",
      "summary": "2~3문장 한국어 요약",
      "sources": [{"outlet": "CNBC", "url": "https://..."}]
    }
  ]
}
"""


def _build_user_prompt(articles: list[dict], max_articles: int) -> str:
    trimmed = articles[:max_articles]
    lines = []
    for i, a in enumerate(trimmed, start=1):
        lines.append(
            f"{i}. [{a['category']}] {a['outlet']}: {a['title']}\n"
            f"   링크: {a['link']}\n"
            f"   설명: {a.get('description', '')[:300]}"
        )
    return "다음은 최근 수집된 기사 목록입니다:\n\n" + "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _call_anthropic(articles: list[dict], config: dict) -> str:
    from anthropic import Anthropic

    model = os.environ.get("SUMMARY_MODEL", DEFAULT_MODEL)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    max_articles = config.get("digest", {}).get("max_articles_to_ai", 100)

    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(articles, max_articles)}],
    )
    return resp.content[0].text


def summarize(articles: list[dict], config: dict) -> tuple[dict, bool]:
    """(결과 JSON, AI 요약 성공 여부) 반환. 실패 시 헤드라인 목록으로 폴백."""
    if not articles:
        return {"topics": []}, True

    for attempt in range(2):
        try:
            raw = _call_anthropic(articles, config)
            parsed = json.loads(_strip_code_fence(raw))
            if "topics" in parsed:
                return parsed, True
        except Exception:  # noqa: BLE001 - 재시도 후 폴백으로 처리
            if attempt == 1:
                break
            continue

    return _fallback(articles), False


def _fallback(articles: list[dict]) -> dict:
    max_topics = 7
    topics = []
    for a in articles[:max_topics]:
        topics.append(
            {
                "title": a["title"],
                "category": a.get("category", "기타"),
                "impact": "중간",
                "summary": "(AI 요약 실패로 헤드라인만 표시합니다.)",
                "sources": [{"outlet": a.get("outlet", ""), "url": a.get("link", "")}],
            }
        )
    return {"topics": topics}
