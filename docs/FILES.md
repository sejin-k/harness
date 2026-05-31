# 파일별 역할 (FILES)

> 이 저장소의 모든 파일이 무슨 역할을 하는지 정리한 문서.
> 코드 단위 흐름은 [`FLOWS.md`](./FLOWS.md), 로드맵은 [`../PROGRESS.md`](../PROGRESS.md) 참조.
>
> 설계 철학이 곧 파일 구조다 — *선언 / 오케스트레이션 / 단계정의 / 실행 / 격리 / 기록* 의
> 6개 관심사가 각각 한 파일에만 책임을 진다.

---

## 1. 하네스 본체 — `harness/` (Python 패키지)

| 파일 | 역할 | 핵심 책임 |
|---|---|---|
| `state.py` | **상태 저장 계층 — 유일한 기록자** | `state/` 아래 모든 JSON/JSONL을 쓰는 단 하나의 모듈. 원자적 쓰기(`tmp→fsync→rename`), `flock` 동시성, ID 발급, 이벤트 로그, 인덱스 재생성 |
| `state_machine.py` | **결정적 오케스트레이터** | `advance()`로 한 항목을 한 단계 전진. 승인 게이트 · 재시도(`_handle_failure`) · 리뷰 되돌림(`_handle_route`) · 커밋(`_commit_phase`) · 동시 처리 루프(`run_loop`) · 승인(`approve`) |
| `phases.py` | **단계 정의 + 게이트** | 7단계를 `Phase(프롬프트빌더, 게이트, 도구스코프, actuator)`로 선언. **게이트 = 스크립트 판정**(LLM 자기보고 불신). `PIPELINE`/`PHASES` 레지스트리, 상태 전이 함수. INTEGRATE(트렁크 병합/PR)·DEPLOY는 에이전트 없는 actuator 단계 |
| `runner.py` | **비결정적 작업자 호출** | `claude` CLI를 헤드리스로 실행(`-p --output-format json`). "무엇을 만들었나"만 보고하고 판정은 안 함. SDK 교체 시 이 파일만 바꾸면 되도록 격리 |
| `worktree.py` | **동시 처리 격리** | 항목별 git worktree 생성/제거. 브랜치 `harness/WI-xxxx`를 트렁크에서 분기. `_wt_lock`으로 worktree add/remove 직렬화 |
| `config.py` | **설정 로더** | 글로벌(`config.yaml`) + 프로젝트(`harness.yaml`) 깊은 병합. 기본값·자율성 정책(`deploy.require_human`) 정의, repo 경로 정규화 |
| `__init__.py` | 패키지 마커 | (빈 파일) `harness` import 가능하게 함 |

---

## 2. 진입점 & 루트 설정/문서

| 파일 | 역할 |
|---|---|
| `hctl` | **CLI 진입점**(실행 가능). `add/run/status/log/approve/projects/worktrees/reindex` 서브커맨드. 로직 없이 위 모듈을 호출만 |
| `config.yaml` | **글로벌 설정**. 모델, `permission_mode`, `max_attempts`, `max_review_rounds`, `runner_timeout_sec`, `workers` |
| `README.md` | 프로젝트 설명 · 아키텍처 · 사용법 · 개발 히스토리 · 이어서 작업 가이드 |
| `PROGRESS.md` | 사람이 읽는 로드맵/진행 기록 (완료 항목 · 우선순위별 남은 작업) |
| `docs/FLOWS.md` | 명령어별 처리 흐름 (mermaid) + 파일 입출력 맵 |
| `docs/FILES.md` | (이 문서) 파일별 역할 |

---

## 3. 프롬프트 템플릿 — `prompts/` (단계 입력)

각 단계 에이전트에게 주는 지시문. `phases.py`의 `build_prompt`가 `.format(...)`으로 변수를 채운다.

