# 명령어별 처리 흐름 (Mermaid)

> `hctl`의 각 명령이 코드 단위(함수/모듈)로 어떻게 처리되는지 도식화한 문서.
> VS Code의 Mermaid 프리뷰(또는 GitHub)에서 렌더링해 볼 것.
>
> 핵심 원칙: **상태 변경은 `state.py`만**, **합격 판정은 `gate` 함수만**, **코드 생성은 `runner`(Claude)만**.
>
> 각 흐름 끝의 **📁 생성/수정 파일** 표기는 그 명령이 디스크에 무엇을 쓰는지 나타낸다.

---

## 0-A. 파일 맵 — 어떤 함수가 어떤 파일을 건드리나

| 파일/디렉토리 | 쓰는 함수 | 읽는 함수 | 성격 |
|---|---|---|---|
| `state/work_items/WI-NNNN.json` | `create_work_item`, `save_item` (→ `_atomic_write`) | `load_item`, `list_items` | **진실 원천** (원자적 교체) |
| `state/events/WI-NNNN.jsonl` | `append_event` (O_APPEND) | `read_events` | **진실 원천** (감사 로그) |
| `state/queue.jsonl` | `create_work_item` (append) | — | 인입 로그 (append-only) |
| `state/index.json` | `_reindex_locked`, `reindex` | `load_index` | 파생 캐시 (재생성 가능) |
| `state/.lock` | `_lock` (flock) | `_lock` | 동시성 직렬화용 |
| `state/worktrees/<proj>/<item>/` | `ensure_worktree` (git worktree add) | 단계 실행 cwd | 항목별 격리 작업 트리 |
| 브랜치 `harness/WI-NNNN` | `ensure_worktree`, `_commit_phase` (git commit) | `_review_prompt` (diff) | 항목별 커밋 이력 |
| `<repo>/.harness/<item>/spec.md` | SPEC 에이전트 (Write) | DESIGN/IMPLEMENT/TEST/REVIEW 프롬프트 | 단계 산출물 |
| `<repo>/.harness/<item>/design.md` | DESIGN 에이전트 (Write) | IMPLEMENT/REVIEW 프롬프트 | 단계 산출물 |
| `<repo>/` 서비스 코드·테스트 | IMPLEMENT/TEST 에이전트 (Write/Edit) | TEST/REVIEW 게이트 (실행) | 실제 결과물 |

> 규율: `state/` 의 파일은 **오직 `state.py`** 가 쓴다. 에이전트(Claude)는 worktree 안의
> `.harness/*.md` 와 서비스 코드만 쓰고, 상태 파일은 절대 직접 쓰지 않는다.

---

## 0. 전체 개요 (계층)

```mermaid
flowchart TD
    subgraph CLI["hctl (사람 진입점)"]
        add[add]
        run[run]
        loop[run --loop]
        status[status]
        log[log]
        approve[approve]
        misc[projects / worktrees / reindex]
    end

    subgraph SM["state_machine.py (결정적 오케스트레이터)"]
        advance["advance()"]
        runloop["run_loop()"]
        pick["pick_next() / _select()"]
        appr["approve()"]
    end

    subgraph WORK["비결정적 / 격리"]
        runner["runner.run_agent() → claude CLI"]
        wt["worktree.ensure_worktree()"]
    end

    subgraph DET["결정적 판정"]
        gate["phases.PHASES[x].gate()"]
        act["actuator (DEPLOY)"]
    end

    subgraph ST["state.py (유일한 기록자)"]
        items[(work_items/*.json)]
        events[(events/*.jsonl)]
        index[(index.json)]
    end

    add --> SM
    run --> advance
    loop --> runloop --> advance
    advance --> wt --> runner --> gate --> ST
    advance --> act
    status --> index
    log --> events
    approve --> appr --> ST
```

---

## 1. `hctl add <project> "<req>"` — 요구사항 등록

