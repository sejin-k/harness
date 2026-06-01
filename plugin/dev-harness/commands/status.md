---
description: 하네스 작업 항목 상태를 보여준다
---

하네스 작업 항목 상태를 조회해 사용자에게 보고하라. 인자($ARGUMENTS, 예: `--item WI-0001`)가 있으면 전달한다.

```bash
HARNESS_DATA_HOME="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/bin/hctl" status $ARGUMENTS
```
