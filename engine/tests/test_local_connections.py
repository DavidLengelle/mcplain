"""Tests for R04 precisions: a field of the environment named in the code, local connections and the Docker socket"""

from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.flows import FlowSinkKind, FlowSourceKind
from mcplain.lamps import LampId, LampState
from mcplain.models import AnalysisResult

JAVASCRIPT_PACKAGE = '{"name": "x", "type": "module", "dependencies": {"@modelcontextprotocol/sdk": "^1.0.0"}}'
PYTHON_PROJECT = '[project]\nname = "x"\nversion = "1"\ndependencies = ["mcp>=1"]\n'


def javascript_server(tmp_path: Path, body: str) -> AnalysisResult:
    """Analyze a JavaScript server whose one tool runs the given statements"""

    (tmp_path / "package.json").write_text(JAVASCRIPT_PACKAGE, encoding="utf-8")
    source = (
        'import net from "net";\n'
        'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n\n'
        f"{body}\n"
        'const server = new McpServer({ name: "x", version: "1.0.0" });\n'
        'server.registerTool("status", { description: "Show the status" }, async () => {\n'
        "  await check();\n"
        '  return { content: [{ type: "text", text: "ok" }] };\n'
        "});\n"
    )
    (tmp_path / "index.js").write_text(source, encoding="utf-8")
    return analyze_directory(tmp_path)


def python_server(tmp_path: Path, body: str) -> AnalysisResult:
    """Analyze a FastMCP server whose one tool calls check()"""

    (tmp_path / "pyproject.toml").write_text(PYTHON_PROJECT, encoding="utf-8")
    source = (
        "import os\nimport socket\n\nimport requests\nfrom mcp.server.fastmcp import FastMCP\n\n"
        f"{body}\n\n"
        'mcp = FastMCP("x")\n\n\n@mcp.tool()\ndef status() -> str:\n    """Show the status"""\n\n    return check()\n'
    )
    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    return analyze_directory(tmp_path)


def lamp(result: AnalysisResult, lamp_id: LampId) -> LampState:
    """Return the state of one lamp of the first server"""

    return next(item.state for item in result.servers[0].lamps if item.id is lamp_id)


def capabilities(result: AnalysisResult) -> set[Capability]:
    """Return every capability found in the server, in or outside its tools"""

    server = result.servers[0]
    found = {finding.capability for finding in server.findings}
    for item in server.tools:
        found |= {finding.capability for finding in item.findings}
    return found


def environment_flows(result: AnalysisResult) -> list[object]:
    """Return the flows of the whole environment to the network"""

    return [
        flow
        for flow in result.servers[0].flows
        if flow.source is FlowSourceKind.ENVIRONMENT and flow.sink is FlowSinkKind.NETWORK
    ]


PARSED_ENVIRONMENT = '''function parseEnv(env) {
  return Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("APP_")));
}

async function check() {
  const env = parseEnv(process.env);
  return fetch(`https://${env.APP_HOST}/api/status`, { headers: { "x-client": env["APP_CLIENT"] } });
}'''


def test_a_field_named_in_the_code_of_a_parsed_environment_is_not_the_whole_environment(tmp_path: Path) -> None:
    """env.APP_HOST and env["APP_CLIENT"], read from parseEnv(process.env), go into a request: no R04"""

    result = javascript_server(tmp_path, PARSED_ENVIRONMENT)
    assert environment_flows(result) == []
    assert "R04" not in [alert.rule for alert in result.verdict.alerts]


def test_a_field_read_in_a_called_function_is_not_the_whole_environment(tmp_path: Path) -> None:
    """The parsed environment is given to a function that reads one named field for the URL: no R04"""

    body = PARSED_ENVIRONMENT.replace(
        "return fetch(`https://${env.APP_HOST}/api/status`, { headers: { \"x-client\": env[\"APP_CLIENT\"] } });",
        "return ping(env);",
    )
    body += "\n\nfunction ping(config) {\n  return fetch(`https://${config.APP_HOST}/api/status`);\n}"
    result = javascript_server(tmp_path, body)
    assert environment_flows(result) == []


def test_a_python_field_named_in_the_code_of_a_copied_environment_is_one_variable(tmp_path: Path) -> None:
    """config = dict(os.environ), then config["APP_HOST"] and config.get("APP_TOKEN"): no R04"""

    body = '''def check() -> str:
    config = dict(os.environ)
    url = f"https://{config['APP_HOST']}/status"
    return requests.get(url, headers={"Authorization": config.get("APP_TOKEN", "")}).text'''
    result = python_server(tmp_path, body)
    assert environment_flows(result) == []
    assert "R04" not in [alert.rule for alert in result.verdict.alerts]


