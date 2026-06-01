# 진행 현황 (PROGRESS)

> 최종 갱신: 2026-06-01
> 이 문서는 사람이 읽는 로드맵/진행 기록이다. (런타임 상태는 `state/`의 스크립트가 관리)

## 한눈에 보기

- 핵심 파이프라인 **7단계 전부 동작**: SPEC → DESIGN → IMPLEMENT → TEST → REVIEW → **INTEGRATE** → DEPLOY
- 코드 규모: 하네스 본체 약 1,700줄 (Python 8파일 + `hctl` CLI) + 플러그인 스캐폴드
- 검증: 데모 작업 항목 **5건 전부 DONE** + **5건 모두 실제 `main` 병합 완료**(INTEGRATE 백필)
- **Claude Code 플러그인 전환(얇은 래퍼) 완료** — 상태=사용자 홈(`${CLAUDE_PLUGIN_DATA}`), 설정=프로젝트 `harness.yaml`
- 전체 코드 흐름 문서: [`docs/CODE-FLOW.md`](./docs/CODE-FLOW.md) (함수/클래스 단위 + mermaid + 중단/재개)

---

## ✅ 완료 (검증됨)

| # | 구성 | 파일 | 검증 |
|---|------|------|------|
| 1 | JSON 상태 계층 (유일한 기록자, 원자적 쓰기, 동시성 안전) | `harness/state.py` | WI-0001~0005 |
| 2 | 결정적 상태머신 + 게이트 | `harness/state_machine.py` | 전 항목 |
| 3 | 6단계 파이프라인 | `harness/phases.py` | WI-0003 (6단계 완주) |
| 4 | 독립 리뷰어 에이전트 + 변경요청 수정 사이클 | `phases.py` / `state_machine.py` | WI-0004·0005 (리뷰 라운드 발동) |
| 5 | 배포 전 사람 승인 게이트 (배포만 승인) | `state_machine.advance/approve` | WI-0003 (승인→배포) |
| 6 | worktree 동시 처리 + 워커 풀 | `harness/worktree.py`, `run_loop` | WI-0004·0005 병렬 |
| 7 | Agent Runner (claude CLI 헤드리스, 단계별 도구 제한) | `harness/runner.py` | 전 항목 |
| 8 | CLI (add/run/status/log/approve/projects/reindex/worktrees) | `hctl` | — |
| 9 | 트렁크 반영 INTEGRATE 단계 (direct 병합/PR, 회귀 테스트, 충돌·실패 시 abort) | `phases.py` (`_integrate_*`) | WI-0001 실제 `main` 병합 + 회귀 그린, 회귀실패·충돌 abort 단위검증 |
| 10 | worktree 자동 정리 (DONE 시 best-effort 제거, 브랜치 보존) | `state_machine.advance` | 데모 WI-0004·0005 정리, WI-0001~0005 전부 `main` 백필 |
| 11 | **플러그인 전환(얇은 래퍼)** — 엔진/상태 경로 분리, cwd/플러그인 모드, `plugin/dev-harness/` | `state.py`·`config.py`·`worktree.py`·`hctl`·`plugin/` | `claude plugin validate` ✔, 런처로 상태가 `CLAUDE_PLUGIN_DATA`에 생성됨 확인 |
| 12 | `hctl init` 스캐폴딩 — 스택별 명령 감지·`service` 블록·드라이런·git확인·깨진 yaml 친절처리 | `config.scaffold_project_yaml`·`detect_commands`·`hctl cmd_init` | Node/Python/Go… 감지, `--force` 백업, 오타키 경고 검증 |

---

## ⬜ 남은 것 (우선순위별)

### A. 지속 운영 — *원래 목표의 핵심*
- **[P1] 데몬화/스케줄링** — `run --loop`를 상주 프로세스(launchd/systemd)/cron으로. (현재 수동 호출)
- **[P1] 요구사항 자동 인입** — GitHub Issues/Slack/웹훅/이메일에서 자동 수집. (현재 `hctl add` 수동)
- [P2] idle 폴링/백오프 — 큐 빌 때 대기하다 새 요구사항 감지.
- [P2] graceful shutdown/재개 — 데몬 중단 시 진행 중 항목 안전 처리.

### B. 결과 반영 (파이프라인 빈틈)
- ✅ **[P1] main 병합 / PR 생성** — INTEGRATE 단계로 구현(`integrate.mode: direct|pr`). 게이트 통과 브랜치를 트렁크에 반영.
- ✅ [P2] 회귀 방지 — direct 병합 시 병합 결과 기준 전체 테스트 재실행, 실패하면 `merge --abort`.
- [P2] DEPLOY 강화 — 롤백, 마이그레이션, 블루/그린, 실패 자동복구.
- ✅ [P2] worktree 정리 — DONE 도달 시 `advance()`가 `remove_worktree`를 best-effort 호출(브랜치/커밋 보존). 데모 WI-0001~0005 백필 병합 후 잔여 worktree 정리 완료.
- ✅ [robustness] INTEGRATE actuator가 더러운 트렁크에 견고 — 병합 전·abort 시 `reset --hard HEAD`+`clean`으로 pristine 보장(회귀 테스트가 만든 `.pyc` 잔여로 다음 병합이 막히던 버그 수정).
- [P3] PR 모드 보강 — NEEDS_HUMAN(PR 대기) 상태에서 `hctl approve` 시 INTEGRATE 재실행으로 PR 중복 생성될 수 있음(전용 처리 필요). 원격 없는 데모에선 direct만 검증됨.

