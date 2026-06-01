# Harness — 지속 운영형 AI 개발 하네스

요구사항을 입력하면 **설계 → 개발 → 테스트 → 리뷰 → 배포**까지 전체 개발 사이클을
자동으로 수행하는 하네스다. 한 번 쓰고 끝나는 도구가 아니라, 계속 들어오는 요구사항을
처리하며 **지속적으로 운영**되는 것을 목표로 한다.

---

## 핵심 설계 원칙

> **LLM은 비결정적(non-deterministic) 작업자, 하네스는 결정적(deterministic) 오케스트레이터다.**

| 구분 | 담당 | 방식 |
|------|------|------|
| 무엇을 할지 판단·실행 (코드 작성, 설계 등) | **LLM (Claude)** | 프롬프트 + 도구 |
| 지금 어느 단계인지, 다음에 뭘 할지, 통과/실패 판정 | **스크립트** | JSON 상태 + 코드 상태머신 |

진행 상황·상태는 **문서나 프롬프트가 아니라 스크립트로** 확실하게 관리한다.
LLM은 절대 "지금 무슨 단계지?"를 스스로 판단하지 않는다. 스크립트가 상태를 들고 있고,
LLM은 *(현재 상태, 작업 컨텍스트, 단계 프롬프트)* 를 받아 *(산출물, 구조화된 결과)* 를
내놓는 **무상태 함수**처럼 호출된다. 그 결과의 합격 여부는 스크립트(게이트)가 판정한다.

---

