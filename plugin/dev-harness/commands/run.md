---
description: 하네스를 한 단계(또는 --loop) 전진시킨다
---

현재 프로젝트의 하네스 작업을 전진시켜라. 사용자가 준 인자($ARGUMENTS, 예: `--item WI-0001`, `--loop`)를 그대로 전달한다.

```bash
HARNESS_DATA_HOME="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/bin/hctl" run $ARGUMENTS
```

주의: 각 단계는 내부적으로 `claude`를 헤드리스로 호출하므로 비용이 든다(중첩 실행). 긴 `--loop`은 백그라운드 실행을 권장한다.
