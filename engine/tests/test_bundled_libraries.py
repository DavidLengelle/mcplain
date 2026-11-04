"""Tests for bundled libraries: their never-called code counts neither for the lamps nor for O08 (decision of 3 November 2026)"""

import inspect
from pathlib import Path

from mcplain.adapters.bundles import package_of
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.lamps import LampId, LampState
from mcplain.models import AnalysisResult, Finding, OutsideKind
from mcplain.rules import red

MANIFEST = '{"name": "bundled", "bin": {"bundled": "dist/index.js"}, "dependencies": {"@modelcontextprotocol/sdk": "^1"}}'
HEAD = """var __commonJS = (cb, mod) => () => (mod || cb((mod = { exports: {} }).exports, mod), mod.exports);

"""
LIBRARY = """// ../../node_modules/depd/index.js
var require_depd = __commonJS((exports, module) => {
  function wrapfunction(fn, message) {
    var deprecatedfn = new Function("fn", "return fn");
    return deprecatedfn(fn);
  }
  module.exports = wrapfunction;
});

"""
SERVER = """// src/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
var server = new McpServer({ name: "bundled", version: "1.0.0" });
server.registerTool("hello", { description: "Say hello" }, async () => {
  return { content: [{ type: "text", text: "hello" }] };
});
"""


def analyze_bundle(tmp_path: Path, bundle: str) -> AnalysisResult:
    """Write one bundled server and analyze it"""

    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    (tmp_path / "dist").mkdir(exist_ok=True)
    (tmp_path / "dist" / "index.js").write_text(bundle, encoding="utf-8")
    return analyze_directory(tmp_path)


def dynamic_code(result: AnalysisResult) -> list[Finding]:
    """Return the dynamic code findings of the server"""

    return [finding for finding in result.servers[0].findings if finding.capability is Capability.DYNAMIC_CODE]


def commands_lamp(result: AnalysisResult) -> LampState:
    """Return the state of the commands lamp of the server"""

    return {lamp.id: lamp.state for lamp in result.servers[0].lamps}[LampId.COMMANDS]


def o08_count(result: AnalysisResult) -> int:
    """Count the O08 alerts of a result"""

    return len([alert for alert in result.verdict.alerts if alert.rule == "O08"])


def test_never_called_code_of_a_bundled_library_counts_neither_for_lamps_nor_o08(tmp_path: Path) -> None:
    """new Function in a depd function that nothing calls: marked, the lamp stays off, no O08"""

    result = analyze_bundle(tmp_path, HEAD + LIBRARY + SERVER)
    [finding] = dynamic_code(result)
    assert (finding.outside, finding.unused_library) == (OutsideKind.NEVER_CALLED, "depd")
    assert commands_lamp(result) is LampState.OFF
    assert o08_count(result) == 0


def test_the_same_code_outside_a_library_region_still_counts(tmp_path: Path) -> None:
    """Without the node_modules comment, the same never-called function is the server's own code: it counts"""

    result = analyze_bundle(tmp_path, HEAD + LIBRARY.replace("../../node_modules/depd/index.js", "src/depd.ts") + SERVER)
    [finding] = dynamic_code(result)
    assert finding.unused_library is None
    assert commands_lamp(result) is LampState.ON
    assert o08_count(result) == 1


def test_code_run_when_the_module_loads_still_counts(tmp_path: Path) -> None:
    """A function called by the module body runs at load time: it counts"""

    loaded = LIBRARY.replace("  module.exports = wrapfunction;", "  module.exports = wrapfunction(String, 'x');")
    result = analyze_bundle(tmp_path, HEAD + loaded + SERVER)
    [finding] = dynamic_code(result)
    assert finding.unused_library is None
    assert commands_lamp(result) is LampState.ON


