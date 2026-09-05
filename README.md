# RSS → Discord 뉴스레터

`feeds/stocks-kr-us-feeds.opml`에 정의된 국내·미국 증시 RSS 피드를 GitHub Actions로
주기적으로 수집하고, 하루 한 번 카테고리별로 묶은 헤드라인 다이제스트를 Discord로 보냅니다.
AI API를 호출하지 않으며, 서버 호스팅 없이 GitHub Actions cron만으로 동작합니다.

**대시보드**: https://web-nine-ruddy-66.vercel.app (다이제스트 이력 · 피드 상태, [웹 대시보드](#웹-대시보드-vercel) 참고)

## 설정 체크리스트

- [x] GitHub 저장소 연결 (`awesome72/RSS`)
- [x] GitHub Actions 워크플로 추가 (`collect.yml`, `digest.yml`)
- [x] Vercel 대시보드 배포 및 GitHub 연동
- [x] Discord 웹훅 생성 및 `DISCORD_WEBHOOK_URL` 등록
- [ ] `collect` 워크플로 최초 1회 수동 실행으로 `seen.json` 초기화 ([첫 실행 안내](#첫-실행-안내))

## 동작 방식

| 워크플로 | 주기 | 하는 일 |
|---|---|---|
| `collect.yml` | 2시간마다 | 전체 피드 수집 → 중복 제거 → 신규 기사를 `state/pending.json`에 적재. 실행 결과를 `#로그` 채널에 전송 |
| `digest.yml` | 매일 KST 08:00 (UTC 23:00) | `pending.json`에 쌓인 기사를 카테고리별로 묶어 헤드라인 목록으로 `#다이제스트` 채널에 전송 후 대기열 비움 |

- 다이제스트는 미국 증시 마감 이후 시각(KST 08:00)에 맞춰 하루 1회만 발송됩니다.
- **AI 요약을 사용하지 않습니다.** 수집된 기사의 원문 제목·출처·링크만 5개 카테고리
  (국내 증시 / 미국 증시 / 매크로·공시 / 반도체·기술 / 전쟁·지정학)로 묶어서 그대로 보여줍니다.
- 카테고리 하나가 슬롯을 독점하지 않도록, `keywords_boost` 매치 기사를 우선하되
  **카테고리별로 라운드로빈**으로 배분해 `max_headlines`를 채웁니다 (기사가 많은 카테고리 때문에
  다른 카테고리가 다이제스트에서 통째로 빠지는 일이 없도록).
- 개별 피드가 실패해도 전체 실행은 멈추지 않고 실패 내역만 로그로 남습니다.
- 어떤 피드든 3회 연속 실패하면 자동 비활성화되고 로그로 알림됩니다.
- `collect`/`digest`가 예외로 죽어도 가능한 한 실패 사실을 로그 채널에 먼저 알린 뒤 종료합니다
  (GitHub Actions 탭을 직접 안 봐도 Discord에서 확인 가능).

## 수집 중인 피드 (32개, 5개 카테고리)

전체 정의는 `feeds/stocks-kr-us-feeds.opml`에 있습니다. 아래는 그 내용을 그대로 옮긴 표입니다.

| 카테고리 | 피드 |
|---|---|
| 국내 증시 | 한국경제 · 증권, 한국경제 · 경제, 한국경제 · 국제, 서울경제 · 마켓시그널, 서울경제 · 경제, 서울경제 · 금융, 서울경제 · 기업, 연합뉴스 · 경제, 코스피 종합 키워드 (Google News) |
| 미국 증시 | CNBC · Finance/Economy/Earnings/Market Insider/Trader Talk/Energy/Health Care, Investing.com · US Stock Market, Yahoo Finance, Seeking Alpha · NVDA 예시, WSJ · Markets |
| 매크로·공시 | Fed · 전체 보도자료/통화정책/은행·소비자 규제정책, Bloomberg 연준 키워드 (Google News), 국채금리 키워드 (Google News, 한글), Treasury Yields 키워드 (Google News, 영문) |
| 반도체·기술 | 한국경제 · IT·과학, Reuters 반도체 키워드 (Google News), 반도체 키워드 (Google News, 한글) |
| 전쟁·지정학 | BBC · World News, WSJ · World News, 연합뉴스 · 국제 |

피드를 추가/삭제하려면 OPML 파일을 편집하세요. `<outline text="카테고리명">`으로 묶인 그룹이
곧 대시보드·Discord에서 쓰이는 카테고리가 됩니다. 새 피드를 추가한 직후에는 그 피드의 과거
글까지 한꺼번에 "신규"로 잡혀 다음 다이제스트가 일시적으로 그 카테고리 위주로 쏠릴 수 있습니다
(하루 이틀 지나면 정상화됩니다).

## Discord 웹훅 만들기

1. Discord 서버 설정 → 연동 → 웹훅 → 새 웹훅 만들기
2. 웹훅의 URL을 복사

현재는 다이제스트와 실행 로그를 **웹훅 1개, 같은 채널**로 함께 받도록 설정되어 있습니다
(채널을 분리하고 싶다면 웹훅을 하나 더 만들고 아래 워크플로 env에서
`DISCORD_WEBHOOK_LOG`를 별도 Secret으로 나누면 됩니다).

## GitHub Repository Secrets 설정

저장소의 **Settings → Secrets and variables → Actions**에서 아래 값을 등록하세요.

| Secret 이름 | 용도 |
|---|---|
| `DISCORD_WEBHOOK_URL` | 다이제스트 + 실행 로그를 받을 채널의 웹훅 URL |

로컬 개발 시에는 `.env.example`을 복사해 `.env`로 만들고 값을 채우세요 (`.env`는 git에 커밋되지 않습니다).

## 첫 실행 안내

`state/seen.json`이 비어 있는 상태(최초 1회)에서 `collect`를 실행하면, 그동안 쌓여있던
모든 기사가 한꺼번에 "신규"로 잡혀 다이제스트가 폭주합니다. 이를 막기 위해
**첫 실행에서는 전송 없이 seen.json만 채우고 종료**합니다. 이후 실행부터 정상적으로
신규 기사만 `pending.json`에 쌓입니다.

## 로컬 실행 (CLI)

```bash
pip install -r requirements.txt

python -m src.main health --dry-run   # 피드 생존 확인만, 전송 없음
python -m src.main collect --dry-run  # 수집 + 대기열 적재, 로그는 stdout 출력
python -m src.main digest --dry-run   # 카테고리별 헤드라인 다이제스트를 stdout에 출력 (실제 전송/대기열 초기화 없음)
```

`--dry-run`을 주면 Discord로 전송하는 대신 전송될 JSON을 그대로 stdout에 출력합니다.
개발 중 웹훅을 실제로 두드리지 않기 위한 옵션입니다.

## 테스트 / CI

```bash
pip install -r requirements-dev.txt
pytest -q
```

핵심 로직(OPML 파싱, URL 정규화·중복 제거, 카테고리 라운드로빈 배분, Discord 임베드 글자수
제한)에 대한 회귀 테스트가 `tests/`에 있습니다 — 실제로 겪었던 두 가지 버그(카테고리 쏠림,
Google News 긴 링크로 인한 6000자 초과 400 에러)를 재현하는 테스트를 포함합니다.
`.github/workflows/ci.yml`이 `main` 브랜치 push·PR마다 자동으로 실행합니다
(`state/*.json`만 바뀌는 봇 커밋은 커밋 메시지의 `[skip ci]`로 건너뜁니다).

## 수동 실행

GitHub Actions 탭에서 `Collect RSS` 또는 `Daily Digest` 워크플로를 `workflow_dispatch`로
수동 실행할 수 있습니다.

## 웹 대시보드 (Vercel)

`web/index.html`은 빌드 과정이나 서버 없이, 브라우저에서 직접
`raw.githubusercontent.com`의 `state/digest_history.json` · `state/feeds_health.json`을
읽어와 최신 다이제스트·이전 이력·피드 상태를 보여주는 순수 정적 페이지입니다.

- Vercel 프로젝트 루트: `web/` (Vercel 프로젝트 설정에서 Root Directory를 `web`으로 지정)
- GitHub 저장소와 연결되어 있어 `main` 브랜치에 푸시하면 자동 재배포됩니다
- 페이지 자체는 정적이라 재배포 없이도 새로고침할 때마다 최신 데이터를 가져옵니다
  (다이제스트가 발송되어 `digest_history.json`이 갱신되면 바로 반영)
- 저장소가 공개 저장소여야 raw 파일에 인증 없이 접근할 수 있습니다
- 시스템 다크 모드 설정을 자동으로 따라가며, 우상단 "다크 모드" 버튼으로 직접 켜고 끌 수도
  있습니다 (선택은 브라우저에 저장되어 다음 방문에도 유지됩니다)
- 검색창(제목·출처)과 카테고리 필터 칩으로 원하는 헤드라인만 빠르게 찾을 수 있습니다

## 저작권 준수 (필수)

- 원문 본문을 절대 싣지 않습니다. Discord에는 기사 **제목 + 출처 + 링크**만 표시하고,
  본문을 대신하는 요약문도 만들지 않습니다 (AI를 사용하지 않으므로 재구성 자체가 없습니다).
- RSS `description` 필드는 수집 단계의 키워드 필터링에만 쓰이고, Discord로는 절대 전달되지
  않습니다.
- 서울경제·아시아경제 등 일부 피드는 **개인 비상업적 사용**만 허용하며 AI 학습 데이터 축적을
  금지합니다. 이 시스템은 **개인 Discord 서버 전용**이며, 공개 서버 배포·재배포·모델 학습
  데이터 축적을 금지합니다.

## 디렉터리 구조

```
.github/workflows/
  collect.yml         # 2시간마다 cron
  digest.yml          # 매일 KST 08:00 cron
  ci.yml              # main push/PR마다 pytest 실행
feeds/
  stocks-kr-us-feeds.opml
src/
  opml.py             # OPML 파싱 → Feed 객체 리스트
  collector.py         # 피드 수집, 중복 제거, 정규화, 카테고리 라운드로빈 배분
  discord.py           # Embed 빌드(글자수 제한 패킹 포함) + 전송
  state.py             # state/*.json 읽기/쓰기
  main.py              # CLI 엔트리포인트 + 실패 알림 wrapper
tests/                 # pytest 회귀 테스트 (opml/state/collector/discord)
state/
  seen.json            # 이미 보낸 기사 URL 해시 (30일 지나면 자동 삭제)
  feeds_health.json    # 피드별 성공/실패 카운트
  pending.json         # 다음 다이제스트에서 처리할 신규 기사 대기열
  digest_history.json  # 대시보드용 다이제스트 이력 (최근 60건)
web/
  index.html           # Vercel에 배포되는 정적 대시보드 (라이트/다크 모드, 검색·필터)
config.yaml            # 부스트/뮤트 키워드, 수집·다이제스트 설정
requirements.txt
requirements-dev.txt    # requirements.txt + pytest
```