```mermaid
flowchart TD
    A[hctl add] --> B{"project가<br/>list_projects()에 있나?"}
    B -- 없음 --> X[에러 출력 후 종료]
    B -- 있음 --> C["state.create_work_item()"]
    C --> D["_lock() 획득 (공유자원 직렬화)"]
    D --> E["_next_id() → WI-NNNN"]
    E --> F["항목 JSON 생성<br/>state=QUEUED<br/>branch=harness/WI-NNNN"]
    F --> G["_atomic_write (tmp→fsync→rename)"]
    G --> H["queue.jsonl append (인입 로그)"]
    H --> I["append_event 'created'"]
    I --> J["_reindex_locked()"]
    J --> K[등록 완료 출력]

    F -. 쓰기 .-> f1[("work_items/WI-NNNN.json<br/>신규 생성")]
    H -. append .-> f2[("queue.jsonl")]
    I -. append .-> f3[("events/WI-NNNN.jsonl")]
    J -. 갱신 .-> f4[("index.json")]
```

**📁 생성/수정 파일**
- 🆕 `state/work_items/WI-NNNN.json` (state=QUEUED)
- ➕ `state/queue.jsonl` (인입 1줄 추가)
- ➕ `state/events/WI-NNNN.jsonl` (`created` 이벤트)
- ✏️ `state/index.json` (요약 갱신)

---

## 2. `hctl run [--item]` — 한 단계 전진 (핵심)

```mermaid
flowchart TD
    A["hctl run"] --> B{"--item 지정?"}
    B -- 아니오 --> P["pick_next()<br/>우선순위↑·오래된순 1건"]
    B -- 예 --> C
    P --> C["state_machine.advance(item)"]

    C --> D{"state ∈ TERMINAL?<br/>(DONE/FAILED/NEEDS_HUMAN)"}
    D -- 예 --> SKIP[skip 반환]
    D -- 아니오 --> E["phase_for_state(state)"]

    E --> F{"requires_approval &&<br/>미승인?"}
    F -- 예 --> NH["state=NEEDS_HUMAN<br/>pending_phase 기록<br/>'awaiting_approval'<br/>⛔ 멈춤"]
    F -- 아니오 --> G["state=phase claim<br/>attempts[phase]++"]

    G --> H["worktree.ensure_worktree()<br/>+ base_commit 1회 기록"]
    H --> I{"build_prompt is None?<br/>(스크립트 전용 단계)"}

    I -- "예 (DEPLOY)" --> J["actuator(ctx) 실행"]
    I -- 아니오 --> K["runner.run_agent()<br/>claude CLI 호출<br/>allowed_tools 제한"]

    J --> L
    K --> M{"run.ok?"}
    M -- 아니오 --> FAIL["_handle_failure"]
    M -- 예 --> L["phase.gate(ctx, run)<br/>스크립트 판정"]

    L --> N{"gate.passed?"}
    N -- 예 --> OK["_commit_phase()<br/>artifacts 기록<br/>state=next_state()<br/>'phase_done'"]
    N -- "아니오 + route_to" --> RT["_handle_route<br/>(리뷰 수정 사이클)"]
    N -- "아니오 + route 없음" --> FAIL

    OK --> Z[advanced 반환]

    G -. save_item .-> w1[("work_items/WI-NNNN.json<br/>매 전이마다 교체")]
    G -. append .-> w2[("events/WI-NNNN.jsonl<br/>phase_start/agent_done/gate/phase_done")]
    H -. git worktree add .-> w3[("state/worktrees/&lt;proj&gt;/WI-NNNN/")]
    K -. "Write/Edit (에이전트)" .-> w4[(".harness/WI-NNNN/spec.md·design.md<br/>+ 서비스 코드/테스트")]
    OK -. git commit .-> w5[("브랜치 harness/WI-NNNN")]
```

**📁 단계별 생성/수정 파일** (어떤 단계를 도는지에 따라 다름)

| 단계 | 에이전트가 쓰는 파일 (worktree 내) | 상태머신이 쓰는 파일 (`state/`) |
|---|---|---|
| SPEC | `.harness/WI-NNNN/spec.md` | work_item.json, events.jsonl |
| DESIGN | `.harness/WI-NNNN/design.md` | 〃 |
| IMPLEMENT | 서비스 코드(`app/*.py` 등) | 〃 (+ build/lint는 읽기만) |
| TEST | 테스트 파일(`tests/*.py`) | 〃 |
| REVIEW | (없음 — 읽기 전용) | 〃 (테스트 재실행은 읽기) |
| INTEGRATE | (없음 — actuator가 메인 레포에서 병합/PR) | 〃 (+ 메인 레포 `main`에 머지 커밋) |
| DEPLOY | (없음 — actuator가 deploy 명령 실행) | 〃 |

