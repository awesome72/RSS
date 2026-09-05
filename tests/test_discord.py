import json

from src import discord as dc


def test_build_digest_messages_respects_discord_limits_with_long_urls():
    """회귀 테스트: 실제로 발생했던 400 에러 — Google News 링크(300자+) 여러 개가 합쳐지면
    개별 embed의 4096자 제한은 지켜도 메시지 전체 6000자 제한을 넘길 수 있었다."""
    long_url = "https://news.google.com/rss/articles/" + "A" * 350 + "?oc=5"
    groups = {
        cat: [
            {
                "title": f"{cat} 헤드라인 {i} 반도체 국채금리 전망 테스트용 긴 제목입니다",
                "link": long_url,
                "outlet": "테스트출처",
            }
            for i in range(15)
        ]
        for cat in ["국내 증시", "미국 증시", "매크로·공시", "반도체·기술", "전쟁·지정학"]
    }

    messages = dc.build_digest_messages(groups, collected=999)

    assert len(messages) > 0
    for msg in messages:
        embeds = msg.get("embeds", [])
        assert len(embeds) <= dc.MAX_EMBEDS_PER_MESSAGE
        total = sum(len(e["title"]) + len(e["description"]) for e in embeds)
        assert total <= 6000
        for e in embeds:
            assert len(e["description"]) <= dc.MAX_DESCRIPTION_LEN
        assert len(msg.get("content", "")) <= dc.MAX_CONTENT_LEN


def test_build_digest_messages_empty_groups_still_sends_header():
    messages = dc.build_digest_messages({}, collected=0)
    assert len(messages) == 1
    assert "content" in messages[0]


def test_build_log_message_shape():
    stats = {"total_feeds": 5, "success": 4, "new_articles": 10, "run_title": "테스트 로그"}
    msg = dc.build_log_message(stats)
    assert msg["embeds"][0]["title"] == "테스트 로그"
    assert "5" in msg["embeds"][0]["description"]


def test_send_dry_run_prints_json_without_hitting_network(capsys):
    dc.send("https://discord.com/api/webhooks/x", {"content": "hi"}, dry_run=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"content": "hi"}