## 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                     하네스 (결정적 영역)                         │
│                                                                │
│  요구사항 큐 ─> 상태머신 ─> 단계 실행기 ─> 게이트(검증) ─> 승인     │
│   (state.py)  (state_      (phases.py)   (phases.py)  (게이트)   │
│                machine.py)                                      │
│        │           │            │            │                 │
│        └───────────┴────────────┴────────────┘                 │
│                        │                                       │
│                 ┌──────▼───────┐                               │
│                 │  JSON 상태     │  state/work_items/*.json      │
│                 │  (유일한 기록자)│  state/events/*.jsonl         │
│                 └──────────────┘                               │
└────────────────────────┬───────────────────────────────────────┘
                        │ (무상태 호출, 단계별 도구 제한)
                 ┌──────▼───────┐
                 │ Agent Runner │  claude CLI 헤드리스 (runner.py)
                 │   (Claude)   │  ← 비결정적 작업자
                 └──────────────┘
                        │
                 ┌──────▼───────┐
                 │ git worktree │  작업 항목별 격리 작업 디렉토리 (worktree.py)
                 └──────────────┘  ← 동시 처리의 기반
```

### 구성 요소

| 파일 | 역할 |
|------|------|
| `harness/state.py` | **상태 저장 계층 — 상태 파일을 기록하는 유일한 모듈.** 엔티티별 JSON + 이벤트 JSONL + 원자적 쓰기. 상태 루트(`DATA_ROOT`)는 env로 분리(플러그인=사용자 홈). |
| `harness/state_machine.py` | 결정적 오케스트레이터. `advance()`로 한 항목을 한 단계 전진. 동시 스케줄러 `run_loop()`. DONE 시 worktree 자동 정리. |
| `harness/phases.py` | 7단계 정의 — (프롬프트 + 도구 스코프 + 결정적 게이트). INTEGRATE/DEPLOY는 스크립트 전용 actuator. |
| `harness/runner.py` | claude CLI 헤드리스 호출 (`-p --output-format json`). 단계별 도구 제한. |
| `harness/worktree.py` | 작업 항목별 git worktree 격리 (동시 처리). |
| `harness/config.py` | 설정 로더(레거시 `projects/<name>` + cwd/플러그인 모드) + `harness.yaml` 스캐폴딩(스택 감지). |
| `hctl` | CLI 진입점 (`add/run/status/log/approve/init/projects/reindex/worktrees`). |
| `prompts/*.md` | 단계별 프롬프트 템플릿. |
| `plugin/dev-harness/` | **Claude Code 플러그인**(얇은 래퍼) — `plugin.json` · `bin/hctl` 런처 · `commands/*.md` 슬래시 명령 · 엔진 동봉. |
| `docs/CODE-FLOW.md` | 전체 코드 흐름(함수/클래스 단위 + mermaid + 중단/재개). |

---

## 파이프라인 (7단계)

```
QUEUED → SPEC → DESIGN → IMPLEMENT → TEST → REVIEW → INTEGRATE ──자동── ✋NEEDS_HUMAN
                                                                         │ hctl approve
                                                                         ▼
                                                                      DEPLOY → DONE
       보조 상태: FAILED · NEEDS_HUMAN
```

각 단계는 **에이전트 호출 → 결정적 게이트 검증**으로 구성된다. 게이트는 LLM의 자기보고를
믿지 않고 *스크립트가* 판정한다.

| 단계 | 하는 일 | 도구 | 게이트(스크립트 검증) |
|------|---------|------|----------------------|
| **SPEC** | 요구사항 → 수용 기준 명세 | Read, Write | `spec.md` 존재 + 수용 기준 ≥3 |
| **DESIGN** | 기술 설계 문서 | Read, Write | `design.md` 필수 섹션(접근/파일/인터페이스/경로) |
| **IMPLEMENT** | 코드 구현 | Read, Write, Edit, Bash | 변경 발생 + 빌드/린트 통과 |
| **TEST** | 테스트 작성·실행 | Read, Write, Edit, Bash | 테스트 명령 통과 |
| **REVIEW** | **독립 리뷰어**(읽기 전용) 검토 | Read, Bash | 구조화된 PASS 판정 + 테스트 재실행 그린 |
| **INTEGRATE** | **스크립트 전용** 트렁크 반영(병합/PR) | — | `main`에 직접 병합 또는 PR 생성 + 회귀 테스트 통과 |
| **DEPLOY** | **스크립트 전용**(에이전트 없음) 배포 | — | 사람 승인 후 배포 명령 + 헬스체크 |

### 특징적 설계 결정

- **독립 리뷰어 분리**: REVIEW는 구현한 에이전트가 아닌 별도 리뷰어를 *읽기 전용*(Edit/Write 없음)으로
  호출한다. 코드를 못 고치므로 진짜 제3자 검토가 된다. 변경 요청 시 `REVIEW → IMPLEMENT`로
  되돌려 수정 사이클을 돌린다 (`max_review_rounds`로 제한).
- **배포만 사람 승인**: 자율성 정책. SPEC~INTEGRATE는 무인 진행, DEPLOY 진입 시에만 멈춰 `hctl approve`를
  기다린다. 승인 *전*에는 배포 명령이 절대 실행되지 않는다.
- **트렁크 반영(INTEGRATE)**: 게이트를 통과한 항목 브랜치를 트렁크에 반영해 사이클을 닫는다.
  `integrate.mode: direct`는 `main`에 직접 병합(--no-ff)하되 **병합 결과 기준 회귀 테스트가 통과해야만**
  머지를 확정하고, 실패/충돌 시 `merge --abort`로 트렁크를 보호한다. `mode: pr`은 `gh`로 PR을 생성하고
  사람이 머지/배포하도록 멈춘다. (다른 단계는 worktree 안에서, INTEGRATE만 메인 레포에서 동작)
- **DEPLOY는 스크립트 전용**: 가장 위험한 단계에서 LLM 즉흥 판단을 배제하고, 사람이 승인한 산출물을
  결정적으로 배포 명령 실행 + 헬스체크한다.

---

## 상태 관리 (JSON, DB 아님)

DB 대신 JSON을 쓰되 신뢰성을 위해 다음 규율을 따른다 (검토 결과 채택):

```
state/
├── queue.jsonl              # 요구사항 인입 로그 (append-only)
├── work_items/WI-0001.json  # 작업 항목 상태 (원자적 교체)  ← 진실 원천
├── events/WI-0001.jsonl     # 항목별 타임라인 (append-only) ← 진실 원천
└── index.json               # 조회용 요약 (파생·재생성 가능)
```

- **원자적 쓰기**: tmp 작성 → fsync → `os.rename` (POSIX 원자적). 반쪽 파일 불가.
- **장애 격리**: 항목 1개 파일이 깨져도 나머지는 무사. `index.json`은 파생 캐시라 `hctl reindex`로 복원.
- **동시성**: 항목별 파일 분리 + 공유 자원(ID 발급/큐/인덱스)은 `flock`으로 직렬화.
- **유일한 기록자**: 오직 `harness/state.py`만 이 파일들을 쓴다. 에이전트는 직접 쓰지 않는다.
- **상태 루트 위치(`DATA_ROOT`)는 분리됨**: 엔진 코드(`ENGINE_ROOT`)와 별개로, 상태는
  ① env(`CLAUDE_PLUGIN_DATA`/`HARNESS_DATA_HOME`, 플러그인=사용자 홈) → ② 레거시 in-repo `state/`
  → ③ `~/.harness` 순으로 결정된다. 즉 플러그인으로 쓰면 **상태는 사용자 홈, 프로젝트 폴더는 안 건드린다.**

> 중단·재개 동작(어디서 끊겨도 안전한 이유, 재시작 방법)은 [`docs/CODE-FLOW.md` §4](./docs/CODE-FLOW.md) 참조.

---

## 동시 처리 (git worktree)

각 작업 항목은 자신의 worktree(별도 작업 디렉토리)에서 처리되어, 여러 항목을 병렬로
진행해도 작업 트리가 충돌하지 않는다.

```
projects/demo-service                        # 메인 레포 (트렁크 main 유지)
state/worktrees/demo-service/WI-0004         # 항목별 격리 작업 디렉토리 (branch harness/WI-0004)
state/worktrees/demo-service/WI-0005         # ...
```

`run_loop()`가 ThreadPoolExecutor로 워커 풀을 돌리며, 프로젝트별 `concurrency` 한도를 준수한다.

---

## 사용법

```bash
# 요구사항 등록
./hctl add <project> "<요구사항>" [--priority N]

# 한 단계 전진 (특정 항목 또는 큐에서 자동 선택)
./hctl run [--item WI-0001]

# 동시 처리 루프 (워커 N개로 큐가 빌 때까지)
./hctl run --loop --workers 2

# 현황 / 상세 / 이벤트 타임라인
./hctl status [--item WI-0001]
./hctl log WI-0001

# 배포 승인 (NEEDS_HUMAN 해제)
./hctl approve WI-0001

# 프로젝트에 harness.yaml 생성 (스택 자동 감지·검증)
./hctl init [--project-dir <dir>] [--force]

# 기타
./hctl projects        # 프로젝트 목록 (레거시 등록)
./hctl worktrees       # worktree 목록
./hctl reindex         # index.json 복구
```

### 두 가지 운영 모드

| 모드 | 설정 위치 | 등록 명령 | 용도 |
|------|-----------|-----------|------|
| **cwd/플러그인** (권장) | 프로젝트 자체의 `harness.yaml` | `hctl add --project-dir <dir> "<요구사항>"` (또는 `$CLAUDE_PROJECT_DIR`) | 임의 프로젝트에서 바로 실행. 상태는 사용자 홈 |
| **레거시(중앙)** | `projects/<name>/harness.yaml` | `hctl add <name> "<요구사항>"` | 하네스 레포 안에 프로젝트 등록 |

cwd 모드는 `harness.yaml`이 없으면 **첫 `add` 시 자동 생성(스캐폴드)** 한다. project 식별자는 경로 해시로
자동 부여되어 한 상태 저장소에 여러 프로젝트가 공존한다.

### 프로젝트 설정 (`harness.yaml` — 프로젝트 레포에 커밋)

`hctl init`이 스택(Node/Python/Go/Rust/Java/.NET/…)을 감지해 명령을 채우고, `service`·`gates`·`integrate`
블록과 함께 생성한다. test 명령 드라이런·git 전제조건 확인·깨진 yaml 친절 처리·`--force` 백업 포함.

```yaml
project: demo-service
service:
  health_check: 'curl -f http://localhost:8000/healthz'   # 쉘 명령, rc=0이면 통과
commands:
  build: "..."
  lint:  "..."
  test:  'python3 -m unittest discover -p "test_*.py"'
  deploy: "./deploy.sh prod"
gates:
  test:   { require_pass: true }
  deploy: { require_human: true }    # 배포만 사람 승인
concurrency: 2
```

### 글로벌 설정 (`config.yaml`)

```yaml
model: ""                       # 빈 값이면 claude CLI 기본 모델
permission_mode: bypassPermissions
max_attempts: 2                 # 게이트 실패 시 단계 재시도
max_review_rounds: 2            # 리뷰 변경요청 수정 사이클 한도
workers: 2                      # 동시 처리 워커 풀 크기
```

### Claude Code 플러그인으로 쓰기 (`plugin/dev-harness/`)

하네스는 어차피 Claude 환경을 전제하므로, 플러그인으로 감싸 **임의 프로젝트 안에서** 슬래시 명령으로 운영한다.
엔진은 플러그인에 동봉되고, **상태는 사용자 홈(`${CLAUDE_PLUGIN_DATA}`)**, 설정은 프로젝트 `harness.yaml`이다.

```bash
claude --plugin-dir ./plugin/dev-harness     # 로컬 테스트
# 세션 안에서:
/dev-harness:init                  # harness.yaml 생성(스택 감지) + 보정
/dev-harness:add 장바구니 합계 기능을 구현하라
/dev-harness:run --loop            # 자동 진행 (DEPLOY 승인에서 멈춤)
/dev-harness:status
/dev-harness:approve WI-0001
```

- **결정적 코어는 그대로** — 상태머신·게이트·`state.py`는 Python이 들고, 플러그인은 배포/제어 계층만.
- ⚠️ 각 단계가 `claude`를 헤드리스로 호출(중첩 실행·비용). 긴 `run --loop`은 백그라운드 권장.
- 설계·로드맵은 `PROGRESS.md` §I, 메모리 `harness-plugin-architecture.md` 참조.

---

## 개발 히스토리

설계 → 결정 → 단계적 구현 순으로, 각 단계를 실제 작업 항목으로 검증하며 진행했다.

### 0. 설계 및 핵심 결정
- 전체 SDLC 하네스 설계 보고. 핵심 원칙 확정: *결정적 오케스트레이터 + 비결정적 작업자*.
- 주요 결정:
  - **상태 저장**: DB 대신 **엔티티별 JSON + JSONL + 원자적 쓰기** (검토 후 채택 — 투명성·장애격리 우수)
  - **자율성**: **배포만 사람 승인**
  - **런타임**: **Python** + **claude CLI 헤드리스**(Agent SDK 미설치라 CLI 채택, 외부 의존 최소화)
  - **대상**: **서비스 개발**(웹/백엔드)

### 1. MVP — 3단계 파이프라인
- SPEC → IMPLEMENT → TEST + 상태계층 + 상태머신 + Runner + `hctl`.
- 검증 **WI-0001** (장바구니 총액 계산): 요구사항 1건 → 코드+테스트 자동 생성, 8개 테스트 통과.

### 2. DESIGN + REVIEW 추가
- DESIGN 단계, 그리고 **독립 리뷰어 에이전트**(읽기 전용) + 변경요청 시 IMPLEMENT 되돌림 사이클.
- 검증 **WI-0002** (이메일 형식 검증): 5단계 완주, 19개 테스트 통과, 리뷰어 첫 회 PASS.

### 3. DEPLOY + 승인 게이트
- 스크립트 전용 DEPLOY 단계 + 단계 실행 *전* 사람 승인 게이트.
- 검증 **WI-0003** (단어 수 세기): REVIEW까지 자동 → DEPLOY 승인 대기 → `hctl approve` → 배포+헬스체크 → DONE.
  배포 직전 정지 시 실제로 미배포 상태임을 확인.

### 4. worktree 동시 처리
- 작업 항목별 git worktree 격리 + ThreadPoolExecutor 동시 스케줄러 + 프로젝트별 동시 한도.
- 검증 **WI-0004**(섭씨→화씨), **WI-0005**(짝수 합)를 **workers=2로 병렬 처리**.
  - 타임라인 교차로 병렬 실행 입증, 각자 독립 worktree(temperature.py / even_sum.py).
  - **보너스**: 두 독립 리뷰어가 `__pycache__/*.pyc` 커밋 문제를 잡아내 **수정 사이클 발동** →
    구현자가 `.pyc` 추적 해제 + `.gitignore` 추가 → 재리뷰 PASS.

### 5. INTEGRATE — 결과 트렁크 반영 (파이프라인 빈틈 메움)
- REVIEW와 DEPLOY 사이에 **INTEGRATE** 단계 추가. 게이트 통과 브랜치를 `main`에 반영해 사이클을 닫는다.
  `integrate.mode: direct`(자동 병합 + 병합 결과 회귀 테스트, 실패/충돌 시 `merge --abort`) | `pr`(`gh` PR).
- **백필 검증**: 그동안 브랜치에만 있던 WI-0001~0005를 실제 `main`에 병합. WI-0004는 진짜 충돌(`app/__init__.py`
  export)을 수동 해소. 과정에서 **더러운 트렁크 버그**(회귀 테스트가 만든 `.pyc`로 다음 병합 차단)를 발견해
  `_reset_trunk`(reset --hard + clean)로 수정.

### 6. worktree 자동 정리
- DONE 도달 시 `advance()`가 `remove_worktree`를 best-effort 호출(브랜치/커밋 보존). 정의만 있고 미연결이던 기능 연결.

### 7. Claude Code 플러그인 전환 (얇은 래퍼) + `hctl init`
- **경로 분리**: `ENGINE_ROOT`(코드) vs `DATA_ROOT`(상태, env 기반). 상태를 사용자 홈/`${CLAUDE_PLUGIN_DATA}`로.
- **cwd/플러그인 모드**: 프로젝트 디렉토리의 `harness.yaml`을 읽고(`load_project_at`), 경로 해시로 식별. 레거시 유지.
- **`hctl init` 스캐폴딩**: 스택 감지로 명령 추론 + `service` 블록 + 드라이런 + git 확인 + 깨진 yaml 친절 처리.
- **플러그인 스캐폴드**: `plugin/dev-harness/`(`plugin.json`·`bin/hctl`·`commands/*.md`). `claude plugin validate` ✔.

> 누적: 작업 항목 5건 전부 DONE **+ 5건 모두 `main` 병합**. 하네스 본체 약 1,700줄 + 플러그인 스캐폴드.

---

## 이어서 작업하려면 (개발 가이드)

> 컨텍스트가 비워진 새 세션이 이 저장소에서 작업을 이어갈 때 필요한 실무 정보.

### 0) 먼저 정상 동작 확인 (sanity check)
```bash
cd /Users/lumieres/Desktop/projects/harness
python3 -c "import harness.state, harness.state_machine, harness.phases, \
  harness.runner, harness.worktree, harness.config; print('imports OK')"
./hctl status            # 작업 항목 현황 (WI-0001~0005 DONE 이어야 함)
claude --version         # Runner 백엔드 (PATH에 있어야 함)
```

### 1) 새 단계(phase) 추가 패턴
단계는 4곳만 손대면 추가된다 (`harness/phases.py` 중심):
1. `PIPELINE` 리스트에 단계명 삽입 (순서 = 실행 순서)
2. `PHASES` 딕셔너리에 `Phase(...)` 항목 추가 — `allowed_tools`, `system`, `build_prompt`(프롬프트 생성 함수), `gate`(결정적 검증 함수). 에이전트 없는 스크립트 전용 단계는 `build_prompt=None` + `actuator` 사용 (DEPLOY 참고).
3. `prompts/<phase>.md` 프롬프트 템플릿 작성 (`build_prompt`가 `.format(...)`로 채움)
4. 게이트 함수는 `GateResult(passed, detail, checks, route_to=?)` 반환. 비선형 전이가 필요하면 `route_to` 사용 (REVIEW→IMPLEMENT 되돌림이 예시).

`next_state()`/`phase_for_state()`는 `PIPELINE` 기반으로 자동 동작하므로 별도 수정 불필요.
사람 승인이 필요한 단계는 프로젝트 `harness.yaml`의 `gates.<phase>.require_human: true`
(체크는 `requires_approval()` + `advance()`의 승인 게이트가 담당).

### 2) 하네스 변경을 검증하는 법
하네스 자체 단위테스트는 아직 없다(= 남은 작업 D). **변경 검증 = 데모 작업 항목 end-to-end 실행**:
```bash
./hctl add demo-service "<테스트용 요구사항>" --priority 10
./hctl run --loop --workers 2   # 길게 걸리므로 백그라운드 실행 권장
./hctl status --item WI-xxxx     # 단계별 게이트 결과/커밋 확인
./hctl log WI-xxxx               # 이벤트 타임라인
```
⚠️ 이 실행은 **실제 `claude` 호출 = 실제 비용**이 든다 (단계당 ~$0.1~0.3). 상태/게이트 로직만
바꿨다면 `state/work_items/*.json`을 직접 조작해 특정 상태를 재현하는 편이 싸다.

### 3) 환경 지뢰 (건드리기 전 주의 — 의도된 선택들)
- **이 디렉토리(`harness/`)는 git 레포가 아니다.** 반면 `projects/demo-service`는 git 레포(트렁크 `main`).
- **pytest 미설치** → 데모 테스트는 stdlib `unittest`. 데모에 pytest를 가정하지 말 것.
- **claude-agent-sdk 미설치** → Runner는 *의도적으로* `claude` CLI 헤드리스 사용. SDK로 갈아타지 말 것(원하면 `runner.py`만 교체 가능하게 격리돼 있음).
- **`permission_mode: bypassPermissions`는 의도적** (격리 worktree 내 자율 실행). 단계별 `allowed_tools`로 최소권한 유지.
- **상태 파일은 오직 `harness/state.py`만 기록.** 다른 모듈/에이전트가 직접 쓰지 말 것.
- worktree는 **DONE 시 자동 정리**된다(`advance()`가 `remove_worktree` 호출). 중단된 항목은 worktree가 남을 수 있다.
- **상태 루트는 env로 이동 가능**: `CLAUDE_PLUGIN_DATA`/`HARNESS_DATA_HOME`이 있으면 그곳에, 없으면 레거시 in-repo `state/`.
  레포 안에서 직접 돌리면 기존처럼 `state/`를 쓰지만, 플러그인으로 쓰면 사용자 홈에 생긴다.

### 4) 핵심 컨벤션
- 작업 항목 ID: `WI-0001`(4자리 0패딩, `state.py`가 발급) · 브랜치: `harness/WI-xxxx`
- 단계 산출물: `<repo>/.harness/<item_id>/{spec,design}.md`
- 커밋 메시지: `harness(WI-xxxx): <PHASE> done` (단계 경계에서 `state_machine`이 자동 커밋)
- 종료 상태: `DONE` / `FAILED` / `NEEDS_HUMAN`

> 참고: 핵심 결정·구조는 영속 메모리(`harness-project.md`)에도 저장돼 새 세션에 자동 로드된다.

---

## 남은 작업

전체 로드맵과 우선순위는 [`PROGRESS.md`](./PROGRESS.md) 참조.
핵심 남은 것: **플러그인 풀구성(전용 trunk 워크트리·서브에이전트·모니터 알림) · 데몬화/자동 인입 · 하네스 자체 테스트**.
(결과 트렁크 반영·worktree 자동정리·플러그인 얇은 래퍼·`hctl init`은 완료)

---

## 요구사항

- Python 3.12+
- `claude` CLI (Claude Code) — PATH에 있어야 함
- PyYAML
- git
