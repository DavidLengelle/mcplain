"""Tests for file roles: imported tests and examples and declared entry points count as server code"""

import json
from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.models import LocationKind
from mcplain.paths import location_kind
from mcplain.verdict import counted_findings


def test_imported_example_counts_for_the_verdict(fixtures: Path) -> None:
    """examples/helper.py is imported by the server, so its network call is server code"""

    result = analyze_directory(fixtures / "example_bypass")
    [server] = result.servers
    [report] = server.tools
    [post] = report.findings
    assert post.capability is Capability.NETWORK
    assert post.file == "examples/helper.py"
    assert post.location_kind is LocationKind.SERVER_CODE
    assert [step.function for step in post.call_chain] == ["send_report"]
    assert post in counted_findings(server)


def test_example_not_imported_stays_an_example(fixtures: Path) -> None:
    """examples/demo.py is not imported, so it is still reported as an example"""

    analysis = PythonAdapter().analyze(fixtures / "example_bypass")
    [demo] = [finding for finding in analysis.findings if finding.file == "examples/demo.py"]
    assert demo.location_kind is LocationKind.TEST_OR_EXAMPLE


def test_python_entry_points_are_server_code(tmp_path: Path) -> None:
    """Console scripts and __main__.py are server code wherever they live"""

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["mcp"]\n\n[project.scripts]\nx = "examples.run:main"\n',
        encoding="utf-8",
    )
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "run.py").write_text("import os\n\n\ndef main():\n    os.system('ls')\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__main__.py").write_text("import os\n\nos.remove('x')\n")
    analysis = PythonAdapter().analyze(tmp_path)
    assert {finding.location_kind for finding in analysis.findings} == {LocationKind.SERVER_CODE}


def test_wheel_entry_points_file(tmp_path: Path) -> None:
    """entry_points.txt of a wheel names the entry module"""

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "examples.py").write_text("import os\n\n\ndef main():\n    os.system('ls')\n")
    (tmp_path / "pkg-1.0.dist-info").mkdir()
    (tmp_path / "pkg-1.0.dist-info" / "entry_points.txt").write_text("[console_scripts]\npkg = pkg.examples:main\n")
    analysis = PythonAdapter().analyze(tmp_path)
    assert [finding.location_kind for finding in analysis.findings] == [LocationKind.SERVER_CODE]


def test_javascript_main_and_bin_are_server_code(tmp_path: Path) -> None:
    """main and bin of package.json are server code, and so is what they import"""

    manifest = {"name": "x", "main": "test/index.js", "bin": {"x": "./scripts/build-cli"}}
    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "index.js").write_text('import { run } from "./run.js";\nrun();\n')
    (tmp_path / "test" / "run.js").write_text('import { execSync } from "child_process";\nexport function run() { execSync("ls"); }\n')
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "build-cli.js").write_text('import fs from "fs";\nfs.rmSync("x");\n')
    (tmp_path / "test" / "unused.test.js").write_text('import fs from "fs";\nfs.writeFileSync("x", "y");\n')
    analysis = JavaScriptAdapter().analyze(tmp_path)
    kinds = {finding.file: finding.location_kind for finding in analysis.findings}
    assert kinds == {
        "test/run.js": LocationKind.SERVER_CODE,
        "scripts/build-cli.js": LocationKind.SERVER_CODE,
        "test/unused.test.js": LocationKind.TEST_OR_EXAMPLE,
    }


@pytest.mark.parametrize(
    "path",
    [
        "build/snapshot-tests/device-availability.js",
        "build/smoke-tests/mcp-test-harness.js",
        "build/benchmarks/claude-ui/run.js",
        "pkg/smoke_tests/run.py",
        "pkg/snapshot_tests/run.py",
        "test-calendar-fix.js",
        "src/test-helpers.mjs",
        "test-server.py",
    ],
)
def test_snapshot_smoke_bench_folders_and_test_dash_files_are_tests(path: str) -> None:
    """Folders of snapshot tests, smoke tests and benchmarks, and test-*.js files, are tests (decision of 3 November 2026)"""

    assert location_kind(path) is LocationKind.TEST_OR_EXAMPLE


@pytest.mark.parametrize("path", ["build.js", "build.mjs", "build.ts", "build.py"])
def test_a_build_file_at_the_root_is_a_build_script(path: str) -> None:
    """build.js at the root of the package, and its Python equivalent, are build scripts"""

    assert location_kind(path) is LocationKind.BUILD_SCRIPT


@pytest.mark.parametrize("path", ["src/build.js", "src/utils/build.py", "latest-test.js", "contest-entry.js", "benchmark.js"])
def test_close_names_stay_server_code(path: str) -> None:
    """A build.js below the root, and names that only look like tests, stay server code"""

    assert location_kind(path) is LocationKind.SERVER_CODE


def test_a_test_dash_file_imported_by_the_server_counts(tmp_path: Path) -> None:
    """A test-*.js file or a smoke-tests folder imported by the server is server code again"""

    (tmp_path / "package.json").write_text(json.dumps({"name": "x", "main": "index.js"}), encoding="utf-8")
    (tmp_path / "index.js").write_text('import { run } from "./test-run.js";\nimport { probe } from "./smoke-tests/probe.js";\nrun();\nprobe();\n')
    (tmp_path / "test-run.js").write_text('import { execSync } from "child_process";\nexport function run() { execSync("ls"); }\n')
    (tmp_path / "smoke-tests").mkdir()
    (tmp_path / "smoke-tests" / "probe.js").write_text('import { execSync } from "child_process";\nexport function probe() { execSync("ls"); }\n')
    (tmp_path / "test-alone.js").write_text('import { execSync } from "child_process";\nexecSync("ls");\n')
    (tmp_path / "build.js").write_text('import { execSync } from "child_process";\nexecSync("echo build");\n')
    analysis = JavaScriptAdapter().analyze(tmp_path)
    kinds = {finding.file: finding.location_kind for finding in analysis.findings}
    assert kinds == {
        "test-run.js": LocationKind.SERVER_CODE,
        "smoke-tests/probe.js": LocationKind.SERVER_CODE,
        "test-alone.js": LocationKind.TEST_OR_EXAMPLE,
        "build.js": LocationKind.BUILD_SCRIPT,
    }


def test_a_build_file_run_by_npm_install_counts(tmp_path: Path) -> None:
    """build.js run by a postinstall script is install-time code, so it counts"""

    manifest = {"name": "x", "main": "index.js", "scripts": {"postinstall": "node build.js"}}
    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "index.js").write_text("export const x = 1;\n")
    (tmp_path / "build.js").write_text('import { execSync } from "child_process";\nexecSync("echo build");\n')
    analysis = JavaScriptAdapter().analyze(tmp_path)
    assert [(finding.file, finding.location_kind) for finding in analysis.findings if finding.file == "build.js"] == [
        ("build.js", LocationKind.SERVER_CODE)
    ]
