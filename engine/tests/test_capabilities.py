"""Tests that the capability tables classify the expected file system calls"""

from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.capabilities import Capability, PathKind, find_sensitive_paths, is_secret_name, path_kinds

JAVASCRIPT_CALLS: list[tuple[str, Capability]] = [
    ("fs.stat(p)", Capability.FS_READ),
    ("fs.lstat(p)", Capability.FS_READ),
    ("fs.realpath(p)", Capability.FS_READ),
    ("fs.access(p)", Capability.FS_READ),
    ("fs.opendir(p)", Capability.FS_READ),
    ("fs.readdir(p)", Capability.FS_READ),
    ("fs.createReadStream(p)", Capability.FS_READ),
    ("fs.existsSync(p)", Capability.FS_READ),
    ("fs.open(p, 'r')", Capability.FS_READ),
    ("fs.open(p, 'w')", Capability.FS_WRITE),
    ("fs.open(p, flags)", Capability.FS_WRITE),
    ("fs.rename(a, b)", Capability.FS_WRITE),
    ("fs.mkdir(p)", Capability.FS_WRITE),
    ("fs.copyFile(a, b)", Capability.FS_WRITE),
    ("fs.appendFile(p, d)", Capability.FS_WRITE),
    ("fs.chmod(p, 0o600)", Capability.FS_WRITE),
    ("fs.createWriteStream(p)", Capability.FS_WRITE),
]

PYTHON_CALLS: list[tuple[str, Capability]] = [
    ("os.stat(p)", Capability.FS_READ),
    ("os.listdir(p)", Capability.FS_READ),
    ("os.scandir(p)", Capability.FS_READ),
    ("Path(p).iterdir()", Capability.FS_READ),
    ("Path(p).glob('*.py')", Capability.FS_READ),
    ("glob.glob('*.py')", Capability.FS_READ),
    ("Path(p).stat()", Capability.FS_READ),
    ("os.rename(a, b)", Capability.FS_WRITE),
    ("os.replace(a, b)", Capability.FS_WRITE),
    ("os.mkdir(p)", Capability.FS_WRITE),
    ("os.makedirs(p)", Capability.FS_WRITE),
    ("os.chmod(p, 0o600)", Capability.FS_WRITE),
    ("shutil.copy(a, b)", Capability.FS_WRITE),
    ("shutil.copytree(a, b)", Capability.FS_WRITE),
    ("shutil.move(a, b)", Capability.FS_WRITE),
    ("shutil.rmtree(p)", Capability.FS_WRITE),
]


@pytest.mark.parametrize(("call", "capability"), JAVASCRIPT_CALLS)
def test_javascript_file_system_calls(tmp_path: Path, call: str, capability: Capability) -> None:
    """Node fs calls, including the promises API, are classified"""

    source = f'import fs from "fs/promises";\n\nexport function work(p, a, b, d, flags) {{\n  {call};\n}}\n'
    (tmp_path / "index.js").write_text(source, encoding="utf-8")
    analysis = JavaScriptAdapter().analyze(tmp_path)
    assert [finding.capability for finding in analysis.findings] == [capability]


@pytest.mark.parametrize(("call", "capability"), PYTHON_CALLS)
def test_python_file_system_calls(tmp_path: Path, call: str, capability: Capability) -> None:
    """os, pathlib, glob and shutil calls are classified"""

    source = f"import glob\nimport os\nimport shutil\nfrom pathlib import Path\n\n\ndef work(p, a, b):\n    {call}\n"
    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    analysis = PythonAdapter().analyze(tmp_path)
    assert [finding.capability for finding in analysis.findings] == [capability]


def test_shutil_queries_are_not_writes(tmp_path: Path) -> None:
    """shutil.which and shutil.disk_usage only read information"""

    source = "import shutil\n\n\ndef work():\n    shutil.which('node')\n    shutil.disk_usage('/')\n"
    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    assert PythonAdapter().analyze(tmp_path).findings == []


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("API_KEY", True),
        ("GITHUB_TOKEN", True),
        ("DB_PASSWORD", True),
        ("openaiApiKey", True),
        ("PORT", False),
        ("LOG_LEVEL", False),
        ("PWD", False),
        ("HOME", False),
    ],
)
def test_secret_names(name: str, secret: bool) -> None:
    """Variable names that look like secrets are recognized"""

    assert is_secret_name(name) is secret


@pytest.mark.parametrize(
    ("text", "category", "kind"),
    [
        ("~/.ssh/id_ed25519", "ssh_keys", PathKind.SECRET),
        ("/home/me/.ssh/authorized_keys", "ssh_authorized_keys", PathKind.AUTOSTART),
        ("~/.bashrc", "shell_startup", PathKind.AUTOSTART),
        ("~/.zsh_history", "shell_history", PathKind.SECRET),
        ("~/.npmrc", "package_config", PathKind.SECRET),
        ("~/.npmrc", "package_config", PathKind.TOOL_CONFIG),
        ("~/.gitconfig", "git_config", PathKind.TOOL_CONFIG),
        ("~/Library/Application Support/Claude/claude_desktop_config.json", "mcp_client_config", PathKind.TOOL_CONFIG),
        ("~/.cursor/mcp.json", "mcp_client_config", PathKind.TOOL_CONFIG),
        (".vscode/mcp.json", "mcp_client_config", PathKind.TOOL_CONFIG),
        ("/etc/cron.d/backup", "cron", PathKind.AUTOSTART),
        ("crontab -l", "cron", PathKind.AUTOSTART),
        ("~/.config/systemd/user/agent.service", "systemd_unit", PathKind.AUTOSTART),
        ("~/Library/LaunchAgents/com.x.plist", "launch_agent", PathKind.AUTOSTART),
        ("AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup", "windows_startup", PathKind.AUTOSTART),
        ("~/.config/autostart/x.desktop", "desktop_autostart", PathKind.AUTOSTART),
        ("~/.ethereum/keystore", "crypto_wallet", PathKind.SECRET),
        ("Local Extension Settings/nkbihfbeogaeaoehlefnkodbefgpgknn", "crypto_wallet", PathKind.SECRET),
    ],
)
def test_sensitive_path_categories(text: str, category: str, kind: PathKind) -> None:
    """Each sensitive path has a category and at least one kind: secret, autostart or tool config"""

    categories = [found for found, _ in find_sensitive_paths(text)]
    assert category in categories
    assert kind in path_kinds(category)


@pytest.mark.parametrize("text", ["user.profile", "profile.json", ".env.example", "README.md", "my_crontab_parser"])
def test_ordinary_names_are_not_sensitive(text: str) -> None:
    """Ordinary file names that only look like sensitive ones are not reported"""

    assert find_sensitive_paths(text) == []
