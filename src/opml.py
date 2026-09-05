"""OPML 파싱 → Feed 객체 리스트."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class Feed:
    url: str
    title: str
    category: str
    needs_confirm: bool  # 제목에 "(확인 필요)"가 포함된 피드


def parse_opml(path: str) -> list[Feed]:
    tree = ET.parse(path)
    body = tree.getroot().find("body")
    if body is None:
        return []

    feeds: list[Feed] = []

    def walk(node: ET.Element, category: str) -> None:
        for outline in node.findall("outline"):
            xml_url = outline.get("xmlUrl")
            title = outline.get("title") or outline.get("text") or ""
            if xml_url:
                feeds.append(
                    Feed(
                        url=xml_url,
                        title=title,
                        category=category,
                        needs_confirm="(확인 필요)" in title,
                    )
                )
            else:
                # 폴더 outline: 하위 outline들의 카테고리로 사용
                sub_category = title or category
                walk(outline, sub_category)

    walk(body, category="기타")
    return feeds
