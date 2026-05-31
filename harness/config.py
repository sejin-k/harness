"""설정 로더 — 글로벌(config.yaml) + 프로젝트별(projects/<name>/harness.yaml).

대상은 '서비스 개발'이므로 프로젝트 설정은 서비스 친화 스키마를 따른다.
하네스는 여기 선언된 명령(build/test/lint/deploy)을 *실행·판정*만 하며,
특정 언어/프레임워크에 종속되지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .state import HARNESS_HOME

PROJECTS_DIR = HARNESS_HOME / "projects"
GLOBAL_CONFIG_FILE = HARNESS_HOME / "config.yaml"

# 글로벌 기본값
_GLOBAL_DEFAULTS: dict[str, Any] = {
    "model": "",                          # 빈 값이면 claude CLI 기본 모델 사용
    "permission_mode": "bypassPermissions",  # 격리 브랜치 내 자율 실행 (배포만 사람 승인)
    "max_attempts": 2,                    # 게이트 실패 시 단계 재시도 횟수
    "max_review_rounds": 2,               # 리뷰어 CHANGES_REQUESTED 수정 사이클 한도
    "runner_timeout_sec": 1200,
    "workers": 2,                         # 동시 처리 워커 풀 크기 (--workers로 재정의)
}

# 프로젝트 기본값 (서비스 개발 스키마)
_PROJECT_DEFAULTS: dict[str, Any] = {
    "service": {"run": "", "health_check": "", "migrate": ""},
    "commands": {"build": "", "test": "", "lint": "", "deploy": ""},
    "gates": {
        "test": {"require_pass": True},
        "deploy": {"require_human": True},   # ← 자율성 정책: 배포만 승인
    },
    # 트렁크 반영 방식: direct(브랜치를 main에 직접 병합, 무인) | pr(gh로 PR 생성, 사람 머지)
    "integrate": {"mode": "direct"},
    "concurrency": 1,
    "model": "",
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_global() -> dict[str, Any]:
    cfg = dict(_GLOBAL_DEFAULTS)
    if GLOBAL_CONFIG_FILE.exists():
        loaded = yaml.safe_load(GLOBAL_CONFIG_FILE.read_text(encoding="utf-8")) or {}
        cfg = _deep_merge(cfg, loaded)
    return cfg


def project_config_path(project: str) -> Path:
    return PROJECTS_DIR / project / "harness.yaml"


def load_project(project: str) -> dict[str, Any]:
    path = project_config_path(project)
    if not path.exists():
        raise FileNotFoundError(f"프로젝트 설정 없음: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = _deep_merge(_PROJECT_DEFAULTS, loaded)
    cfg["project"] = project
    # repo 경로 정규화 (상대경로면 HARNESS_HOME 기준)
    repo = cfg.get("repo") or str(PROJECTS_DIR / project)
    repo_path = Path(repo)
    if not repo_path.is_absolute():
        repo_path = (HARNESS_HOME / repo_path).resolve()
    cfg["repo"] = str(repo_path)
    return cfg


def list_projects() -> list[str]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir()
                  if (p / "harness.yaml").exists())