- 매 단계: ✏️ `work_items/WI-NNNN.json`(claim·전이), ➕ `events/WI-NNNN.jsonl`(여러 이벤트), ✏️ `index.json`
- 게이트 통과 시: 🌿 `harness/WI-NNNN` 브랜치에 커밋 (`_commit_phase`)
- 첫 실행 시: 🆕 `state/worktrees/<proj>/WI-NNNN/` worktree 생성

### 2-1. 실패/되돌림 분기 상세

```mermaid
flowchart TD
    subgraph FAIL["_handle_failure"]
        F1{"attempt >= max_attempts?"}
        F1 -- 예 --> F2["state=NEEDS_HUMAN<br/>'needs_human'"]
        F1 -- 아니오 --> F3["state=phase 유지<br/>'retry_pending'<br/>(다음 run에서 재시도)"]
    end

    subgraph ROUTE["_handle_route (REVIEW 변경요청)"]
        R1["review_rounds++"]
        R1 --> R2{"round > max_review_rounds?"}
        R2 -- 예 --> R3["state=NEEDS_HUMAN"]
        R2 -- 아니오 --> R4["IMPLEMENT/TEST/REVIEW<br/>attempts=0 리셋<br/>state=route_to(IMPLEMENT)<br/>last_review에 피드백 저장"]
        R4 --> R5["다음 IMPLEMENT가<br/>리뷰 피드백 반영해 재구현"]
    end
```

**📁 생성/수정 파일** (둘 다 `state.py` 경유)
- ✏️ `state/work_items/WI-NNNN.json` (state=NEEDS_HUMAN / 재시도 유지 / route_to 변경, `last_review` 저장)
- ➕ `state/events/WI-NNNN.jsonl` (`needs_human` / `retry_pending` / `review_changes`)
- ✏️ `state/index.json`

---

## 3. `hctl run --loop --workers N` — 동시 처리

```mermaid
flowchart TD
    A["hctl run --loop"] --> B["run_loop(workers, max_steps)"]
    B --> C["ThreadPoolExecutor 생성"]
    C --> D{"steps < max_steps?"}
    D -- 아니오 --> END[루프 종료 요약]
    D -- 예 --> E{"가용 워커 있나?<br/>len(in_flight) < workers"}

    E -- 예 --> F["_select(busy, active_by_project)<br/>busy 아니고<br/>concurrency 한도 내 항목"]
    F --> G{"선택된 항목?"}
    G -- 있음 --> H["ex.submit(advance, item)<br/>in_flight에 등록"]
    H --> E
    G -- 없음 --> I

    E -- 아니오 --> I{"in_flight 비었나?"}
    I -- 예 --> END
    I -- 아니오 --> J["wait(FIRST_COMPLETED)"]
    J --> K["완료된 future 결과 수집<br/>steps++<br/>on_result 콜백 출력"]
    K --> D
```

> 각 워커는 결국 `advance()` 1스텝을 실행 → 한 항목이 SPEC→…→DEPLOY까지 가려면 여러 번
> picked & advanced 된다. 항목끼리는 worktree로 격리되어 병렬 안전.

**📁 생성/수정 파일**
- `run_loop` 자체는 파일을 직접 쓰지 않음 — 각 `advance()`가 §2와 동일하게 씀
- 항목마다 **서로 다른** `work_items/WI-xxxx.json` · `events/WI-xxxx.jsonl` · worktree 를 쓰므로 충돌 없음
- 공유 파일(`index.json`, `queue.jsonl`)은 `state._lock()`(flock)으로 직렬화

---

## 4. `hctl approve <id>` — NEEDS_HUMAN 해제

