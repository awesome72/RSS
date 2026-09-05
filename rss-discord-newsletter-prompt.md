# RSS → Discord 뉴스레터 구현 프롬프트

> 이 문서 전체를 Claude Code(또는 다른 코딩 에이전트)에 그대로 붙여넣으세요.
> `stocks-kr-us-feeds.opml` 파일을 같은 디렉터리에 두고 시작하면 됩니다.

---

## 0. 역할

당신은 개인용 금융 뉴스 파이프라인을 만드는 시니어 백엔드 엔지니어입니다.
아래 명세대로 **동작하는 저장소 하나**를 처음부터 끝까지 구현하세요.
설계 논의는 하지 말고 바로 코드를 작성하고, 마지막에 실행 방법만 요약하세요.

---

## 1. 무엇을 만드는가

같은 디렉터리의 `stocks-kr-us-feeds.opml`에 정의된 RSS 피드를 주기적으로 수집해서,
**Discord 채널 3개**로 서로 다른 형태로 배달하는 시스템.

| 채널 | 주기 | 내용 |
|---|---|---|
| `#속보` | 20분마다 | 신규 기사 헤드라인 + 출처 + 링크. 요약 없음 |
| `#데일리` | 평일 KST 08:00, 17:00 | AI가 클러스터링·요약한 다이제스트. 하루 2회 |
| `#로그` | 실행 시마다 | 수집 통계, 실패한 피드, 에러 |

08:00은 미국장 마감 후 → **미국 증시 리뷰** 중심.
17:00은 한국장 마감 후 → **국내 증시 리뷰 + 미국 프리마켓 전망** 중심.

---

## 2. 기술 스택 (고정)

- **Python 3.11+**
- `feedparser` — RSS/Atom 파싱
- `httpx` — Discord webhook 전송, 비동기
- `anthropic` — 요약·번역·클러스터링
- **GitHub Actions cron** — 스케줄러. 별도 서버 없음
- **상태 저장**: 저장소 내 `state/seen.json` (이미 보낸 기사 URL 해시). Actions가 커밋해서 다음 실행에 재사용
- **Discord Webhook** — 봇이 아니라 웹훅. 채널별 웹훅 URL 3개

의존성은 `requirements.txt`로 고정 버전 명시.

---

## 3. 디렉터리 구조

```
rss-discord/
├── .github/workflows/
│   ├── breaking.yml        # 20분 cron
│   └── digest.yml          # 08:00 / 17:00 KST cron
├── feeds/
│   └── stocks-kr-us-feeds.opml
├── src/
│   ├── opml.py             # OPML 파싱 → Feed 객체 리스트
│   ├── collector.py        # 피드 수집, 중복 제거, 정규화
│   ├── summarizer.py       # Anthropic API 호출
│   ├── discord.py          # Embed 빌드 + 전송
│   ├── state.py            # seen.json 읽기/쓰기
│   └── main.py             # CLI 엔트리포인트
├── state/seen.json
├── config.yaml
├── requirements.txt
└── README.md
```

---

## 4. 핵심 요구사항

### 4.1 OPML 파싱
- 중첩된 `<outline>` 구조를 읽어 **폴더명을 카테고리로** 사용
  (`국내 증시`, `미국 증시`, `매크로·공시`, `Google News 우회`)
- 제목에 `(확인 필요)`가 포함된 피드는 **3회 연속 실패 시 자동으로 비활성화**하고 `#로그`에 알림
- 피드별 성공/실패 카운트를 `state/feeds_health.json`에 기록

### 4.2 수집
- 각 피드를 비동기로 병렬 수집, 피드당 타임아웃 10초, 동시 실행 8개로 제한
- `User-Agent`를 명시적으로 설정 (기본 UA는 일부 언론사에서 차단됨)
- 실패해도 전체를 중단하지 말고 개별 실패로 기록하고 계속 진행
- 중복 제거 키: `sha256(정규화된 URL)`. 정규화 = 쿼리스트링의 `utm_*` 제거 + 프래그먼트 제거
- `seen.json`은 **30일 지난 항목을 자동 삭제**해서 무한히 커지지 않게 할 것

### 4.3 필터링
`config.yaml`에 아래를 정의하고 코드에서 읽어 쓰세요:

```yaml
keywords_boost:      # 포함되면 우선순위 상승
  - 반도체
  - HBM
  - 삼성전자
  - SK하이닉스
  - 연준
  - FOMC
  - 금리
  - 실적
  - semiconductor
  - earnings
keywords_mute:       # 포함되면 제외
  - 부고
  - 인사
  - 신간
  - 포토
min_title_length: 10
```

- `#속보`는 `keywords_boost` 매치 기사만 보냄 (노이즈 억제)
- `#데일리`는 전체 수집분을 대상으로 함

### 4.4 AI 요약 (`#데일리`)

Anthropic API 사용. 모델은 `claude-sonnet-5`, 토큰 절약이 필요하면 `claude-haiku-4-5-20251001`.
API 키는 `ANTHROPIC_API_KEY` 환경변수.

**호출은 하루 2회, 다이제스트당 1회로 제한**합니다. 기사 100건을 한 번에 넣고 아래를 시키세요:

1. **클러스터링** — 같은 사건을 다루는 기사들을 하나의 토픽으로 묶기
2. **선별** — 토픽 중 상위 5~7개만
3. **요약** — 토픽마다 한국어 2~3문장. 미국 기사도 한국어로
4. **분류** — 각 토픽에 `국내증시 / 미국증시 / 매크로 / 산업` 태그
5. **영향도** — 각 토픽에 `높음 / 중간 / 낮음`

