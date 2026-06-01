"""git worktree 격리 — 작업 항목별 독립 작업 디렉토리.

동시 처리의 핵심. 각 작업 항목은 자신의 worktree(별도 작업 트리)에서 처리되어,
여러 항목을 병렬로 진행해도 작업 트리가 서로 충돌하지 않는다.

- 메인 레포       : 프로젝트 디렉토리(harness.yaml이 있는 곳)
- 항목별 worktree : DATA_ROOT/state/worktrees/<item_id>   (브랜치 harness/<item_id>)

worktree add/remove는 메인 레포의 .git 메타데이터를 건드리므로 스레드 락으로 직렬화한다.
(커밋은 항목마다 다른 브랜치 ref라 git 자체로 안전 → 락 불필요)
"""

from __future__ import annotations

import threading
from pathlib import Path

from .phases import run_shell
from .state import STATE_DIR

WORKTREES_DIR = STATE_DIR / "worktrees"   # DATA_ROOT 아래 (상태와 함께 사용자 홈/플러그인 데이터로 이동)

_GIT_ID = "-c user.email=harness@local -c user.name=harness"
_wt_lock = threading.Lock()   # worktree add/remove 직렬화


def _trunk_ref(main_repo: Path) -> str:
    for ref in ("main", "master"):
        rc, _ = run_shell(f"git rev-parse --verify {ref}", main_repo)
        if rc == 0:
            return ref
    rc, out = run_shell("git rev-parse --abbrev-ref HEAD", main_repo)
    return out.strip() or "HEAD"


def ensure_baseline(main_repo: Path) -> None:
    """메인 레포가 git 레포이고 최소 1개 커밋을 갖도록 보장."""
    main_repo.mkdir(parents=True, exist_ok=True)
    if not (main_repo / ".git").exists():
        run_shell("git init -q", main_repo)
    rc, _ = run_shell("git rev-parse --verify HEAD", main_repo)
    if rc != 0:
        run_shell(f"git {_GIT_ID} add -A", main_repo)
        run_shell(f"git {_GIT_ID} commit -q --allow-empty -m 'harness: baseline'", main_repo)


def worktree_path(project: str, item_id: str) -> Path:
    return WORKTREES_DIR / project / item_id


def ensure_worktree(main_repo: Path, project: str, item_id: str, branch: str) -> Path:
    """항목용 worktree를 생성(또는 기존 반환). 브랜치는 트렁크에서 분기."""
    ensure_baseline(main_repo)
    wt = worktree_path(project, item_id)
    if wt.exists() and (wt / ".git").exists():
        return wt   # 이미 존재 (이전 advance에서 생성됨)

    with _wt_lock:
        # 락 재확인 (다른 스레드가 막 만들었을 수 있음)
        if wt.exists() and (wt / ".git").exists():
            return wt
        wt.parent.mkdir(parents=True, exist_ok=True)
        rc, _ = run_shell(f"git rev-parse --verify {branch}", main_repo)
        if rc == 0:
            # 브랜치가 이미 있으면 그대로 체크아웃
            run_shell(f"git worktree add -f {wt} {branch}", main_repo)
        else:
            base = _trunk_ref(main_repo)
            run_shell(f"git worktree add -f {wt} -b {branch} {base}", main_repo)
    return wt


def remove_worktree(main_repo: Path, project: str, item_id: str) -> bool:
    """worktree 작업 디렉토리 제거 (브랜치/커밋은 메인 레포에 보존)."""
    wt = worktree_path(project, item_id)
    with _wt_lock:
        rc, _ = run_shell(f"git worktree remove --force {wt}", main_repo)
        run_shell("git worktree prune", main_repo)
    return rc == 0


def list_worktrees(main_repo: Path) -> str:
    rc, out = run_shell("git worktree list", main_repo)
    return out if rc == 0 else "(worktree 조회 실패)"
