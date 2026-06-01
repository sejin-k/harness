---
description: NEEDS_HUMAN 상태의 작업을 승인·재개한다 (배포 승인 등)
---

NEEDS_HUMAN으로 멈춘 작업 항목을 승인·재개하라. 항목 ID($ARGUMENTS, 예: `WI-0001`)를 전달한다.

```bash
HARNESS_DATA_HOME="${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}/bin/hctl" approve $ARGUMENTS
```