출력은 **JSON만** 반환하도록 프롬프트에 명시하고, 마크다운 코드펜스를 제거한 뒤 파싱하세요.
파싱 실패 시 1회 재시도, 그래도 실패하면 요약 없이 헤드라인 목록으로 폴백합니다.

```json
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
```

### 4.5 Discord 전송

**반드시 지켜야 할 제약:**
- 메시지당 embed 최대 **10개**
- embed `description` 최대 **4096자**, 전체 embed 합계 **6000자**
- 메시지 `content` 최대 **2000자**
- 웹훅 rate limit: 5초에 5회 → 전송 사이 **1초 sleep**, 429 응답 시 `Retry-After` 헤더만큼 대기 후 재시도

**포맷:**
- `#속보`: embed 1개에 여러 헤드라인을 묶어서. 제목 = 시각, description = `• [제목](링크) — 출처` 목록
- `#데일리`: 토픽 1개당 embed 1개. 색상은 영향도로 구분 (높음 빨강 `0xE74C3C` / 중간 노랑 `0xF1C40F` / 낮음 회색 `0x95A5A6`). footer에 출처 목록
- 다이제스트 맨 앞에 요약 헤더 메시지: 수집 기사 수, 토픽 수, 대상 시간대

### 4.6 저작권 준수 — 필수

이건 선택이 아닙니다. 코드에 강제하세요.

- **원문 본문을 절대 그대로 싣지 않습니다.** 항상 자체 요약 + 원문 링크
- RSS `description` 필드를 Discord에 그대로 복사 금지. 반드시 요약을 거치거나 제목만 사용
- 인용이 불가피하면 **15단어 미만, 출처당 1회**
- 서울경제·아시아경제 등은 RSS를 **개인 비상업적 사용으로만** 허용하고 AI 학습 이용을 금지합니다.
  → 이 시스템은 **개인 Discord 서버 전용**입니다. 공개 서버 배포·재배포·모델 학습 데이터 축적 금지
- `README.md`에 이 조건을 명시할 것

---

## 5. 환경변수

```
DISCORD_WEBHOOK_BREAKING=
DISCORD_WEBHOOK_DIGEST=
DISCORD_WEBHOOK_LOG=
ANTHROPIC_API_KEY=
```

로컬은 `.env`(gitignore), GitHub Actions는 Repository Secrets.

---

## 6. GitHub Actions

- cron은 **UTC 기준**입니다. KST 08:00 = UTC 23:00 (전날), KST 17:00 = UTC 08:00
- 평일만: `'0 23 * * 0-4'` (KST 월~금 08:00), `'0 8 * * 1-5'` (KST 월~금 17:00)
- `workflow_dispatch`를 넣어 수동 실행 가능하게
- `state/` 변경분은 `git-auto-commit-action` 등으로 커밋. **커밋 루프에 빠지지 않도록** `[skip ci]` 사용
- 동시 실행 방지: `concurrency` 그룹 설정

---

## 7. CLI

```bash
python -m src.main breaking          # 속보 1회 실행
python -m src.main digest --slot am  # 오전 다이제스트
python -m src.main digest --slot pm  # 오후 다이제스트
python -m src.main health            # 피드 생존 확인만, 전송 없음
python -m src.main --dry-run ...     # Discord 전송 대신 stdout 출력
```

`--dry-run`은 모든 서브커맨드에서 동작해야 합니다. 개발 중 웹훅을 때리지 않기 위함입니다.

---

## 8. 첫 실행 처리

`seen.json`이 비어 있으면 모든 피드의 전체 기사가 "신규"로 잡혀 수백 건이 쏟아집니다.
→ **최초 실행 시에는 전송하지 않고 seen.json만 채우고 종료**하세요. 로그에 안내 출력.

---

## 9. 완료 기준

1. `python -m src.main health --dry-run`이 OPML의 모든 피드에 대해 성공/실패 표를 출력한다
2. `python -m src.main breaking --dry-run`이 신규 기사만 골라 Discord embed JSON을 출력한다
3. `python -m src.main digest --slot pm --dry-run`이 AI 요약 JSON을 파싱해 embed로 변환한다
4. 같은 명령을 두 번 실행하면 두 번째는 신규 기사 0건이다 (중복 제거 검증)
5. `README.md`에 웹훅 생성 방법, Secrets 설정, 첫 실행 절차, 저작권 조건이 적혀 있다

---

## 10. 하지 말 것

- Discord **봇**으로 만들지 마세요. 웹훅이면 충분하고 호스팅이 필요 없습니다
- 데이터베이스를 도입하지 마세요. JSON 파일로 충분합니다
- 기사 **본문 크롤링**을 하지 마세요. RSS가 주는 필드만 씁니다
- 피드별로 개별 AI 호출을 하지 마세요. 비용이 수십 배가 됩니다
- 실패한 피드 하나 때문에 전체 실행이 죽지 않게 하세요

---

## 부록 — 대안 스택

GitHub Actions 대신 쓸 수 있는 것 (요청 시에만 구현):

| 방식 | 장점 | 단점 |
|---|---|---|
| **n8n** (self-host) | 노코드, RSS→Discord 노드 기본 제공 | 서버 필요, AI 요약 커스터마이징 제한 |
| **Cloudflare Workers + KV** | 무료 티어, 저지연 | 파이썬 불가, TS로 재작성 |
| **라즈베리파이 + cron** | 완전한 제어 | 가동률 본인 책임 |
| **Zapier / Make** | 5분 셋업 | 유료, 피드 20개면 비쌈 |
