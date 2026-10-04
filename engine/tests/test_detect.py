"""Tests for server, language and compiled code detection"""

import json
from pathlib import Path

import pytest

from mcplain.detect import detect
from mcplain.errors import DetectionError
from mcplain.models import AnalysisStatus


def write(path: Path, text: str) -> None:
    """Write a text file, creating its folders"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def npm_server(folder: Path, name: str) -> None:
    """Create a minimal npm MCP server"""

    manifest = {"name": name, "dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}
    write(folder / "package.json", json.dumps(manifest))
    write(folder / "index.js", "export {};\n")


def test_monorepo_lists_both_servers(fixtures: Path) -> None:
    """Two servers and no selection give multiple_servers with both paths"""

    detection = detect(fixtures / "monorepo")
    assert detection.status is AnalysisStatus.MULTIPLE_SERVERS
    assert [(candidate.path, candidate.language) for candidate in detection.candidates] == [
        ("src/a", "javascript"),
        ("src/b", "python"),
    ]


def test_monorepo_with_subfolder(fixtures: Path) -> None:
    """Targeting a subfolder selects that server"""

    detection = detect(fixtures / "monorepo", "src/b")
    assert detection.status is AnalysisStatus.OK
    assert detection.server is not None
    assert detection.server.path == "src/b"
    assert detection.server.sdk == "mcp"


def test_go_server_is_unsupported(fixtures: Path) -> None:
    """A Go server using the official SDK is reported as unsupported_language"""

    detection = detect(fixtures / "go_server")
    assert detection.status is AnalysisStatus.UNSUPPORTED_LANGUAGE
    assert detection.language == "go"
    assert detection.server is not None
    assert detection.server.sdk == "github.com/modelcontextprotocol/go-sdk"


def test_awesome_list_is_not_a_server(fixtures: Path) -> None:
    """A repository made of Markdown only is not_a_server"""

    detection = detect(fixtures / "awesome_list")
    assert detection.status is AnalysisStatus.NOT_A_SERVER
    assert detection.notes == ["note.mostly_documentation"]


def test_npm_compiled(fixtures: Path) -> None:
    """A package made of a binary and platform packages is compiled"""

    detection = detect(fixtures / "npm_compiled")
    assert detection.status is AnalysisStatus.COMPILED
    assert detection.compiled_files == ["bin/compiled-server"]
    assert "note.platform_binary_dependencies" in detection.notes


def test_partially_compiled_server(tmp_path: Path) -> None:
    """A server with source code and a native addon is analyzed with a warning"""

    npm_server(tmp_path, "partial")
    (tmp_path / "prebuilds").mkdir()
    (tmp_path / "prebuilds" / "addon.node").write_bytes(b"\x7fELF" + bytes(32))
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.OK
    assert detection.compiled_files == ["prebuilds/addon.node"]
    assert "note.partially_compiled" in detection.notes


def test_windows_executable_signature(tmp_path: Path) -> None:
    """A PE executable is recognized by its header, whatever its name"""

    npm_server(tmp_path, "pe")
    header = bytearray(256)
    header[0:2] = b"MZ"
    header[60:64] = (128).to_bytes(4, "little")
    header[128:132] = b"PE\x00\x00"
    (tmp_path / "helper.dat").write_bytes(bytes(header))
    assert detect(tmp_path).compiled_files == ["helper.dat"]


def test_typescript_is_recognized(fixtures: Path) -> None:
    """A package.json server with .ts sources is TypeScript"""

    detection = detect(fixtures / "ts_registertool")
    assert detection.server is not None
    assert detection.server.language == "typescript"


def test_wheel_metadata_is_a_manifest(tmp_path: Path) -> None:
    """An extracted wheel is recognized from its METADATA file"""

    write(tmp_path / "demo" / "server.py", "from mcp.server import MCPServer\n")
    write(tmp_path / "demo-1.0.dist-info" / "METADATA", "Name: demo\nRequires-Dist: mcp[cli]>=2.0\n")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.OK
    assert detection.server is not None
    assert detection.server.path == "."
    assert detection.server.name == "demo"


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("requirements.txt", "# deps\nfastmcp>=2.0\nrequests\n"),
        ("requirements-prod.txt", "mcp==2.3.0\n"),
        ("setup.py", "from setuptools import setup\nsetup(name='x', install_requires=['mcp>=1.0'])\n"),
        ("setup.cfg", "[metadata]\nname = x\n\n[options]\ninstall_requires =\n    mcp>=1.0\n"),
        ("pyproject.toml", "[tool.poetry.dependencies]\npython = '^3.12'\nfastmcp = '^2'\n"),
    ],
)
def test_python_manifests(tmp_path: Path, name: str, content: str) -> None:
    """Every Python project file can reveal an MCP SDK dependency"""

    write(tmp_path / name, content)
    write(tmp_path / "server.py", "print('x')\n")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.OK
    assert detection.server is not None
    assert detection.server.language == "python"


def test_setup_py_is_never_executed(tmp_path: Path) -> None:
    """setup.py is read as text, so its code has no effect"""

    marker = tmp_path / "executed"
    write(tmp_path / "setup.py", f"open({str(marker)!r}, 'w').write('x')\nsetup(install_requires=['mcp'])\n")
    detect(tmp_path)
    assert not marker.exists()


def test_detection_from_imports(tmp_path: Path) -> None:
    """A lone script that imports an MCP SDK is found without a project file"""

    write(tmp_path / "server.py", "from fastmcp import FastMCP\n\nmcp = FastMCP('x')\n")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.OK
    assert detection.notes == ["note.detected_from_imports"]


def test_examples_do_not_create_extra_servers(tmp_path: Path) -> None:
    """An example server inside examples/ does not hide the real one"""

    npm_server(tmp_path, "real")
    npm_server(tmp_path / "examples" / "demo", "demo")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.OK
    assert detection.server is not None
    assert detection.server.path == "."


def test_list_is_capped_at_fifty(tmp_path: Path) -> None:
    """At most fifty servers are listed"""

    for index in range(55):
        npm_server(tmp_path / "servers" / f"s{index:02d}", f"s{index}")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.MULTIPLE_SERVERS
    assert len(detection.candidates) == 50
    assert detection.truncated


def test_project_without_sdk_is_not_a_server(tmp_path: Path) -> None:
    """A JavaScript project without an MCP SDK is not_a_server"""

    write(tmp_path / "package.json", json.dumps({"name": "x", "dependencies": {"express": "^5"}}))
    write(tmp_path / "index.js", "export {};\n")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.NOT_A_SERVER
    assert detection.notes == ["note.no_mcp_sdk"]


def test_rust_project_without_known_sdk_is_unsupported(tmp_path: Path) -> None:
    """A Rust project is reported as an unsupported language"""

    write(tmp_path / "Cargo.toml", "[package]\nname = 'x'\n\n[dependencies]\nserde = '1'\n")
    write(tmp_path / "src" / "main.rs", "fn main() {}\n")
    detection = detect(tmp_path)
    assert detection.status is AnalysisStatus.UNSUPPORTED_LANGUAGE
    assert detection.language == "rust"


def test_missing_subfolder(fixtures: Path) -> None:
    """A subfolder that does not exist is an error"""

    with pytest.raises(DetectionError) as error:
        detect(fixtures / "monorepo", "src/zzz")
    assert error.value.code == "analyze.subdir_not_found"