### C. 알림 — *무인 운영 시 사람을 부르는 신호*
- **[P1] NEEDS_HUMAN 알림** — 승인 대기/실패 시 푸시(Slack/데스크톱/이메일). (현재 status 수동 확인)
- [P2] 완료/실패 통지, 일일 처리 요약.

### D. 품질/안전
- **[P1] 하네스 자체 테스트** — 하네스 코드의 단위/통합 테스트. (현재 데모로 수동 검증만)
- [P2] 비용 상한/예산 — 항목별·일별 한도 초과 시 정지.
- [P2] 항목 수명 타임아웃, 엣지케이스 복구(CLI 실패/git 충돌/디스크).
- [P3] 권한 샌드박스 강화, 시크릿 관리. (현재 bypassPermissions)

### E. 관측성/운영 도구
- [P2] 메트릭 — 처리량, 단계별 성공률, 평균 비용/시간, 리뷰 라운드 통계.
- [P2] 에이전트 전체 대화 로그 저장 (진단용). (현재 result 텍스트만)
- [P3] 웹 대시보드.

### F. 워크플로 고도화
- [P2] 요구사항 분해 — 큰 요구사항 → 여러 work item.
- [P2] 작업 간 의존성 — A 완료 후 B 실행.
- [P3] 분산 실행 — 여러 머신에 워커 분산.

### G. 멀티 프로젝트
- [P2] 여러 레포 동시 운영 검증 + 도구.
- ✅ [P2] `hctl init` 스캐폴딩 + config 검증 — 스택 감지·`service` 블록·드라이런·`validate_project_yaml`·`--force` 백업. (cwd/플러그인 모드는 경로해시 id로 멀티 프로젝트 자연 지원)

### H. 사용성/하우스키핑
- [P3] `hctl cancel/requeue`, 우선순위 변경, dry-run.
- [P3] 린트 정리 — `hctl`의 미사용 `args` 경고 2건(`cmd_projects`, `cmd_reindex`).

### I. Claude Code 플러그인화 — *배포·실행 형태* (설계 확정, 얇은 래퍼 완료)
하네스는 어차피 Claude 환경 필수(`runner.py`가 `claude -p` 호출) → 플러그인이 가장 자연스러운 배포·실행 계층.
상태=`${CLAUDE_PLUGIN_DATA}`(사용자 홈), 설정=프로젝트 `harness.yaml` 커밋. **결정적 코어(상태머신·게이트·`state.py`)는 보존.**
- ✅ **얇은 래퍼** — 엔진/상태 경로 분리(env 기반 `DATA_ROOT`), cwd/플러그인 모드(`load_project_at`/`project_dir`), `plugin/dev-harness/`(`plugin.json`·`bin/hctl` 런처·`commands/{add,run,status,approve,init}.md`). `claude plugin validate` 통과.
- [P2] 풀구성 — REVIEW 독립 리뷰어를 `agents/` 서브에이전트로(읽기전용 도구제한), NEEDS_HUMAN **모니터 알림**(C 흡수), 단계 페르소나를 `agents/*.md`로 단일화하고 러너가 `claude -p --agent`로 적용(동작 동일·표현 정리).
- **[P1] 전용 trunk 워크트리** — 내장형에선 INTEGRATE의 `reset --hard`가 사용자 작업 폴더를 건드릴 위험. 병합을 전용 trunk 워크트리에서 수행해 사용자 작업트리를 격리.
- [P2] 엔진 동봉을 심링크→복사(빌드), 마켓플레이스 배포.
- ⚠️ 미해결: 중첩 `claude` 실행(비용 2겹, `run --loop`은 백그라운드), 완전 무인은 여전히 데몬/`/schedule` 필요.

---

## 권장 다음 순서

~~B(결과 반영)~~ ✅ · ~~플러그인 얇은 래퍼(I)~~ ✅ → 남은 우선순위: **I 풀구성 → C(알림) → A(자동화) → D(자체 테스트)**

1. ✅ ~~main 병합/PR~~ (INTEGRATE) · ✅ ~~worktree 자동정리~~ · ✅ ~~플러그인 얇은 래퍼·`hctl init`~~
2. **플러그인 풀구성** — 우선 **전용 trunk 워크트리**(I, `reset --hard`가 사용자 폴더 건드리는 위험 제거)가 [P1]. 이어 REVIEW 서브에이전트 + NEEDS_HUMAN 모니터 알림(C 흡수).
3. 데몬화 + 요구사항 자동 인입 — 사람 개입 없이 순환
4. 하네스 자체 테스트 — 위를 신뢰성 있게 운영하는 안전망 (INTEGRATE actuator·스캐폴딩 단위 테스트부터 코드화 권장)
