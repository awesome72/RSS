# RSS → Discord 뉴스레터

`feeds/stocks-kr-us-feeds.opml`에 정의된 국내·미국 증시 RSS 피드를 GitHub Actions로
주기적으로 수집하고, 하루 한 번 AI가 요약한 다이제스트를 Discord로 보냅니다.
서버 호스팅 없이 GitHub Actions cron만으로 동작합니다.

## 동작 방식

| 워크플로 | 주기 | 하는 일 |
|---|---|---|
| `collect.yml` | 2시간마다 | 전체 피드 수집 → 중복 제거 → 신규 기사를 `state/pending.json`에 적재. 실행 결과를 `#로그` 채널에 전송 |
| `digest.yml` | 매일 KST 08:00 (UTC 23:00) | `pending.json`에 쌓인 기사를 Claude가 클러스터링·요약 → `#다이제스트` 채널에 전송 후 대기열 비움 |

- 다이제스트는 미국 증시 마감 이후 시각(KST 08:00)에 맞춰 하루 1회만 발송됩니다.
- AI 호출은 다이제스트당 1회로 제한됩니다 (기사 최대 100건을 한 번에 처리).
- 개별 피드가 실패해도 전체 실행은 멈추지 않고 실패 내역만 로그로 남습니다.
- 제목에 `(확인 필요)`가 붙은 피드는 3회 연속 실패 시 자동 비활성화되고 로그로 알림됩니다.

## Discord 웹훅 만들기

1. Discord 서버 설정 → 연동 → 웹훅 → 새 웹훅 만들기
2. 다이제스트를 받을 채널, 실행 로그를 받을 채널에 각각 하나씩 (총 2개) 생성
3. 각 웹훅의 URL을 복사

## GitHub Repository Secrets 설정

저장소의 **Settings → Secrets and variables → Actions**에서 아래 값을 등록하세요.

| Secret 이름 | 용도 |
|---|---|
| `DISCORD_WEBHOOK_DIGEST` | 다이제스트 채널 웹훅 URL |
| `DISCORD_WEBHOOK_LOG` | 실행 로그 채널 웹훅 URL |
| `ANTHROPIC_API_KEY` | Claude API 키 (다이제스트 요약용) |

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
python -m src.main digest --dry-run   # AI 요약 후 다이제스트를 stdout에 출력 (실제 전송/대기열 초기화 없음)
```

`--dry-run`을 주면 Discord로 전송하는 대신 전송될 JSON을 그대로 stdout에 출력합니다.
개발 중 웹훅을 실제로 두드리지 않기 위한 옵션입니다.

## 수동 실행

GitHub Actions 탭에서 `Collect RSS` 또는 `Daily Digest` 워크플로를 `workflow_dispatch`로
수동 실행할 수 있습니다.

## 저작권 준수 (필수)

- 원문 본문을 그대로 싣지 않습니다. 항상 AI가 재구성한 자체 요약과 원문 링크만 제공합니다.
- RSS `description` 필드를 Discord에 그대로 복사하지 않습니다.
- 인용이 불가피한 경우 15단어 미만, 출처당 1회로 제한합니다.
- 서울경제·아시아경제 등 일부 피드는 **개인 비상업적 사용**만 허용하며 AI 학습 데이터 축적을
  금지합니다. 이 시스템은 **개인 Discord 서버 전용**이며, 공개 서버 배포·재배포·모델 학습
  데이터 축적을 금지합니다.

## 디렉터리 구조

```
.github/workflows/
  collect.yml         # 2시간마다 cron
  digest.yml          # 매일 KST 08:00 cron
feeds/
  stocks-kr-us-feeds.opml
src/
  opml.py             # OPML 파싱 → Feed 객체 리스트
  collector.py         # 피드 수집, 중복 제거, 정규화
  summarizer.py        # Anthropic API 호출
  discord.py           # Embed 빌드 + 전송
  state.py             # state/*.json 읽기/쓰기
  main.py              # CLI 엔트리포인트
state/
  seen.json            # 이미 보낸 기사 URL 해시 (30일 지나면 자동 삭제)
  feeds_health.json    # 피드별 성공/실패 카운트
  pending.json         # 다음 다이제스트에서 처리할 신규 기사 대기열
config.yaml            # 부스트/뮤트 키워드, 수집 설정
requirements.txt
```
