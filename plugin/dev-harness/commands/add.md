---
description: 현재 프로젝트에 요구사항을 하네스 작업 항목으로 등록한다
---

다음 요구사항을 현재 프로젝트의 하네스 큐에 등록하라. 아래 Bash 명령을 그대로 실행하고, 출력(등록된 WI 번호)을 사용자에게 보고하라.

```bash
HARNESS_DATA_HOME="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/bin/hctl" add --project-dir "${CLAUDE_PROJECT_DIR}" "$ARGUMENTS"
```

전제: 이 프로젝트 루트에 `harness.yaml`(build/test/deploy 명령)이 있어야 한다. 없으면 명령이 안내 메시지를 출력한다.
