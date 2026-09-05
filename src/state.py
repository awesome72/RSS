"""state/*.json 읽기/쓰기 + URL 정규화/해시 + 만료 정리."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
SEEN_PATH = STATE_DIR / "seen.json"
HEALTH_PATH = STATE_DIR / "feeds_health.json"
PENDING_PATH = STATE_DIR / "pending.json"
HISTORY_PATH = STATE_DIR / "digest_history.json"


def _load(path: Path, default):
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return default
    return json.loads(text)


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def hash_url(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


# ---- seen.json ----

def load_seen() -> dict:
    return _load(SEEN_PATH, {})


def save_seen(seen: dict) -> None:
    _save(SEEN_PATH, seen)


def prune_seen(seen: dict, retention_days: int) -> dict:
    cutoff = time.time() - retention_days * 86400
    return {h: v for h, v in seen.items() if v.get("first_seen", 0) >= cutoff}


def mark_seen(seen: dict, url: str) -> None:
    h = hash_url(url)
    if h not in seen:
        seen[h] = {"url": url, "first_seen": time.time()}


def is_seen(seen: dict, url: str) -> bool:
    return hash_url(url) in seen


# ---- feeds_health.json ----

def load_health() -> dict:
    return _load(HEALTH_PATH, {})


def save_health(health: dict) -> None:
    _save(HEALTH_PATH, health)


def record_result(health: dict, feed_url: str, success: bool, needs_confirm: bool) -> bool:
    """피드 성공/실패를 기록. (확인 필요) 피드가 3회 연속 실패로 새로 비활성화되면 True 반환."""
    entry = health.setdefault(
        feed_url,
        {"success": 0, "fail": 0, "consecutive_fail": 0, "disabled": False},
    )
    newly_disabled = False
    if success:
        entry["success"] += 1
        entry["consecutive_fail"] = 0
    else:
        entry["fail"] += 1
        entry["consecutive_fail"] += 1
        if needs_confirm and entry["consecutive_fail"] >= 3 and not entry["disabled"]:
            entry["disabled"] = True
            newly_disabled = True
    return newly_disabled


def is_disabled(health: dict, feed_url: str) -> bool:
    return health.get(feed_url, {}).get("disabled", False)


# ---- pending.json (다음 다이제스트에서 처리할 신규 기사) ----

def load_pending() -> list:
    return _load(PENDING_PATH, [])


def save_pending(pending: list) -> None:
    _save(PENDING_PATH, pending)


def clear_pending() -> None:
    save_pending([])


# ---- digest_history.json (대시보드용 다이제스트 이력) ----

def load_history() -> list:
    return _load(HISTORY_PATH, [])


def save_history(history: list) -> None:
    _save(HISTORY_PATH, history)


def append_history(entry: dict, retention: int = 60) -> None:
    history = load_history()
    history.append(entry)
    save_history(history[-retention:])
