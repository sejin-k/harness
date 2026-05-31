"""Agent Runner — 비결정적 작업자(Claude) 호출 계층.

백엔드는 `claude` CLI 헤드리스 모드(`-p --output-format json`)를 사용한다.
(claude-agent-sdk가 설치되면 동일 인터페이스로 교체 가능하도록 격리)

결정성 경계
-----------
Runner는 '에이전트가 무엇을 만들었는가'를 그대로 보고할 뿐,
합격/불합격 판정은 하지 않는다. 판정은 state_machine의 게이트(스크립트)가 한다.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunResult:
    ok: bool                       # 프로세스 정상 종료 + 에이전트 비오류
    text: str = ""                 # 에이전트 최종 응답 텍스트
    raw: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    num_turns: int = 0
    error: str = ""                # 실패 사유 (런타임/타임아웃 등)


def run_agent(
    *,
    prompt: str,
    system: str,
    allowed_tools: list[str],
    cwd: str,
    model: str = "",
    permission_mode: str = "bypassPermissions",
    timeout_sec: int = 1200,
) -> RunResult:
    """단계 프롬프트로 claude CLI를 헤드리스 실행한다.

    allowed_tools 로 단계별 도구를 제한한다(최소 권한). 예: ["Read"] 또는
    ["Read", "Write", "Edit", "Bash"].
    """
    cmd: list[str] = [
        "claude", "-p", prompt,
        "--append-system-prompt", system,
        "--output-format", "json",
        "--permission-mode", permission_mode,
        "--add-dir", cwd,
    ]
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    if model:
        cmd += ["--model", model]

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return RunResult(ok=False, error=f"timeout after {timeout_sec}s")
    except FileNotFoundError:
        return RunResult(ok=False, error="claude CLI를 찾을 수 없음 (PATH 확인)")

    if proc.returncode != 0:
        return RunResult(
            ok=False,
            error=f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout)[:2000]}",
        )

    raw: dict[str, Any] = {}
    text = proc.stdout
    try:
        raw = json.loads(proc.stdout)
        text = raw.get("result", proc.stdout)
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 원시 출력을 텍스트로 보존
        pass

    is_error = bool(raw.get("is_error", False))
    return RunResult(
        ok=not is_error,
        text=text if isinstance(text, str) else json.dumps(text, ensure_ascii=False),
        raw=raw,
        cost_usd=float(raw.get("total_cost_usd", 0.0) or 0.0),
        num_turns=int(raw.get("num_turns", 0) or 0),
        error="" if not is_error else "agent reported is_error",
    )