def test_the_positive_fixture_of_r04_still_fires(fixtures: Path) -> None:
    """engine/tests/fixtures/rules/R04/positive sends the whole environment: R04 stays red"""

    result = analyze_directory(fixtures / "rules" / "R04" / "positive")
    assert "R04" in [alert.rule for alert in result.verdict.alerts]


@pytest.mark.parametrize(
    "call",
    [
        'net.createConnection("/tmp/app.sock")',
        "net.connect(8080)",
        'net.connect({ path: "/tmp/app.sock" })',
        'net.connect({ host: "127.0.0.1", port: 8080 })',
        'net.connect(8080, "localhost")',
        'net.connect("/tmp/app.sock", () => {})',
    ],
)
def test_a_local_javascript_connection_is_not_internet(tmp_path: Path, call: str) -> None:
    """A socket path or a port alone, or a local host, reaches this computer only: no Internet lamp, no O01"""

    result = javascript_server(tmp_path, f"async function check() {{\n  return {call};\n}}")
    assert Capability.NETWORK not in capabilities(result)
    assert Capability.LOCAL_CONNECTION in capabilities(result)
    assert lamp(result, LampId.INTERNET) is LampState.OFF
    assert result.servers[0].network_not_followed == []
    assert result.verdict.color.value == "green"


@pytest.mark.parametrize("call", ['net.connect(443, "api.example.com")', 'net.connect({ host: "api.example.com", port: 443 })'])
def test_a_remote_javascript_connection_is_internet(tmp_path: Path, call: str) -> None:
    """A host that is not this computer is the Internet"""

    result = javascript_server(tmp_path, f"async function check() {{\n  return {call};\n}}")
    assert Capability.NETWORK in capabilities(result)
    assert lamp(result, LampId.INTERNET) is LampState.ON


def docker_alerts(result: AnalysisResult) -> list[object]:
    """Return the O08 alerts about the Docker socket"""

    return [alert for alert in result.verdict.alerts if alert.rule == "O08" and alert.detail == "docker_socket"]


def test_a_connection_to_the_docker_socket_can_control_docker(tmp_path: Path) -> None:
    """net.connect to /var/run/docker.sock: O08 says it can control Docker and lights the commands lamp"""

    result = javascript_server(tmp_path, 'async function check() {\n  return net.connect("/var/run/docker.sock");\n}')
    assert Capability.DOCKER_SOCKET in capabilities(result)
    [alert] = docker_alerts(result)
    assert alert.title == "rule.O08.docker.plain_title"
    assert result.verdict.title is not None and result.verdict.title.code == "rule.O08.docker.plain_title"
    assert lamp(result, LampId.COMMANDS) is LampState.ON
    assert lamp(result, LampId.INTERNET) is LampState.OFF


UNIX_SOCKET = '''def check() -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect("{path}")
        return client.recv(1024).decode()'''


def test_a_python_unix_socket_is_not_internet(tmp_path: Path) -> None:
    """socket.socket(socket.AF_UNIX) talks to this computer only"""

    result = python_server(tmp_path, UNIX_SOCKET.replace("{path}", "/tmp/app.sock"))
    assert Capability.NETWORK not in capabilities(result)
    assert lamp(result, LampId.INTERNET) is LampState.OFF
    assert result.servers[0].network_not_followed == []


def test_a_python_unix_socket_to_docker_can_control_docker(tmp_path: Path) -> None:
    """A Unix socket connected to docker.sock gives O08 Docker and lights the commands lamp"""

    result = python_server(tmp_path, UNIX_SOCKET.replace("{path}", "/var/run/docker.sock"))
    assert docker_alerts(result)
    assert lamp(result, LampId.COMMANDS) is LampState.ON
    assert lamp(result, LampId.INTERNET) is LampState.OFF


def test_a_python_internet_socket_is_still_internet(tmp_path: Path) -> None:
    """socket.socket() with the default family reaches the network"""

    body = UNIX_SOCKET.replace("socket.AF_UNIX, socket.SOCK_STREAM", "").replace('"{path}"', '("api.example.com", 443)')
    result = python_server(tmp_path, body)
    assert Capability.NETWORK in capabilities(result)
    assert lamp(result, LampId.INTERNET) is LampState.ON