| 파일 | 단계 | 역할 |
|---|---|---|
| `spec.md` | SPEC | 요구사항 → 수용 기준 명세 작성 |
| `design.md` | DESIGN | 기술 설계 문서 작성 |
| `implement.md` | IMPLEMENT | spec/design 따라 코드 구현 (+ 직전 리뷰 피드백 주입) |
| `test.md` | TEST | 수용 기준 검증 테스트 작성 |
| `review.md` | REVIEW | 독립 리뷰어에게 diff 검토 + JSON verdict 요청 |
| *(INTEGRATE)* | — | 프롬프트 없음 (스크립트 전용: 트렁크 병합 또는 PR 생성) |
| *(DEPLOY)* | — | 프롬프트 없음 (스크립트 전용 단계) |

---

## 4. 런타임 상태 — `state/` (오직 `state.py`만 기록)

| 파일/디렉토리 | 역할 | 성격 |
|---|---|---|
| `work_items/WI-NNNN.json` | 항목별 상태(현재 단계·시도·산출물·승인·오류) | **진실 원천**, 원자적 교체 |
| `events/WI-NNNN.jsonl` | 항목별 타임라인(created/phase_start/gate/…) | **진실 원천**, append-only |
| `queue.jsonl` | 요구사항 인입 로그 | append-only |
| `index.json` | 전체 조회용 요약 | 파생 캐시 (손상 시 `reindex`로 복원) |
| `.lock` | `flock` 직렬화용 빈 파일 | 동시성 |
| `worktrees/<proj>/<item>/` | 항목별 격리 작업 디렉토리 | git worktree (DONE 도달 시 `state_machine`이 자동 정리; 브랜치/커밋은 보존) |

---

## 5. 데모 프로젝트 — `projects/demo-service/` (작업 대상 레포)

하네스가 코드를 만들어 넣는 **대상 git 레포** (트렁크 `main`).

| 파일/디렉토리 | 역할 |
|---|---|
| `harness.yaml` | 프로젝트 설정 — `commands{build,test,lint,deploy}`, `service.health_check`, `gates`, `concurrency` |
| `README.md` | 데모 서비스 설명 |
| `app/`, `tests/` | 에이전트가 생성한 서비스 코드·테스트가 쌓이는 곳 |
| `.git/` | 레포. `refs/heads/harness/WI-*` 항목별 브랜치, `worktrees/` worktree 메타데이터 |

> 새 프로젝트를 추가하려면 `projects/<name>/harness.yaml` 하나만 만들면 된다
> (스캐폴딩 `hctl init`은 미구현 — PROGRESS G 참조).

---

## 6. 단계 산출물 (worktree 안, 에이전트가 생성)

| 경로 | 생성 단계 | 역할 |
|---|---|---|
| `<repo>/.harness/<item>/spec.md` | SPEC | 수용 기준 명세 (이후 모든 단계가 읽음) |
| `<repo>/.harness/<item>/design.md` | DESIGN | 기술 설계 (IMPLEMENT/REVIEW가 읽음) |
| `<repo>/app/*.py` 등 | IMPLEMENT | 실제 서비스 코드 |
| `<repo>/tests/*.py` 등 | TEST | 테스트 코드 |

---

## 데이터 흐름 한눈에

```
config.yaml / harness.yaml  (선언: 무엇을 빌드·테스트·배포하나)
        │
        ▼
hctl ─> state_machine ─> [runner ─> prompts/*.md ─> Claude] ─> phases.gate (판정)
        │                                                          │
        └──────────── 기록은 항상 state.py 경유 ────────────────────┘
                              │
        ┌─────────────────────┴──────────────────────┐
   state/work_items·events·index            worktree 안의 .harness/*.md · 서비스 코드
   (하네스의 상태 = 진실 원천)                 (작업 결과물 = 대상 레포 브랜치)
```

**불변식**: `state/`는 `state.py`만 쓴다 · 합격 판정은 `gate`만 한다 · 코드 생성은 `runner`(Claude)만 한다.
