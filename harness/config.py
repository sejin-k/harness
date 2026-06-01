"""설정 로더 — 글로벌(config.yaml) + 프로젝트별(projects/<name>/harness.yaml).

대상은 '서비스 개발'이므로 프로젝트 설정은 서비스 친화 스키마를 따른다.
하네스는 여기 선언된 명령(build/test/lint/deploy)을 *실행·판정*만 하며,
특정 언어/프레임워크에 종속되지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
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


# ── cwd/플러그인 모드 ────────────────────────────────────────────────────
# 레거시는 projects/<name>/harness.yaml(중앙 등록). 플러그인 모드는 프로젝트 디렉토리
# 자체(${CLAUDE_PROJECT_DIR} 또는 cwd)의 harness.yaml을 읽고, 식별자는 경로에서 유도한다.

def project_id_for(project_dir: str | Path) -> str:
    """프로젝트 디렉토리 경로에서 안정적·충돌없는 식별자를 만든다."""
    p = Path(project_dir).expanduser().resolve()
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", p.name).strip("-") or "project"
    return f"{base}-{hashlib.sha1(str(p).encode()).hexdigest()[:8]}"


def load_project_at(project_dir: str | Path) -> dict[str, Any]:
    """프로젝트 디렉토리의 harness.yaml을 읽는다 (cwd/플러그인 모드).
    프로젝트 디렉토리 자체가 레포이며, project 식별자는 경로 기반."""
    d = Path(project_dir).expanduser().resolve()
    path = d / "harness.yaml"
    if not path.exists():
        raise FileNotFoundError(f"프로젝트 설정 없음: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = _deep_merge(_PROJECT_DEFAULTS, loaded)
    cfg["project"] = loaded.get("project") or project_id_for(d)
    cfg["project_dir"] = str(d)
    cfg["repo"] = str(d)
    return cfg


def load_project_auto(item: dict[str, Any]) -> dict[str, Any]:
    """작업 항목에 맞는 설정을 로드. project_dir이 있으면 cwd/플러그인 모드, 없으면 레거시."""
    if item.get("project_dir"):
        return load_project_at(item["project_dir"])
    return load_project(item["project"])


# ── 스캐폴딩 (첫 실행 시 harness.yaml 자동 생성) ───────────────────────────

# 설정 최상위에 올 수 있는 알려진 키 (오타 경고용)
KNOWN_KEYS = {"project", "commands", "service", "gates", "integrate",
              "concurrency", "model", "repo"}

_YAML_TEMPLATE = """\
# dev-harness 프로젝트 설정 — 이 파일은 프로젝트 레포에 커밋하세요.
# 하네스는 여기 선언된 명령을 *실행·판정*만 합니다 (언어/프레임워크 비종속).
# 비워둔 명령은 "생략(통과)"로 처리됩니다. 빌드/테스트/배포 명령을 채워 넣으세요.

project: {project}        # 표시 이름 (상태는 모든 프로젝트가 공유하므로 고유하게 유지)

commands:
  build: {build}          # 빌드 명령 (선택)
  test: {test}            # 테스트 명령 — TEST 게이트가 이 명령으로 통과/실패를 판정
  lint: {lint}            # 린트 명령 (선택)
  deploy: {deploy}        # 배포 명령 (선택; 비우면 배포 단계는 실행을 생략)

service:                  # 웹/백엔드 서비스용 (선택)
  run: {run}              # 서비스 기동 명령
  health_check: {health}  # DEPLOY 후 기동 검증 (예: curl -fsS localhost:8080/health)
  migrate: {migrate}      # DB 마이그레이션 명령

gates:
  test:
    require_pass: true      # 테스트가 반드시 통과해야 다음 단계로 진행
  deploy:
    require_human: true     # 자율성 정책: 배포만 사람 승인 (hctl approve)

integrate:
  mode: direct              # 트렁크 반영 방식: direct(main에 자동 병합) | pr(gh로 PR 생성)

