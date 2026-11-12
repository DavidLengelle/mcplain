"""Tests of the triggers of the bench workflow: it runs again whenever a part it depends on changes"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "bench.yml"
REQUIRED_PATHS: tuple[str, ...] = (
    "engine/**",
    "bench/**",
    "api/**",
    "auth/**",
    "web/**",
    "docker/**",
    ".dockerignore",
    "compose*.yaml",
    "docker-compose*.yml",
    ".github/workflows/bench.yml",
)
SCRIPT_PATTERN = re.compile(r"scripts/[A-Za-z0-9_.-]+")


def workflow_lines() -> list[str]:
    """Return the lines of the bench workflow"""

    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def trigger_block(name: str) -> list[str]:
    """Return the lines of one trigger of the workflow, up to the next trigger or the end of the on block"""

    lines = workflow_lines()
    start = lines.index(f"  {name}:")
    block = []
    for line in lines[start + 1 :]:
        if not line.startswith("    "):
            break
        block.append(line)
    return block


def trigger_paths(name: str) -> list[str]:
    """Return the path filter of one trigger, in its written order"""

    paths = []
    inside = False
    for line in trigger_block(name):
        if line == "    paths:":
            inside = True
            continue
        if inside and line.startswith("      - "):
            paths.append(line.removeprefix("      - ").strip('"'))
        elif inside:
            break
    return paths


def test_push_and_pull_request_share_one_path_filter() -> None:
    """The push and the pull request triggers watch the same parts"""

    assert trigger_paths("push") == trigger_paths("pull_request")


def test_push_runs_on_main_only() -> None:
    """A push starts the bench on main only"""

    assert "    branches:" in trigger_block("push")
    assert "      - main" in trigger_block("push")


def test_every_part_of_the_bench_is_watched() -> None:
    """The engine, the bench, the API, the counter, the website, the images, compose and the workflow are watched"""

    paths = trigger_paths("push")
    for required in REQUIRED_PATHS:
        assert required in paths


def test_every_script_of_the_bench_is_watched() -> None:
    """Each script that the workflow runs is in the path filter"""

    paths = trigger_paths("push")
    scripts = set(SCRIPT_PATTERN.findall(WORKFLOW.read_text(encoding="utf-8")))
    assert scripts
    for script in scripts:
        assert script in paths
        assert (ROOT / script).is_file()


def test_schedule_and_manual_button_are_kept() -> None:
    """The Monday run and the manual button stay"""

    lines = workflow_lines()
    assert "  schedule:" in lines
    assert "  workflow_dispatch:" in lines


def test_a_new_run_cancels_the_old_one_of_the_same_branch() -> None:
    """One bench at a time per branch: the older run is cancelled"""

    lines = workflow_lines()
    assert "concurrency:" in lines
    assert "  group: bench-${{ github.ref }}" in lines
    assert "  cancel-in-progress: true" in lines
