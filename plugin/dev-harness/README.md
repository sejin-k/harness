# dev-harness (Claude Code 플러그인)

요구사항을 **SPEC→DESIGN→IMPLEMENT→TEST→REVIEW→INTEGRATE→DEPLOY**까지 자동 수행하는
결정적 개발 하네스를 Claude Code 플러그인으로 감싼 것.

## 구조

```
dev-harness/
├─ .claude-plugin/plugin.json   매니페스트
├─ bin/hctl                     런처 (동봉 엔진으로 hctl 실행)
├─ commands/                    슬래시 명령 (/dev-harness:add|run|status|approve)
└─ engine/                      엔진 동봉
   ├─ harness/  hctl  prompts/  config.yaml
```

> 로컬 개발에선 `engine/*`이 레포 루트로의 **심링크**다. 배포(zip/마켓플레이스) 시엔 실제 파일을 복사한다.

## 경로 모델

| 무엇 | 어디 |
|---|---|
| 엔진(읽기전용) | `${CLAUDE_PLUGIN_ROOT}/engine` |
| 상태·worktree | `${CLAUDE_PLUGIN_DATA}` (= `~/.claude/plugins/data/<id>/`, 사용자 홈) |
| 설정 `harness.yaml` | **프로젝트 레포에 커밋** (build/test/deploy 명령) |
| 대상 프로젝트 | `${CLAUDE_PROJECT_DIR}` (또는 현재 위치) |

## 로컬 테스트

```bash
claude --plugin-dir ./plugin/dev-harness
# 세션에서:
/dev-harness:add 장바구니 합계 기능을 구현하라
/dev-harness:run --loop
/dev-harness:status
```

## 주의

- 각 단계는 `claude`를 헤드리스로 호출한다(중첩 실행, 비용 2겹). 긴 `--loop`은 백그라운드 권장.
- 현재 INTEGRATE는 트렁크를 `reset --hard`로 정리하므로, 사용자의 커밋 안 된 작업이 있는
  프로젝트에선 위험하다. 전용 trunk 워크트리 분리는 풀구성 단계에서 처리 예정.