concurrency: 1              # 동시에 처리할 작업 항목 수
# model: ""                 # (선택) 단계 에이전트 모델 override
"""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _makefile_targets(d: Path) -> set[str]:
    mk = d / "Makefile"
    if not mk.exists():
        return set()
    try:
        text = mk.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return set()
    return set(re.findall(r"(?m)^([A-Za-z0-9_.-]+):", text))


def detect_commands(project_dir: str | Path) -> dict[str, str]:
    """프로젝트 파일을 보고 명령을 추론한다 (스택별, 보수적).

    package.json/composer.json은 *실제 존재하는 스크립트*만 채워 거짓 실패를 피한다.
    추론할 수 없는 항목은 빈 문자열(=실행 생략)로 둔다.
    """
    d = Path(project_dir).expanduser().resolve()
    out = {k: "" for k in ("build", "test", "lint", "deploy", "run", "health", "migrate")}

    def has(*names: str) -> bool:
        return any((d / n).exists() for n in names)

    if has("package.json"):                       # Node
        scripts = _read_json(d / "package.json").get("scripts", {})
        pm = ("pnpm" if has("pnpm-lock.yaml")
              else "yarn" if has("yarn.lock") else "npm")
        if "test" in scripts:
            out["test"] = "npm test" if pm == "npm" else f"{pm} test"
        if "build" in scripts:
            out["build"] = f"{pm} run build"
        if "lint" in scripts:
            out["lint"] = f"{pm} run lint"
        if "start" in scripts:
            out["run"] = "npm start" if pm == "npm" else f"{pm} start"
    elif (has("pyproject.toml", "setup.py", "setup.cfg", "tests")
          or list(d.glob("test_*.py")) or list(d.glob("tests/test_*.py"))):  # Python
        pyproj = (d / "pyproject.toml")
        uses_pytest = has("pytest.ini", "tox.ini") or (
            pyproj.exists() and "pytest" in pyproj.read_text(encoding="utf-8", errors="ignore"))
        out["test"] = ("python3 -m pytest -q" if uses_pytest
                       else 'python3 -m unittest discover -p "test_*.py"')
    elif has("go.mod"):                            # Go
        out["test"], out["build"] = "go test ./...", "go build ./..."
    elif has("Cargo.toml"):                        # Rust
        out["test"], out["build"] = "cargo test", "cargo build"
    elif has("pom.xml"):                           # Java (Maven)
        out["test"], out["build"] = "mvn -q test", "mvn -q package"
    elif has("build.gradle", "build.gradle.kts"):  # Java (Gradle)
        out["test"], out["build"] = "./gradlew test", "./gradlew build"
    elif list(d.glob("*.sln")) or list(d.glob("*.csproj")):  # .NET
        out["test"], out["build"] = "dotnet test", "dotnet build"
    elif has("mix.exs"):                           # Elixir
        out["test"], out["build"] = "mix test", "mix compile"
    elif has("Gemfile"):                           # Ruby
        out["test"] = "bundle exec rake test" if has("Rakefile") else (
            "bundle exec rspec" if has("spec") else "")
    elif has("composer.json"):                     # PHP
        if "test" in _read_json(d / "composer.json").get("scripts", {}):
            out["test"] = "composer test"

    # Makefile 오버레이: 비어 있는 항목을 make 타깃으로 보완
    targets = _makefile_targets(d)
    for key in ("test", "build", "lint", "deploy"):
        if not out[key] and key in targets:
            out[key] = f"make {key}"
    return out


def friendly_project_name(project_dir: str | Path) -> str:
    """디렉토리 이름 기반의 읽기 쉬운 표시 이름."""
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(project_dir).resolve().name).strip("-")
    return name or "project"


def validate_project_yaml(path: str | Path) -> tuple[bool, str]:
    """harness.yaml 유효성 검사. (ok, message) 반환.

    ok=False면 치명적 오류(파싱 불가/형식 오류). ok=True여도 message가 있으면 경고(오타 키 등).
    """
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return False, f"YAML 파싱 오류: {e}"
    if data is None:
        return True, "빈 설정 (기본값으로 동작)"
    if not isinstance(data, dict):
        return False, "최상위가 매핑(dict) 형태가 아님"
    unknown = sorted(k for k in data if k not in KNOWN_KEYS)
    if unknown:
        return True, f"알 수 없는 키(오타일 수 있음): {', '.join(unknown)}"
    return True, ""


def git_status(project_dir: str | Path) -> dict[str, bool]:
    """프로젝트의 git 상태 (하네스는 worktree 격리에 git이 필수)."""
    d = Path(project_dir).expanduser().resolve()
    is_repo = (d / ".git").exists()
    has_commit = False
    if is_repo:
        r = subprocess.run("git rev-parse --verify HEAD", cwd=str(d), shell=True,
                           capture_output=True)
        has_commit = r.returncode == 0
    return {"is_repo": is_repo, "has_commit": has_commit}


def scaffold_project_yaml(project_dir: str | Path,
                          overwrite: bool = False) -> tuple[Path, bool]:
    """프로젝트 디렉토리에 harness.yaml을 생성한다. (path, created) 반환.

    이미 있으면 overwrite=False일 때 그대로 둔다(created=False).
    overwrite=True면 기존 파일을 harness.yaml.bak로 백업 후 새로 쓴다.
    """
    d = Path(project_dir).expanduser().resolve()
    path = d / "harness.yaml"
    if path.exists() and not overwrite:
        return path, False
    d.mkdir(parents=True, exist_ok=True)
    if path.exists() and overwrite:
        shutil.copy2(path, path.with_name("harness.yaml.bak"))
    fields = detect_commands(d)
    fields["project"] = friendly_project_name(d)
    # YAML 작은따옴표로 안전하게 인용 (값에 큰따옴표가 들어가도 깨지지 않게)
    quoted = {k: "'" + v.replace("'", "''") + "'" for k, v in fields.items()}
    path.write_text(_YAML_TEMPLATE.format(**quoted), encoding="utf-8")
    return path, True