def test_code_written_directly_in_the_module_body_still_counts(tmp_path: Path) -> None:
    """new Function written in the module wrapper itself runs at load time: it counts"""

    body = LIBRARY.replace("  module.exports = wrapfunction;", '  module.exports = new Function("fn", "return fn");')
    result = analyze_bundle(tmp_path, HEAD + body + SERVER)
    marks = {finding.line: finding.unused_library for finding in dynamic_code(result)}
    assert marks == {6: "depd", 9: None}
    assert commands_lamp(result) is LampState.ON
    assert o08_count(result) == 1


def test_a_library_function_reached_by_a_tool_counts(tmp_path: Path) -> None:
    """A tool that calls the library function reaches it: it counts"""

    called = SERVER.replace('text: "hello"', 'text: String(wrapfunction(String, "x"))').replace(
        "// src/index.ts\n", "// src/index.ts\nvar wrapfunction = require_depd();\n"
    )
    flat = LIBRARY.replace("var require_depd = __commonJS((exports, module) => {\n", "").replace(
        "  module.exports = wrapfunction;\n});\n", ""
    )
    result = analyze_bundle(tmp_path, HEAD + flat + called)
    [tool] = result.servers[0].tools
    assert [finding.capability for finding in tool.findings] == [Capability.DYNAMIC_CODE]
    assert all(finding.unused_library is None for finding in tool.findings)


def test_a_last_module_without_a_closing_marker_counts(tmp_path: Path) -> None:
    """When no module comment follows the library, its end is not known: in doubt, it counts"""

    result = analyze_bundle(tmp_path, HEAD + SERVER.replace("// src/index.ts\n", "") + "\n" + LIBRARY)
    [finding] = dynamic_code(result)
    assert finding.unused_library is None
    assert commands_lamp(result) is LampState.ON


def test_a_rolldown_region_is_recognized_and_an_unclosed_one_is_not(tmp_path: Path) -> None:
    """//#region with a node_modules path up to //#endregion is a library; without //#endregion it counts"""

    region = LIBRARY.replace("// ../../node_modules/depd/index.js", "//#region ../../node_modules/.pnpm/depd@2.0.0/node_modules/depd/index.js")
    closed = analyze_bundle(tmp_path, HEAD + region + "//#endregion\n" + SERVER)
    assert [finding.unused_library for finding in dynamic_code(closed)] == ["depd"]
    unclosed = analyze_bundle(tmp_path, HEAD + region + SERVER.replace("// src/index.ts\n", ""))
    assert [finding.unused_library for finding in dynamic_code(unclosed)] == [None]


def test_an_esbuild_object_wrapper_is_a_module_body(tmp_path: Path) -> None:
    """__commonJS({ "path"(exports, module) { ... } }) is also a module body"""

    wrapped = LIBRARY.replace(
        "var require_depd = __commonJS((exports, module) => {\n", 'var require_depd = __commonJS({\n "node_modules/depd/index.js"(exports, module) {\n'
    ).replace("  module.exports = wrapfunction;\n});\n", '  module.exports = new Function("fn", "return fn");\n }\n});\n')
    result = analyze_bundle(tmp_path, HEAD + wrapped + SERVER)
    assert sorted(str(finding.unused_library) for finding in dynamic_code(result)) == ["None", "depd"]


def test_package_names_from_module_paths() -> None:
    """The package is the folder after the last node_modules, with its scope"""

    assert package_of("../../node_modules/depd/index.js") == "depd"
    assert package_of("node_modules/@modelcontextprotocol/sdk/node_modules/ajv/dist/compile/index.js") == "ajv"
    assert package_of("../../node_modules/.pnpm/@vercel+oidc@3.0.0/node_modules/@vercel/oidc/dist/index.js") == "@vercel/oidc"
    assert package_of("src/index.ts") is None
    assert package_of("node_modules/index.js") is None


def test_red_rules_never_read_the_unused_library_mark() -> None:
    """A red rule counts everywhere, called or not: no red rule looks at the mark"""

    assert "unused_library" not in inspect.getsource(red)
