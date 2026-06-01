"""상태 저장 계층 — 이 하네스에서 상태 파일을 기록하는 유일한 모듈.

저장 전략 (DB 대신 JSON, 검토 결과 채택)
-----------------------------------------
- 엔티티별 1파일      : state/work_items/WI-0001.json     (진실 원천)
- 이벤트는 append-only: state/events/WI-0001.jsonl        (진실 원천)
- 요구사항 인입 로그   : state/queue.jsonl                 (append-only)
- 조회용 요약          : state/index.json                  (파생·재생성 가능)

신뢰성 보장
-----------
- 원자적 쓰기 : tmp 작성 → fsync → os.rename (POSIX 원자적) → 반쪽 파일 불가
- 장애 격리   : 항목 1개 파일이 깨져도 나머지는 무사
- 동시성      : 항목별 파일 분리 + 공유 자원(ID 발급/큐/인덱스)은 파일 락으로 직렬화

에이전트(LLM)는 절대 이 파일들을 직접 쓰지 않는다. 오직 이 모듈을 통해서만 변경된다.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# 엔진 코드·prompts·기본설정 위치 (구 HARNESS_HOME). 플러그인에선 ${CLAUDE_PLUGIN_ROOT}.
# 절대 여기에 런타임 상태를 쓰지 않는다 (플러그인 업데이트 시 교체됨).
ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _resolve_data_root() -> Path:
    """상태·worktree를 둘 루트. 우선순위:
      1) 명시 override / 플러그인 영속 디렉토리 (${CLAUDE_PLUGIN_DATA})
      2) 기본: ~/.harness
    """
    env = os.environ.get("HARNESS_DATA_HOME") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".harness").resolve()


DATA_ROOT = _resolve_data_root()
HARNESS_HOME = ENGINE_ROOT  # phases.py가 prompts/ 경로로 참조
STATE_DIR = DATA_ROOT / "state"
WORK_ITEMS_DIR = STATE_DIR / "work_items"
EVENTS_DIR = STATE_DIR / "events"
QUEUE_FILE = STATE_DIR / "queue.jsonl"
INDEX_FILE = STATE_DIR / "index.json"
LOCK_FILE = STATE_DIR / ".lock"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_dirs() -> None:
    WORK_ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, text: str) -> None:
    """tmp 파일에 쓰고 fsync 후 원자적 rename. 반쪽 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # 원자적 교체
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def _lock() -> Iterator[None]:
    """공유 자원(ID 발급/큐/인덱스) 변경을 직렬화하는 advisory 파일 락."""
    _ensure_dirs()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ── 작업 항목(work item) ────────────────────────────────────────────────

def _item_path(item_id: str) -> Path:
    return WORK_ITEMS_DIR / f"{item_id}.json"


def _events_path(item_id: str) -> Path:
    return EVENTS_DIR / f"{item_id}.jsonl"


def _next_id() -> str:
    """기존 항목 파일을 스캔해 다음 WI-NNNN ID 발급. (락 안에서 호출)"""
    _ensure_dirs()
    max_n = 0
    for p in WORK_ITEMS_DIR.glob("WI-*.json"):
        try:
            max_n = max(max_n, int(p.stem.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return f"WI-{max_n + 1:04d}"


def create_work_item(project: str, requirement: str, priority: int = 100,
                     project_dir: str | None = None) -> dict[str, Any]:
    """요구사항을 큐에 등록하고 새 작업 항목을 생성한다.

    project_dir이 주어지면 cwd/플러그인 모드(프로젝트 디렉토리 자체가 레포, harness.yaml은 거기서 읽음).
    None이면 레거시 모드(projects/<name>/harness.yaml).
    """
    with _lock():
        item_id = _next_id()
        item = {
            "id": item_id,
            "project": project,
            "project_dir": project_dir,
            "requirement": requirement,
            "priority": priority,
            "state": "QUEUED",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "attempts": {},
            "artifacts": {},
            "branch": f"harness/{item_id}",
            "last_error": None,
        }
        _atomic_write(_item_path(item_id), json.dumps(item, ensure_ascii=False, indent=2))
        # 요구사항 인입 로그 (append-only)
        with open(QUEUE_FILE, "a", encoding="utf-8") as qf:
            qf.write(json.dumps(
                {"ts": now_iso(), "id": item_id, "project": project,
                 "requirement": requirement, "priority": priority},
                ensure_ascii=False) + "\n")
    append_event(item_id, "created", {"project": project, "requirement": requirement})
    _reindex_locked()
    return item


def load_item(item_id: str) -> dict[str, Any]:
    return json.loads(_item_path(item_id).read_text(encoding="utf-8"))


def save_item(item: dict[str, Any]) -> None:
    item["updated_at"] = now_iso()
    _atomic_write(_item_path(item["id"]), json.dumps(item, ensure_ascii=False, indent=2))
    _reindex_locked()


def list_items() -> list[dict[str, Any]]:
    items = []
    for p in sorted(WORK_ITEMS_DIR.glob("WI-*.json")):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def item_exists(item_id: str) -> bool:
    return _item_path(item_id).exists()


# ── 이벤트 (append-only 감사 로그) ──────────────────────────────────────

def append_event(item_id: str, kind: str, data: dict[str, Any] | None = None) -> None:
    """항목별 이벤트 타임라인에 한 줄 추가. O_APPEND라 크래시에 안전."""
    _ensure_dirs()
    rec = {"ts": now_iso(), "kind": kind, "data": data or {}}
    with open(_events_path(item_id), "a", encoding="utf-8") as ef:
        ef.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_events(item_id: str) -> list[dict[str, Any]]:
    path = _events_path(item_id)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ── 인덱스 (파생 캐시, 재생성 가능) ─────────────────────────────────────

def _build_index() -> dict[str, Any]:
    summary = []
    for item in list_items():
        summary.append({
            "id": item["id"],
            "project": item["project"],
            "state": item["state"],
            "priority": item.get("priority", 100),
            "updated_at": item.get("updated_at"),
            "requirement": item.get("requirement", "")[:80],
        })
    return {"generated_at": now_iso(), "count": len(summary), "items": summary}


def _reindex_locked() -> None:
    """인덱스 재생성. 진실 원천(항목 파일)에서 파생되므로 언제든 안전하게 재호출 가능."""
    _atomic_write(INDEX_FILE, json.dumps(_build_index(), ensure_ascii=False, indent=2))


def reindex() -> dict[str, Any]:
    """index.json이 손상/유실되어도 항목 파일들로부터 복원한다 (hctl reindex)."""
    idx = _build_index()
    _atomic_write(INDEX_FILE, json.dumps(idx, ensure_ascii=False, indent=2))
    return idx


def load_index() -> dict[str, Any]:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return reindex()  # 손상 시 자동 복원
