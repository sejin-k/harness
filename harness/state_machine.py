"""상태머신 — 결정적 오케스트레이터.

`advance()`가 한 작업 항목을 정확히 한 단계 전진시킨다:
  1) 현재 상태에서 실행할 단계 결정      (스크립트)
  2) git 브랜치 격리 보장                 (스크립트)
  3) 단계 에이전트 호출                    (비결정적 — runner)
  4) 게이트로 산출물 검증                  (스크립트, 결정적)
  5) 통과 → 커밋 + 다음 상태 / 실패 → 재시도 또는 NEEDS_HUMAN
모든 전이와 이벤트는 state 모듈을 통해 영속화된다.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable

from . import config, runner, state, worktree
from .phases import (PHASES, PhaseContext, TERMINAL, next_state,
                     phase_for_state, requires_approval, run_shell)

_GIT_ID = ["-c", "user.email=harness@local", "-c", "user.name=harness"]


# ── git 커밋 (항목별 worktree 안에서 동작) ──────────────────────────────

def _commit_phase(repo: Path, item_id: str, phase: str, summary: str) -> str | None:
    run_shell("git " + " ".join(_GIT_ID) + " add -A", repo)
    rc, _ = run_shell("git diff --cached --quiet", repo)
    if rc == 0:
        return None  # 커밋할 변경 없음
    msg = (f"harness({item_id}): {phase} done\n\n{summary[:500]}\n\n"
           "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    safe = msg.replace("'", "'\\''")
    run_shell("git " + " ".join(_GIT_ID) + f" commit -q -m '{safe}'", repo)
    rc, out = run_shell("git rev-parse --short HEAD", repo)
    return out.strip() if rc == 0 else None


# ── 핵심 전이 ───────────────────────────────────────────────────────────

def advance(item_id: str) -> dict[str, Any]:
    """작업 항목 하나를 한 단계 전진시키고 결과 요약을 반환."""
    item = state.load_item(item_id)
    cur = item["state"]

    if cur in TERMINAL:
        return {"item": item_id, "action": "skip", "state": cur,
                "reason": f"종료 상태({cur})"}

    phase_name = phase_for_state(cur)
    if phase_name is None:
        item["state"] = "NEEDS_HUMAN"
        item["last_error"] = f"알 수 없는 상태: {cur}"
        state.save_item(item)
        state.append_event(item_id, "needs_human", {"reason": item["last_error"]})
        return {"item": item_id, "action": "error", "state": "NEEDS_HUMAN",
                "reason": item["last_error"]}

    gcfg = config.load_global()
    pcfg = config.load_project(item["project"])
    main_repo = Path(pcfg["repo"])

    # 승인 게이트(단계 실행 *전*): require_human이고 아직 미승인이면 멈춘다.
    # 자율성 정책상 보통 DEPLOY에만 걸린다. 실제 배포는 hctl approve 후 실행.
    if requires_approval(phase_name, pcfg) and not (item.get("approvals") or {}).get(phase_name):
        item["state"] = "NEEDS_HUMAN"
        item["pending_phase"] = phase_name
        item["pending_reason"] = f"{phase_name} 사람 승인 대기"
        item["last_error"] = None
        state.save_item(item)
        state.append_event(item_id, "awaiting_approval", {"phase": phase_name})
        return {"item": item_id, "action": "awaiting_approval", "phase": phase_name,
                "state": "NEEDS_HUMAN", "reason": item["pending_reason"]}

    # 단계 시작: 상태를 현재 단계로 claim, 시도 횟수 증가
    item["state"] = phase_name
    item["attempts"][phase_name] = item["attempts"].get(phase_name, 0) + 1
    attempt = item["attempts"][phase_name]
    state.save_item(item)

    # 항목 전용 worktree 격리 보장 (동시 처리 시 작업 트리 충돌 방지)
    repo = worktree.ensure_worktree(main_repo, item["project"], item_id, item["branch"])
    artifacts_dir = repo / ".harness" / item_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 리뷰어 diff 기준점이 될 베이스 커밋을 한 번만 기록 (worktree의 분기 시작점)
    if not item.get("base_commit"):
        rc, out = run_shell("git rev-parse HEAD", repo)
        if rc == 0:
            item["base_commit"] = out.strip()
            state.save_item(item)

    phase = PHASES[phase_name]
    ctx = PhaseContext(item=item, project_cfg=pcfg, repo=repo, artifacts_dir=artifacts_dir)

    state.append_event(item_id, "phase_start",
                       {"phase": phase_name, "attempt": attempt})

    # 1) 단계 실행
    if phase.build_prompt is None:
        # 스크립트 전용 단계 (예: DEPLOY) — 에이전트 없이 actuator를 결정적으로 실행
        ok, out = (True, "(no actuator)")
        if phase.actuator:
            ok, out = phase.actuator(ctx)
        run = runner.RunResult(ok=ok, text=out, error="" if ok else "actuator 실패")
        state.append_event(item_id, "actuator_done",
                           {"phase": phase_name, "ok": ok})
    else:
        # 에이전트 호출 (비결정적)
        run = runner.run_agent(
            prompt=phase.build_prompt(ctx),
            system=phase.system,
            allowed_tools=phase.allowed_tools,
            cwd=str(repo),
            model=pcfg.get("model") or gcfg.get("model", ""),
            permission_mode=gcfg.get("permission_mode", "bypassPermissions"),
            timeout_sec=int(gcfg.get("runner_timeout_sec", 1200)),
        )
        state.append_event(item_id, "agent_done", {
            "phase": phase_name, "ok": run.ok, "cost_usd": run.cost_usd,
            "turns": run.num_turns, "error": run.error,
        })

    max_attempts = int(gcfg.get("max_attempts", 2))

    if not run.ok:
        return _handle_failure(item, phase_name, attempt, max_attempts,
                               f"agent 실패: {run.error}")

    # 2) 게이트 검증 (결정적)
    gate = phase.gate(ctx, run)
    state.append_event(item_id, "gate", {
        "phase": phase_name, "passed": gate.passed,
        "detail": gate.detail, "checks": gate.checks,
    })

    if not gate.passed:
        if gate.route_to:   # 예: 리뷰어 CHANGES_REQUESTED → IMPLEMENT 수정 사이클
            return _handle_route(item, phase_name, gate, gcfg)
        return _handle_failure(item, phase_name, attempt, max_attempts,
                               f"게이트 실패: {gate.detail}")

    # INTEGRATE(PR 모드)는 PR 생성으로 하네스 역할이 끝난다 — DEPLOY로 자동 진행하지 않고
    # 사람이 PR을 머지/배포하도록 NEEDS_HUMAN으로 멈춘다.
    if phase_name == "INTEGRATE" and (pcfg.get("integrate") or {}).get("mode", "direct") == "pr":
        item = state.load_item(item_id)
        item["artifacts"][phase_name] = {"commit": None, "gate_detail": gate.detail}
        item["state"] = "NEEDS_HUMAN"
        item["pending_reason"] = "PR 생성됨 — 사람이 머지/배포"
        item["last_error"] = None
        state.save_item(item)
        state.append_event(item_id, "needs_human",
                           {"phase": phase_name, "reason": item["pending_reason"]})
        return {"item": item_id, "action": "pr_open", "phase": phase_name,
                "state": "NEEDS_HUMAN", "reason": item["pending_reason"]}

    # 3) 통과 → 커밋 + 다음 상태
    commit = _commit_phase(repo, item_id, phase_name, run.text or gate.detail)
    item = state.load_item(item_id)
    item["artifacts"][phase_name] = {
        "commit": commit,
        "gate_detail": gate.detail,
        "cost_usd": run.cost_usd,
    }
    nxt = next_state(phase_name)
    item["state"] = nxt
    item["last_error"] = None
    state.save_item(item)
    state.append_event(item_id, "phase_done",
                       {"phase": phase_name, "commit": commit, "next": nxt})

    return {"item": item_id, "action": "advanced", "phase": phase_name,
            "state": nxt, "commit": commit, "cost_usd": run.cost_usd,
            "detail": gate.detail}


def _handle_route(item: dict, from_phase: str, gate, gcfg: dict) -> dict[str, Any]:
    """게이트의 route_to에 따라 비선형 전이. (리뷰어 변경요청 → 수정 사이클)"""
    item = state.load_item(item["id"])
    item["review_rounds"] = item.get("review_rounds", 0) + 1
    item["last_review"] = gate.detail
    cap = int(gcfg.get("max_review_rounds", 2))

    if item["review_rounds"] > cap:
        item["state"] = "NEEDS_HUMAN"
        item["last_error"] = f"리뷰 라운드 한도({cap}) 초과: {gate.detail}"
        state.save_item(item)
        state.append_event(item["id"], "needs_human",
                           {"phase": from_phase, "reason": item["last_error"]})
        return {"item": item["id"], "action": "needs_human", "phase": from_phase,
                "state": "NEEDS_HUMAN", "reason": item["last_error"]}

    target = gate.route_to
    # 수정 사이클: 되돌아가는 단계들의 시도 횟수를 초기화해 새 예산으로 재실행
    for p in ("IMPLEMENT", "TEST", "REVIEW"):
        item["attempts"][p] = 0
    item["state"] = target
    state.save_item(item)
    state.append_event(item["id"], "review_changes",
                       {"from": from_phase, "route_to": target,
                        "round": item["review_rounds"], "findings": gate.detail})
    return {"item": item["id"], "action": "review_changes", "phase": from_phase,
            "state": target, "reason": gate.detail, "round": item["review_rounds"]}


def _handle_failure(item: dict, phase: str, attempt: int, max_attempts: int,
                    reason: str) -> dict[str, Any]:
    item = state.load_item(item["id"])
    item["last_error"] = reason
    if attempt >= max_attempts:
        item["state"] = "NEEDS_HUMAN"
        state.save_item(item)
        state.append_event(item["id"], "needs_human",
                           {"phase": phase, "reason": reason, "attempts": attempt})
        return {"item": item["id"], "action": "needs_human", "phase": phase,
                "state": "NEEDS_HUMAN", "reason": reason}
    # 재시도 여지: 같은 단계 상태로 둔다 (다음 advance에서 재실행)
    item["state"] = phase
    state.save_item(item)
    state.append_event(item["id"], "retry_pending",
                       {"phase": phase, "reason": reason, "attempt": attempt})
    return {"item": item["id"], "action": "retry", "phase": phase,
            "state": phase, "reason": reason, "attempt": attempt}


# ── 큐에서 다음 작업 선택 (지속 운영 루프용) ────────────────────────────

def pick_next() -> str | None:
    """우선순위(낮을수록 먼저) → 오래된 순으로 실행 가능한 항목 1건 선택."""
    candidates = [it for it in state.list_items() if it["state"] not in TERMINAL]
    if not candidates:
        return None
    candidates.sort(key=lambda it: (it.get("priority", 100), it.get("created_at", "")))
    return candidates[0]["id"]


# ── 동시 처리 스케줄러 (worktree 격리 기반) ─────────────────────────────

_PROJECT_CAP_CACHE: dict[str, int] = {}


def _project_cap(project: str) -> int:
    """프로젝트별 동시 처리 한도 (harness.yaml의 concurrency)."""
    if project not in _PROJECT_CAP_CACHE:
        try:
            _PROJECT_CAP_CACHE[project] = max(1, int(
                config.load_project(project).get("concurrency", 1)))
        except Exception:
            _PROJECT_CAP_CACHE[project] = 1
    return _PROJECT_CAP_CACHE[project]


def _select(busy: set[str], active_by_project: dict[str, int]) -> str | None:
    """진행 중(busy)이 아니고 프로젝트 동시 한도를 넘지 않는 다음 항목 선택."""
    cands = [it for it in state.list_items()
             if it["state"] not in TERMINAL and it["id"] not in busy]
    cands.sort(key=lambda it: (it.get("priority", 100), it.get("created_at", "")))
    for it in cands:
        if active_by_project.get(it["project"], 0) < _project_cap(it["project"]):
            return it["id"]
    return None


def run_loop(workers: int = 2, max_steps: int = 100,
             on_result: Callable[[dict], None] | None = None) -> dict[str, Any]:
    """여러 작업 항목을 worktree 격리 하에 동시 처리한다.

    각 항목은 자신의 worktree에서 advance()로 한 단계씩 전진하며, 여러 항목이
    병렬로 진행된다. 항목당 한 번에 하나의 advance만 실행(busy 집합으로 보장),
    프로젝트별 concurrency 한도를 준수한다.
    """
    _PROJECT_CAP_CACHE.clear()
    results: list[dict] = []
    in_flight: dict[Any, str] = {}          # future -> item_id
    active_by_project: dict[str, int] = {}
    steps = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        while steps < max_steps:
            # 가용 워커만큼 작업 제출
            while len(in_flight) < workers:
                item_id = _select(set(in_flight.values()), active_by_project)
                if not item_id:
                    break
                proj = state.load_item(item_id)["project"]
                active_by_project[proj] = active_by_project.get(proj, 0) + 1
                in_flight[ex.submit(advance, item_id)] = item_id

            if not in_flight:
                break

            done, _ = wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
            for fut in done:
                item_id = in_flight.pop(fut)
                steps += 1
                try:
                    res = fut.result()
                except Exception as e:   # advance 내부 예외 격리
                    res = {"item": item_id, "action": "error", "reason": repr(e)}
                proj = state.load_item(item_id)["project"]
                active_by_project[proj] = max(0, active_by_project.get(proj, 1) - 1)
                results.append(res)
                if on_result:
                    on_result(res)

    return {"steps": steps, "results": results}


def approve(item_id: str) -> dict[str, Any]:
    """NEEDS_HUMAN 항목을 사람이 승인해 재개시킨다.

    두 종류의 NEEDS_HUMAN을 구분한다:
      1) 승인 대기(pending_phase 있음): 해당 단계(예: DEPLOY) 실행을 *허가*한다.
      2) 실패성 멈춤(pending_phase 없음): 마지막 시도 단계를 재개한다.
    """
    item = state.load_item(item_id)
    if item["state"] != "NEEDS_HUMAN":
        return {"item": item_id, "action": "noop",
                "reason": f"NEEDS_HUMAN 아님 (현재 {item['state']})"}

    pending = item.get("pending_phase")
    if pending:
        # 1) 승인 부여 → 해당 단계 실행 허가
        item.setdefault("approvals", {})[pending] = {"at": state.now_iso(), "by": "human"}
        item["state"] = pending
        item["pending_phase"] = None
        item["pending_reason"] = None
        item["last_error"] = None
        state.save_item(item)
        state.append_event(item_id, "approved", {"phase": pending, "kind": "gate"})
        return {"item": item_id, "action": "approved", "state": pending,
                "reason": f"{pending} 실행 승인됨"}

    # 2) 실패성 멈춤 → 마지막 시도 단계 재개 (시도 횟수 초기화)
    phase = phase_for_state("QUEUED")
    for p in ("DEPLOY", "REVIEW", "TEST", "IMPLEMENT", "DESIGN", "SPEC"):
        if p in item["attempts"]:
            phase = p
            break
    item["attempts"][phase] = 0
    item["state"] = phase
    item["last_error"] = None
    state.save_item(item)
    state.append_event(item_id, "approved", {"resume_phase": phase, "kind": "resume"})
    return {"item": item_id, "action": "approved", "state": phase}
