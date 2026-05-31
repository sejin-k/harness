"""단계 정의 — 각 SDLC 단계의 (프롬프트 + 도구 스코프 + 결정적 게이트).

게이트(gate)가 이 시스템의 핵심이다. 에이전트의 산출물을 *스크립트가* 검증해
통과/실패를 판정한다. LLM의 자기 보고를 신뢰하지 않는다.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .state import HARNESS_HOME

PROMPTS_DIR = HARNESS_HOME / "prompts"

# 파이프라인 순서 (서비스 개발).
# INTEGRATE = 게이트를 통과한 항목 브랜치를 트렁크에 반영 (병합/PR). DEPLOY 직전.
PIPELINE = ["SPEC", "DESIGN", "IMPLEMENT", "TEST", "REVIEW", "INTEGRATE", "DEPLOY"]
TERMINAL = {"DONE", "FAILED", "NEEDS_HUMAN"}


@dataclass
class PhaseContext:
    item: dict[str, Any]
    project_cfg: dict[str, Any]
    repo: Path
    artifacts_dir: Path          # repo/.harness/<item_id>

    @property
    def spec_path(self) -> Path:
        return self.artifacts_dir / "spec.md"

    @property
    def design_path(self) -> Path:
        return self.artifacts_dir / "design.md"


@dataclass
class GateResult:
    passed: bool
    detail: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    # 통과 실패 시, 표준 재시도 대신 특정 상태로 라우팅 (예: REVIEW→IMPLEMENT 수정 사이클)
    route_to: str | None = None


@dataclass
class Phase:
    name: str
    allowed_tools: list[str]
    system: str
    prompt_template: str                       # prompts/ 내 파일명 ("" = 스크립트 전용)
    # build_prompt가 None이면 에이전트를 호출하지 않는 '스크립트 전용' 단계(예: DEPLOY).
    build_prompt: Callable[[PhaseContext], str] | None
    gate: Callable[[PhaseContext, Any], GateResult]
    # 스크립트 전용 단계의 실행자(actuator). (ok, output) 반환.
    actuator: Callable[[PhaseContext], tuple[bool, str]] | None = None


# ── 공통 헬퍼 ───────────────────────────────────────────────────────────

def run_shell(cmd: str, cwd: Path, timeout: int = 600) -> tuple[int, str]:
    """게이트 검증용 셸 명령 실행. (rc, 합쳐진 출력) 반환."""
    if not cmd.strip():
        return 0, "(명령 없음 — 생략)"
    try:
        p = subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"


def git_has_changes(repo: Path) -> bool:
    rc, out = run_shell("git status --porcelain", repo)
    return rc == 0 and out.strip() != "" and out.strip() != "(명령 없음 — 생략)"


def _load_template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _read_spec(ctx: PhaseContext) -> str:
    if ctx.spec_path.exists():
        return ctx.spec_path.read_text(encoding="utf-8")
    return "(아직 명세 파일 없음)"


def _read_design(ctx: PhaseContext) -> str:
    if ctx.design_path.exists():
        return ctx.design_path.read_text(encoding="utf-8")
    return "(설계 파일 없음)"


def _extract_json(text: str) -> dict[str, Any] | None:
    """리뷰어 출력 텍스트에서 JSON 판정 블록을 추출."""
    if not text:
        return None
    # 1) ```json ... ``` 코드펜스 우선
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [m.group(1)] if m else []
    # 2) 마지막 중괄호 블록 fallback
    last = text.rfind("{")
    if last != -1:
        candidates.append(text[last:text.rfind("}") + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and "verdict" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


# ── SPEC ────────────────────────────────────────────────────────────────

def _spec_prompt(ctx: PhaseContext) -> str:
    return _load_template("spec.md").format(
        project=ctx.project_cfg["project"],
        item_id=ctx.item["id"],
        requirement=ctx.item["requirement"],
        spec_path=str(ctx.spec_path),
    )


def _spec_gate(ctx: PhaseContext, _run) -> GateResult:
    checks = []
    if not ctx.spec_path.exists():
        return GateResult(False, f"명세 파일 미생성: {ctx.spec_path}")
    text = ctx.spec_path.read_text(encoding="utf-8")
    checks.append({"check": "spec_exists", "ok": True})

    has_ac = ("수용 기준" in text) or ("Acceptance Criteria" in text.lower().title()) \
             or ("acceptance criteria" in text.lower())
    checks.append({"check": "has_acceptance_criteria", "ok": has_ac})

    n_boxes = text.count("- [ ]") + text.count("- [x]") + text.count("- [X]")
    enough = n_boxes >= 3
    checks.append({"check": "min_3_criteria", "ok": enough, "count": n_boxes})

    passed = has_ac and enough
    detail = "수용 기준 OK" if passed else "수용 기준 누락 또는 3개 미만"
    return GateResult(passed, detail, checks)


# ── DESIGN ──────────────────────────────────────────────────────────────

def _design_prompt(ctx: PhaseContext) -> str:
    return _load_template("design.md").format(
        project=ctx.project_cfg["project"],
        item_id=ctx.item["id"],
        repo=str(ctx.repo),
        spec_path=str(ctx.spec_path),
        spec_content=_read_spec(ctx),
        design_path=str(ctx.design_path),
    )


def _design_gate(ctx: PhaseContext, _run) -> GateResult:
    checks = []
    if not ctx.design_path.exists():
        return GateResult(False, f"설계 파일 미생성: {ctx.design_path}")
    text = ctx.design_path.read_text(encoding="utf-8")
    checks.append({"check": "design_exists", "ok": True})

    has_approach = ("접근 방식" in text) or ("approach" in text.lower())
    checks.append({"check": "has_approach", "ok": has_approach})

    has_files = ("변경" in text or "파일" in text or "files" in text.lower())
    checks.append({"check": "has_files_section", "ok": has_files})

    has_iface = ("인터페이스" in text or "시그니처" in text
                 or "interface" in text.lower() or "signature" in text.lower())
    checks.append({"check": "has_interface", "ok": has_iface})

    mentions_path = bool(re.search(r"[\w/]+\.\w+", text))  # 파일 경로 토큰 존재
    checks.append({"check": "mentions_file_path", "ok": mentions_path})

    passed = has_approach and has_files and has_iface and mentions_path
    detail = "설계 섹션 충족" if passed else "설계 필수 섹션 누락"
    return GateResult(passed, detail, checks)


# ── IMPLEMENT ─────────────────────────────────────────────────────────────

def _implement_prompt(ctx: PhaseContext) -> str:
    cmds = ctx.project_cfg["commands"]
    review_note = ""
    last_review = ctx.item.get("last_review")
    if last_review:
        review_note = (
            "\n# 직전 리뷰에서 요청된 수정 사항 (반드시 반영)\n"
            f"{last_review}\n"
        )
    return _load_template("implement.md").format(
        project=ctx.project_cfg["project"],
        item_id=ctx.item["id"],
        repo=str(ctx.repo),
        spec_path=str(ctx.spec_path),
        spec_content=_read_spec(ctx),
        build_cmd=cmds.get("build", "") or "(없음)",
        lint_cmd=cmds.get("lint", "") or "(없음)",
    ) + (
        f"\n\n# 설계 (이 설계를 따르라)\n{_read_design(ctx)}" + review_note
    )


def _implement_gate(ctx: PhaseContext, _run) -> GateResult:
    checks = []
    changed = git_has_changes(ctx.repo)
    checks.append({"check": "code_changed", "ok": changed})
    if not changed:
        return GateResult(False, "작업 트리에 변경 사항 없음 (구현되지 않음)", checks)

    cmds = ctx.project_cfg["commands"]
    for name in ("build", "lint"):
        cmd = cmds.get(name, "")
        if cmd.strip():
            rc, out = run_shell(cmd, ctx.repo)
            ok = rc == 0
            checks.append({"check": name, "ok": ok, "rc": rc, "tail": out[-500:]})
            if not ok:
                return GateResult(False, f"{name} 실패 (rc={rc})", checks)
    return GateResult(True, "구현 + 빌드/린트 통과", checks)


# ── TEST ──────────────────────────────────────────────────────────────────

def _test_prompt(ctx: PhaseContext) -> str:
    cmds = ctx.project_cfg["commands"]
    return _load_template("test.md").format(
        project=ctx.project_cfg["project"],
        item_id=ctx.item["id"],
        repo=str(ctx.repo),
        spec_path=str(ctx.spec_path),
        spec_content=_read_spec(ctx),
        test_cmd=cmds.get("test", "") or "(없음)",
    )


def _test_gate(ctx: PhaseContext, _run) -> GateResult:
    cmds = ctx.project_cfg["commands"]
    test_cmd = cmds.get("test", "")
    if not test_cmd.strip():
        return GateResult(False, "테스트 명령(commands.test)이 설정되지 않음")
    require_pass = ctx.project_cfg.get("gates", {}).get("test", {}).get("require_pass", True)
    rc, out = run_shell(test_cmd, ctx.repo)
    ok = (rc == 0) if require_pass else True
    checks = [{"check": "test_command", "ok": ok, "rc": rc, "tail": out[-1000:]}]
    detail = "테스트 통과" if ok else f"테스트 실패 (rc={rc})"
    return GateResult(ok, detail, checks)


# ── REVIEW (독립 리뷰어 에이전트) ───────────────────────────────────────

def _review_prompt(ctx: PhaseContext) -> str:
    cmds = ctx.project_cfg["commands"]
    base = ctx.item.get("base_commit", "")
    rng = f"{base}..HEAD" if base else "HEAD~3..HEAD"
    rc, diff = run_shell(f"git diff {rng}", ctx.repo)
    if rc != 0 or not diff.strip():
        diff = "(diff를 가져오지 못함 — git diff 로 직접 확인하라)"
    return _load_template("review.md").format(
        project=ctx.project_cfg["project"],
        item_id=ctx.item["id"],
        repo=str(ctx.repo),
        spec_path=str(ctx.spec_path),
        design_path=str(ctx.design_path),
        diff=diff[:6000],
        base=base or "<baseline>",
        test_cmd=cmds.get("test", "") or "(없음)",
    )


def _review_gate(ctx: PhaseContext, run) -> GateResult:
    """객관적 floor(테스트 재실행) + 독립 리뷰어의 구조화된 판정."""
    cmds = ctx.project_cfg["commands"]
    checks = []

    verdict = _extract_json(getattr(run, "text", "") or "")
    if not verdict:
        return GateResult(False, "리뷰어 판정(JSON) 파싱 실패")
    v = str(verdict.get("verdict", "")).upper()
    blocking = verdict.get("blocking_findings") or []
    checks.append({"check": "reviewer_verdict", "verdict": v,
                   "blocking": blocking, "summary": verdict.get("summary", "")})

    # 객관적 floor: 테스트가 여전히 통과하는가
    test_cmd = cmds.get("test", "")
    if test_cmd.strip():
        rc, out = run_shell(test_cmd, ctx.repo)
        tests_ok = rc == 0
        checks.append({"check": "tests_still_green", "ok": tests_ok, "rc": rc,
                       "tail": out[-600:]})
        if not tests_ok:
            return GateResult(False, f"리뷰 시점 테스트 실패 (rc={rc})",
                              checks, route_to="IMPLEMENT")

    if "PASS" in v and not blocking:
        return GateResult(True, f"리뷰 통과: {verdict.get('summary', '')}", checks)

    findings = "; ".join(str(b) for b in blocking) or verdict.get("summary", "변경 요청")
    return GateResult(False, f"리뷰어 CHANGES_REQUESTED: {findings}",
                      checks, route_to="IMPLEMENT")


# ── INTEGRATE (스크립트 전용 — 트렁크 반영: 병합 또는 PR) ────────────────
#
# 게이트를 통과한 항목 브랜치(harness/WI-xxxx)를 트렁크에 반영해 사이클을 닫는다.
# 다른 단계들과 달리 *메인 레포*에서 동작한다(브랜치를 트렁크로 합치는 작업).
# 동시 INTEGRATE가 메인 레포의 작업트리/HEAD를 동시에 건드리지 않도록 락으로 직렬화한다.

_GIT_ID = "-c user.email=harness@local -c user.name=harness"
_integrate_lock = threading.Lock()


def _trunk_ref(repo: Path) -> str:
    for ref in ("main", "master"):
        rc, _ = run_shell(f"git rev-parse --verify {ref}", repo)
        if rc == 0:
            return ref
    rc, out = run_shell("git rev-parse --abbrev-ref HEAD", repo)
    return out.strip() or "HEAD"


def _reset_trunk(main_repo: Path) -> None:
    """트렁크 작업트리를 HEAD 기준 pristine 상태로 강제한다.

    하네스 불변식상 메인 레포 작업트리에는 커밋되지 않은 '정상 작업'이 없다(모든 작업은
    worktree에서). 하지만 회귀 테스트를 트렁크에서 돌리면 .pyc 등 부산물이 생겨 다음 병합이
    'local changes would be overwritten'으로 막힐 수 있다. reset --hard(추적 파일 복원) +
    clean(미추적 제거)으로 이를 제거한다. merge --abort는 추적-수정 파일을 복원하지 못하므로
    abort 경로에서도 이 함수를 쓴다."""
    run_shell(f"git {_GIT_ID} reset -q --hard HEAD", main_repo)
    run_shell("git clean -fdq", main_repo)


def _abort_merge(main_repo: Path) -> None:
    """진행 중 머지를 되돌리고 트렁크를 HEAD 기준 pristine 상태로 복원한다."""
    run_shell("git merge --abort", main_repo)
    _reset_trunk(main_repo)


def _integrate_direct(ctx: PhaseContext, main_repo: Path, branch: str,
                      item_id: str) -> tuple[bool, str]:
    """브랜치를 트렁크에 직접 병합한다. 회귀 테스트 통과 시에만 머지를 확정."""
    trunk = _trunk_ref(main_repo)
    run_shell(f"git {_GIT_ID} checkout -q {trunk}", main_repo)
    # 병합 전 트렁크 작업트리를 깨끗이 보장 (직전 회귀 테스트의 .pyc 잔여 등 제거)
    _reset_trunk(main_repo)

    # --no-commit: 회귀 테스트가 통과해야만 머지 커밋을 만든다.
    rc, out = run_shell(f"git {_GIT_ID} merge --no-ff --no-commit {branch}", main_repo)
    if rc != 0:
        _abort_merge(main_repo)
        return False, f"병합 충돌/실패 (rc={rc})\n{out[-800:]}"

    # 이미 반영되어 변경할 게 없으면(staged 비어있음) 그대로 통과
    staged, _ = run_shell("git diff --cached --quiet", main_repo)
    if staged == 0:
        return True, f"{trunk}에 이미 반영됨 (변경 없음)"

    # 회귀 방지: 트렁크(병합 결과) 기준으로 전체 테스트 재실행
    test_cmd = ctx.project_cfg["commands"].get("test", "")
    if test_cmd.strip():
        trc, tout = run_shell(test_cmd, main_repo)
        if trc != 0:
            _abort_merge(main_repo)
            return False, f"트렁크 회귀 테스트 실패 (rc={trc})\n{tout[-800:]}"

    msg = (f"harness({item_id}): integrate {branch} into {trunk}\n\n"
           "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    safe = msg.replace("'", "'\\''")
    run_shell(f"git {_GIT_ID} commit -q -m '{safe}'", main_repo)
    rc2, sha = run_shell("git rev-parse --short HEAD", main_repo)
    return True, f"{trunk}에 병합 완료 ({sha.strip()}) — 회귀 테스트 통과"


def _integrate_pr(main_repo: Path, branch: str, item_id: str) -> tuple[bool, str]:
    """브랜치를 원격에 push하고 gh로 PR을 생성한다 (사람 머지/배포 대기)."""
    rc, _ = run_shell("git remote get-url origin", main_repo)
    if rc != 0:
        return False, "PR 모드인데 origin 원격이 없음 — git remote 설정 필요"
    prc, pout = run_shell(f"git push -u origin {branch}", main_repo)
    if prc != 0:
        return False, f"브랜치 push 실패 (rc={prc})\n{pout[-600:]}"
    title = f"harness({item_id}): {branch}"
    body = "하네스 파이프라인(SPEC~REVIEW) 통과 산출물. 사람 머지/배포 대기."
    grc, gout = run_shell(
        f"gh pr create --head {branch} --title '{title}' --body '{body}'", main_repo)
    if grc != 0:
        return False, f"gh pr create 실패 (gh CLI/권한 확인, rc={grc})\n{gout[-600:]}"
    return True, f"PR 생성됨: {gout.strip()[-300:]}"


def _integrate_actuator(ctx: PhaseContext) -> tuple[bool, str]:
    """integrate.mode에 따라 트렁크에 직접 병합(direct)하거나 PR을 생성(pr)한다."""
    main_repo = Path(ctx.project_cfg["repo"])
    branch = ctx.item["branch"]
    item_id = ctx.item["id"]
    mode = (ctx.project_cfg.get("integrate") or {}).get("mode", "direct")
    with _integrate_lock:
        if mode == "pr":
            return _integrate_pr(main_repo, branch, item_id)
        return _integrate_direct(ctx, main_repo, branch, item_id)


def _integrate_gate(ctx: PhaseContext, run) -> GateResult:
    """통합 actuator 결과를 확인한다 (병합/PR 자체가 결정적 판정)."""
    ok = getattr(run, "ok", False)
    detail = (getattr(run, "text", "") or "")[:400]
    checks = [{"check": "integrate", "ok": ok}]
    return GateResult(ok, detail if ok else f"통합 실패: {detail}", checks)


# ── DEPLOY (스크립트 전용 — 사람 승인 후 결정적 실행) ───────────────────

def _deploy_actuator(ctx: PhaseContext) -> tuple[bool, str]:
    """배포 명령을 결정적으로 실행한다 (에이전트 없음)."""
    cmd = ctx.project_cfg["commands"].get("deploy", "")
    if not cmd.strip():
        return True, "(deploy 명령 미설정 — 실행 생략)"
    rc, out = run_shell(cmd, ctx.repo)
    return rc == 0, f"$ {cmd}\nrc={rc}\n{out[-1500:]}"


def _deploy_gate(ctx: PhaseContext, run) -> GateResult:
    """배포 후 헬스체크로 기동을 검증한다."""
    checks = [{"check": "deploy_command", "ok": getattr(run, "ok", False)}]
    health = ctx.project_cfg.get("service", {}).get("health_check", "")
    if not health.strip():
        return GateResult(True, "배포 완료 (헬스체크 미설정)", checks)
    rc, out = run_shell(health, ctx.repo)
    ok = rc == 0
    checks.append({"check": "health_check", "ok": ok, "rc": rc, "tail": out[-500:]})
    return GateResult(ok, "헬스체크 통과" if ok else f"헬스체크 실패 (rc={rc})", checks)


def requires_approval(phase_name: str, project_cfg: dict[str, Any]) -> bool:
    """단계 실행 전 사람 승인이 필요한가? (자율성 정책: 배포만 승인)"""
    gate_cfg = project_cfg.get("gates", {}).get(phase_name.lower(), {})
    return bool(gate_cfg.get("require_human", False))


# ── 레지스트리 ──────────────────────────────────────────────────────────

PHASES: dict[str, Phase] = {
    "SPEC": Phase(
        name="SPEC",
        allowed_tools=["Read", "Write"],
        system="너는 명세 단계 작업자다. 코드는 건드리지 말고 명세 파일만 생성하라.",
        prompt_template="spec.md",
        build_prompt=_spec_prompt,
        gate=_spec_gate,
    ),
    "DESIGN": Phase(
        name="DESIGN",
        allowed_tools=["Read", "Write"],
        system="너는 설계 단계 작업자다. 코드는 건드리지 말고 설계 문서만 생성하라.",
        prompt_template="design.md",
        build_prompt=_design_prompt,
        gate=_design_gate,
    ),
    "IMPLEMENT": Phase(
        name="IMPLEMENT",
        allowed_tools=["Read", "Write", "Edit", "Bash"],
        system="너는 구현 단계 작업자다. 명세 범위 내에서 서비스 코드를 구현하라.",
        prompt_template="implement.md",
        build_prompt=_implement_prompt,
        gate=_implement_gate,
    ),
    "TEST": Phase(
        name="TEST",
        allowed_tools=["Read", "Write", "Edit", "Bash"],
        system="너는 테스트 단계 작업자다. 수용 기준을 검증하는 테스트를 작성해 통과시켜라.",
        prompt_template="test.md",
        build_prompt=_test_prompt,
        gate=_test_gate,
    ),
    "REVIEW": Phase(
        name="REVIEW",
        # 읽기 전용: 리뷰어는 코드를 수정할 수 없다 (Edit/Write 없음)
        allowed_tools=["Read", "Bash"],
        system=("너는 이 변경을 구현하지 않은 독립 코드 리뷰어다. 코드를 수정하지 말고 "
                "비판적으로 검토한 뒤 마지막에 JSON 판정만 출력하라."),
        prompt_template="review.md",
        build_prompt=_review_prompt,
        gate=_review_gate,
    ),
    "INTEGRATE": Phase(
        name="INTEGRATE",
        allowed_tools=[],            # 스크립트 전용 — 에이전트 호출 없음
        system="",
        prompt_template="",
        build_prompt=None,
        gate=_integrate_gate,
        actuator=_integrate_actuator,
    ),
    "DEPLOY": Phase(
        name="DEPLOY",
        allowed_tools=[],            # 스크립트 전용 — 에이전트 호출 없음
        system="",
        prompt_template="",
        build_prompt=None,
        gate=_deploy_gate,
        actuator=_deploy_actuator,
    ),
}


def phase_for_state(state: str) -> str | None:
    """현재 상태에서 실행해야 할 단계명. QUEUED는 첫 단계(SPEC)로 매핑."""
    if state == "QUEUED":
        return PIPELINE[0]
    if state in PIPELINE:
        return state
    return None


def next_state(phase_name: str) -> str:
    i = PIPELINE.index(phase_name)
    return PIPELINE[i + 1] if i + 1 < len(PIPELINE) else "DONE"