```mermaid
flowchart TD
    A["hctl approve"] --> B["state_machine.approve()"]
    B --> C{"state == NEEDS_HUMAN?"}
    C -- 아니오 --> NOOP[noop 반환]
    C -- 예 --> D{"pending_phase 있나?"}

    D -- "예 (승인 대기)" --> E["approvals[phase] 부여<br/>state=pending_phase<br/>'approved' (gate)"]
    E --> E2["다음 run에서<br/>해당 단계(DEPLOY) 실행 허가"]

    D -- "아니오 (실패성 멈춤)" --> F["마지막 시도 단계 탐색<br/>attempts[phase]=0 리셋<br/>state=phase<br/>'approved' (resume)"]
    F --> F2["다음 run에서 재개"]

    E -. save_item .-> a1[("work_items/WI-NNNN.json<br/>approvals 부여·state 복귀")]
    F -. save_item .-> a1
    E -. append .-> a2[("events/WI-NNNN.jsonl<br/>'approved'")]
    F -. append .-> a2
```

**📁 생성/수정 파일**
- ✏️ `state/work_items/WI-NNNN.json` (`approvals` 추가 또는 `attempts` 리셋, state 변경)
- ➕ `state/events/WI-NNNN.jsonl` (`approved`)
- ✏️ `state/index.json`
- ⚠️ approve는 **상태만 해제**할 뿐 배포를 실행하지 않는다 — 실제 DEPLOY는 다음 `run`에서 일어남

---

## 5. `hctl status` / `hctl log` — 조회 (읽기 전용)

```mermaid
flowchart LR
    subgraph status["hctl status"]
        S1{"--item?"}
        S1 -- 예 --> S2["load_item()<br/>상세: 시도·승인·artifacts·오류"]
        S1 -- 아니오 --> S3["load_index()<br/>전체 요약 테이블<br/>(손상 시 자동 reindex)"]
    end

    subgraph log["hctl log id"]
        L1["read_events()"] --> L2["events/WI.jsonl<br/>타임라인 출력"]
    end
```

**📁 생성/수정 파일**
- 없음 (읽기 전용). 단, `load_index()`는 `index.json`이 손상/부재 시 `reindex()`로 **자동 복원**하며 이때만 `index.json`을 씀.

---

## 6. 보조: `projects` / `worktrees` / `reindex`

```mermaid
flowchart LR
    P["projects"] --> P1["config.list_projects()<br/>+ load_project (repo·test 명령)"]
    W["worktrees"] --> W1["worktree.list_worktrees()<br/>git worktree list"]
    R["reindex"] --> R1["state.reindex()<br/>항목 파일에서 index.json 복원"]
    R1 -. 재생성 .-> rf[("index.json")]
```

**📁 생성/수정 파일**
- `projects` / `worktrees`: 없음 (읽기 전용)
- `reindex`: ✏️ `state/index.json` (work_item 파일들로부터 재생성)

---

## 부록: 작업 항목 상태 전이 (전체)

```mermaid
stateDiagram-v2
    [*] --> QUEUED: hctl add
    QUEUED --> SPEC
    SPEC --> DESIGN: gate PASS
    DESIGN --> IMPLEMENT: gate PASS
    IMPLEMENT --> TEST: gate PASS
    TEST --> REVIEW: gate PASS
    REVIEW --> IMPLEMENT: 변경요청 (route_to)
    REVIEW --> INTEGRATE: gate PASS
    INTEGRATE --> DEPLOY: 병합 PASS (mode=direct)
    INTEGRATE --> NEEDS_HUMAN: PR 생성됨 (mode=pr, 사람 머지/배포)
    DEPLOY --> DONE: 배포+헬스체크 PASS

    SPEC --> NEEDS_HUMAN: 재시도 한도 초과
    DESIGN --> NEEDS_HUMAN
    IMPLEMENT --> NEEDS_HUMAN
    TEST --> NEEDS_HUMAN
    REVIEW --> NEEDS_HUMAN: 리뷰 라운드 초과
    INTEGRATE --> NEEDS_HUMAN: 병합 충돌/회귀 실패
    DEPLOY --> NEEDS_HUMAN: 실행 전 승인 대기

    NEEDS_HUMAN --> DEPLOY: hctl approve (승인)
    NEEDS_HUMAN --> IMPLEMENT: hctl approve (재개)

    DONE --> [*]
```
