---
description: 현재 프로젝트에 harness.yaml을 생성하고 스택에 맞게 보정한다
---

현재 프로젝트의 하네스 설정(`harness.yaml`)을 준비하라. **두 단계**로 진행한다.

## 1단계 — 결정적 스캐폴드 생성
아래 명령으로 기본 `harness.yaml`을 만든다 (스택 자동 추론 + test 드라이런 + git 전제조건 확인). 출력을 사용자에게 보고하라.

```bash
HARNESS_DATA_HOME="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/bin/hctl" init --project-dir "${CLAUDE_PROJECT_DIR}" $ARGUMENTS
```

## 2단계 — 프로젝트에 맞게 보정 (LLM)
생성된 `${CLAUDE_PROJECT_DIR}/harness.yaml`을 읽고, 프로젝트 파일을 조사해 **비어 있거나 부정확한 값을 채워라**:

- `package.json`·`pyproject.toml`·`Makefile`·`Dockerfile`·CI 설정(`.github/workflows` 등)을 확인한다.
- `commands.build/test/lint/deploy`, `service.run/health_check/migrate`를 이 프로젝트의 *실제* 명령으로 채운다.
- 기존 구조·주석은 보존한다. 확신이 없는 값은 비워둔 채, 사용자가 무엇을 확인/입력해야 하는지 알려라.
- 1단계의 test 드라이런이 실패(rc≠0)했다면 올바른 명령으로 교정한다.

마지막에 최종 `harness.yaml`의 `commands`/`service`를 요약해 사용자에게 보고하라.
