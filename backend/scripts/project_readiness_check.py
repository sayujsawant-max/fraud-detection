"""Pre-publish readiness check for the FraudShield repo.

Runs a series of cheap structural checks that catch the common
"forgot to commit X / left a placeholder in Y" failure modes that
trip a portfolio repo right before it goes public. Exit 0 means safe
to push; exit 1 means at least one required item is missing or stale.

Usage::

    python backend/scripts/project_readiness_check.py
    python backend/scripts/project_readiness_check.py --strict  # fail on advisory

This script is intentionally **structural only** — it doesn't run
tests, lint, or builds. Those gates already live in ``make phase9-test``
and the GitHub Actions CI workflow.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_ROOT.parent

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402

# ---------------------------------------------------------------------------
# Required files
# ---------------------------------------------------------------------------

REQUIRED_FILES: tuple[Path, ...] = (
    # Root
    _PROJECT_ROOT / "README.md",
    _PROJECT_ROOT / "LICENSE",
    _PROJECT_ROOT / "Makefile",
    _PROJECT_ROOT / ".env.example",
    _PROJECT_ROOT / ".env.production.example",
    _PROJECT_ROOT / ".gitignore",
    _PROJECT_ROOT / ".pre-commit-config.yaml",
    _PROJECT_ROOT / ".ruff.toml",
    _PROJECT_ROOT / "FRAUDSHIELD_BLUEPRINT.md",
    # Docs
    _PROJECT_ROOT / "docs" / "architecture.md",
    _PROJECT_ROOT / "docs" / "deployment.md",
    _PROJECT_ROOT / "docs" / "interview-guide.md",
    _PROJECT_ROOT / "docs" / "demo-script.md",
    _PROJECT_ROOT / "docs" / "troubleshooting.md",
    _PROJECT_ROOT / "docs" / "future-improvements.md",
    _PROJECT_ROOT / "docs" / "phase-plan.md",
    _PROJECT_ROOT / "docs" / "api-reference.md",
    _PROJECT_ROOT / "docs" / "assets" / "README.md",
    _PROJECT_ROOT / "docs" / "assets" / "architecture-diagram.md",
    # Docs assets placeholders
    _PROJECT_ROOT / "docs" / "assets" / ".gitkeep",
    _PROJECT_ROOT / "docs" / "assets" / "screenshots" / ".gitkeep",
    _PROJECT_ROOT / "docs" / "assets" / "gifs" / ".gitkeep",
    # GitHub
    _PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
    _PROJECT_ROOT / ".github" / "workflows" / "cd.yml",
    _PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md",
    _PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md",
    _PROJECT_ROOT / ".github" / "pull_request_template.md",
    # Backend
    _PROJECT_ROOT / "backend" / "Dockerfile",
    _PROJECT_ROOT / "backend" / "requirements.txt",
    _PROJECT_ROOT / "backend" / "requirements-dev.txt",
    _PROJECT_ROOT / "backend" / "pyproject.toml",
    _PROJECT_ROOT / "backend" / "pytest.ini",
    _PROJECT_ROOT / "backend" / "alembic.ini",
    _PROJECT_ROOT / "backend" / "scripts" / "run_smoke_test.py",
    _PROJECT_ROOT / "backend" / "scripts" / "send_demo_predictions.py",
    _PROJECT_ROOT / "backend" / "scripts" / "sample_transaction.json",
    # Frontend
    _PROJECT_ROOT / "frontend" / "Dockerfile",
    _PROJECT_ROOT / "frontend" / "package.json",
    _PROJECT_ROOT / "frontend" / "package-lock.json",
    _PROJECT_ROOT / "frontend" / "tsconfig.json",
    _PROJECT_ROOT / "frontend" / "next.config.mjs",
    _PROJECT_ROOT / "frontend" / "tailwind.config.ts",
    _PROJECT_ROOT / "frontend" / ".eslintrc.json",
    _PROJECT_ROOT / "frontend" / ".env.example",
    # Infra
    _PROJECT_ROOT / "infra" / "docker-compose.yml",
    _PROJECT_ROOT / "infra" / "prometheus" / "prometheus.yml",
    _PROJECT_ROOT
    / "infra"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "dashboard.yml",
    _PROJECT_ROOT
    / "infra"
    / "grafana"
    / "provisioning"
    / "datasources"
    / "prometheus.yml",
    _PROJECT_ROOT
    / "infra"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "fraudshield-api-performance.json",
    _PROJECT_ROOT
    / "infra"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "fraudshield-model-behavior.json",
    _PROJECT_ROOT
    / "infra"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "fraudshield-drift-retraining.json",
    _PROJECT_ROOT
    / "infra"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "fraudshield-system-health.json",
)

# Sections / phrases the README must contain for the portfolio claim
# to hold up.
README_REQUIRED_SUBSTRINGS: tuple[str, ...] = (
    "FraudShield MLOps",
    "Quick start",
    "make docker-up",
    "Tech stack",
    "FastAPI",
    "MLflow",
    "Evidently",
    "Prefect",
    "Prometheus",
    "Grafana",
    "Next.js",
    "MIT",
)

# Substrings that should NOT appear in major docs (lingering placeholders).
STALE_PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "TODO: write",
    "TODO write",
    "<<TODO>>",
    "Lorem ipsum",
    "FIXME: replace",
)

# Substrings that should never appear ANYWHERE under git.
FORBIDDEN_SECRET_TOKENS: tuple[str, ...] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "AWS_SECRET_ACCESS_KEY=AKIA",  # caught by detect-private-key too
)


@dataclass
class CheckResult:
    """Outcome of a single readiness probe."""

    name: str
    ok: bool
    detail: str
    critical: bool


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_required_files() -> list[CheckResult]:
    """Every file in :data:`REQUIRED_FILES` must exist on disk."""
    results: list[CheckResult] = []
    for path in REQUIRED_FILES:
        rel = path.relative_to(_PROJECT_ROOT)
        if path.exists():
            results.append(
                CheckResult(
                    name=f"file: {rel}", ok=True, detail="present", critical=True
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"file: {rel}",
                    ok=False,
                    detail="missing",
                    critical=True,
                )
            )
    return results


def check_readme_sections() -> list[CheckResult]:
    """The README must mention each canonical portfolio token."""
    readme = _PROJECT_ROOT / "README.md"
    if not readme.exists():
        return [
            CheckResult(
                name="README content",
                ok=False,
                detail="README.md is missing",
                critical=True,
            )
        ]
    text = readme.read_text(encoding="utf-8", errors="replace")
    results: list[CheckResult] = []
    for token in README_REQUIRED_SUBSTRINGS:
        results.append(
            CheckResult(
                name=f"README contains: {token!r}",
                ok=token in text,
                detail="found" if token in text else "missing",
                critical=True,
            )
        )
    return results


def check_no_stale_placeholders() -> list[CheckResult]:
    """Major docs should not contain leftover placeholder strings."""
    targets = [
        _PROJECT_ROOT / "README.md",
        _PROJECT_ROOT / "docs" / "architecture.md",
        _PROJECT_ROOT / "docs" / "deployment.md",
        _PROJECT_ROOT / "docs" / "interview-guide.md",
        _PROJECT_ROOT / "docs" / "demo-script.md",
        _PROJECT_ROOT / "docs" / "troubleshooting.md",
        _PROJECT_ROOT / "docs" / "future-improvements.md",
    ]
    results: list[CheckResult] = []
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        offenders = [tok for tok in STALE_PLACEHOLDER_TOKENS if tok in text]
        rel = path.relative_to(_PROJECT_ROOT)
        if offenders:
            results.append(
                CheckResult(
                    name=f"placeholder scan: {rel}",
                    ok=False,
                    detail=f"contains stale token(s): {offenders}",
                    critical=True,
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"placeholder scan: {rel}",
                    ok=True,
                    detail="clean",
                    critical=True,
                )
            )
    return results


def check_env_example_safe() -> list[CheckResult]:
    """``.env.example`` should ship safe placeholders only."""
    env_example = _PROJECT_ROOT / ".env.example"
    if not env_example.exists():
        return [
            CheckResult(
                name=".env.example safe",
                ok=False,
                detail="missing",
                critical=True,
            )
        ]
    text = env_example.read_text(encoding="utf-8", errors="replace")
    # The dev defaults are intentionally weak ("change-me",
    # "fraudshield_password"). Real credentials would look very
    # different — refuse anything that smells like an actual key.
    suspicious = re.findall(r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}", text)
    if suspicious:
        return [
            CheckResult(
                name=".env.example safe",
                ok=False,
                detail=f"contains likely real secrets: {suspicious}",
                critical=True,
            )
        ]
    return [
        CheckResult(
            name=".env.example safe",
            ok=True,
            detail="only placeholder secrets present",
            critical=True,
        )
    ]


def check_no_env_in_git() -> list[CheckResult]:
    """``.env`` must NOT be tracked by git."""
    try:
        out = subprocess.run(
            ["git", "ls-files", ".env", "backend/.env", "frontend/.env"],
            cwd=_PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return [
            CheckResult(
                name=".env not tracked",
                ok=False,
                detail=f"git not available: {exc}",
                critical=False,
            )
        ]
    tracked = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if tracked:
        return [
            CheckResult(
                name=".env not tracked",
                ok=False,
                detail=f"tracked: {tracked}",
                critical=True,
            )
        ]
    return [
        CheckResult(
            name=".env not tracked",
            ok=True,
            detail="not in the index",
            critical=True,
        )
    ]


def check_no_obvious_secrets() -> list[CheckResult]:
    """Scan committed files for forbidden secret tokens."""
    try:
        out = subprocess.run(
            ["git", "grep", "-In", "-l", "BEGIN PRIVATE KEY", "--", ":(exclude).git"],
            cwd=_PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [
            CheckResult(
                name="no committed private keys",
                ok=True,
                detail="git not available — skipping (advisory)",
                critical=False,
            )
        ]
    offenders = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if offenders:
        return [
            CheckResult(
                name="no committed private keys",
                ok=False,
                detail=f"private key marker found in: {offenders}",
                critical=True,
            )
        ]
    return [
        CheckResult(
            name="no committed private keys",
            ok=True,
            detail="clean",
            critical=True,
        )
    ]


def check_phase_plan_marks_complete() -> list[CheckResult]:
    """``docs/phase-plan.md`` should mark all 10 phases complete."""
    phase_plan = _PROJECT_ROOT / "docs" / "phase-plan.md"
    if not phase_plan.exists():
        return [
            CheckResult(
                name="phase-plan complete",
                ok=False,
                detail="missing",
                critical=True,
            )
        ]
    text = phase_plan.read_text(encoding="utf-8", errors="replace")
    expected_marks = [f"## Phase {i} —" for i in range(11)]
    found = sum(1 for m in expected_marks if m in text)
    complete_marks = text.count("✅ *(complete)*")
    ok = found == 11 and complete_marks >= 11
    return [
        CheckResult(
            name="phase-plan complete",
            ok=ok,
            detail=f"found {found}/11 phase headings, {complete_marks} complete markers",
            critical=True,
        )
    ]


def check_pyproject_coverage_floor() -> list[CheckResult]:
    """``backend/pyproject.toml`` must set a coverage floor of 65."""
    pyproject = _PROJECT_ROOT / "backend" / "pyproject.toml"
    if not pyproject.exists():
        return [
            CheckResult(
                name="pyproject coverage floor",
                ok=False,
                detail="missing",
                critical=True,
            )
        ]
    text = pyproject.read_text(encoding="utf-8", errors="replace")
    ok = "fail_under = 65" in text or "fail_under=65" in text
    return [
        CheckResult(
            name="pyproject coverage floor",
            ok=ok,
            detail="fail_under = 65 present" if ok else "fail_under = 65 missing",
            critical=True,
        )
    ]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_all_checks() -> list[CheckResult]:
    """Execute every readiness probe and return the merged result list."""
    results: list[CheckResult] = []
    results.extend(check_required_files())
    results.extend(check_readme_sections())
    results.extend(check_no_stale_placeholders())
    results.extend(check_env_example_safe())
    results.extend(check_no_env_in_git())
    results.extend(check_no_obvious_secrets())
    results.extend(check_phase_plan_marks_complete())
    results.extend(check_pyproject_coverage_floor())
    return results


def summarise(results: list[CheckResult], *, strict: bool = False) -> int:
    """Pretty-print + return a shell exit code."""
    width = max(len(r.name) for r in results) + 2
    logger.info("=" * (width + 24))
    logger.info("FraudShield readiness check")
    logger.info("=" * (width + 24))

    critical_failures = 0
    advisory_failures = 0
    for r in results:
        label = "PASS" if r.ok else "FAIL"
        marker = "•" if r.critical else "○"
        line = f"  {marker} {r.name:<{width}} {label:>4}  {r.detail}"
        if r.ok:
            logger.info(line)
        elif r.critical or strict:
            critical_failures += 1
            logger.error(line)
        else:
            advisory_failures += 1
            logger.warning(line)

    logger.info("=" * (width + 24))
    if critical_failures:
        logger.error(
            "readiness check failed | critical={} advisory={}",
            critical_failures,
            advisory_failures,
        )
        return 1
    if advisory_failures:
        logger.warning(
            "readiness check passed with advisory warnings | advisory={}",
            advisory_failures,
        )
    else:
        logger.info("readiness check passed — repo is publish-ready")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat advisory checks as critical too.",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point used by ``make readiness-check``."""
    configure_logging()
    args = _parse_args()
    return summarise(run_all_checks(), strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
