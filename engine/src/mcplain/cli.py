"""Command line interface: mcplain <input> [--json] [--lang en|fr] [--select <path>]"""

import argparse
import json
import sys
import unicodedata
from collections import defaultdict

from mcplain.adapters.common import TAG_BASE, hidden_tag_text, invisible_category
from mcplain.analyze import analyze_input
from mcplain.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    Finding,
    LocationKind,
    ServerAnalysis,
    SourceKind,
    Tool,
    UrlKind,
)

UNSAFE_CATEGORIES: frozenset[str] = frozenset({"Cc", "Cf", "Co", "Cs", "Zl", "Zp"})
TAG_LAST = TAG_BASE + 0x7F
EXAMPLES_PER_CAPABILITY = 3
EXAMPLES_PER_DOMAIN = 1
MAX_LISTED_ITEMS = 20
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INPUT_ERROR = 2
INPUT_ERROR_PREFIX = "input."
INDENT = "  "


def neutralize(text: str) -> str:
    """Make control, format and invisible characters visible so they cannot alter the terminal"""

    output: list[str] = []
    tags: list[str] = []
    for character in text:
        codepoint = ord(character)
        if TAG_BASE <= codepoint <= TAG_LAST:
            tags.append(character)
            continue
        if tags:
            output.append(_render_tags(tags))
            tags = []
        if character == "\t":
            output.append(" ")
        elif unicodedata.category(character) in UNSAFE_CATEGORIES or invisible_category(character) is not None:
            output.append(f"<U+{codepoint:04X}>")
        else:
            output.append(character)
    if tags:
        output.append(_render_tags(tags))
    return "".join(output)


def _render_tags(tags: list[str]) -> str:
    """Show a run of Unicode tag characters with the text they hide"""

    hidden = hidden_tag_text("".join(tags))
    if hidden is None:
        return "".join(f"<U+{ord(character):04X}>" for character in tags)
    return f'<tags:"{hidden}">'


def first_line(text: str) -> str:
    """Return the first non-empty line of a text"""

    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _requested_language(argv: list[str]) -> str:
    """Find --lang before parsing so that help texts use the right language"""

    for index, argument in enumerate(argv):
        if argument.startswith("--lang="):
            return argument.split("=", 1)[1]
        if argument == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
    return DEFAULT_LANGUAGE


def build_parser(t: Translator) -> argparse.ArgumentParser:
    """Build the argument parser with translated help texts"""

    parser = argparse.ArgumentParser(prog="mcplain", description=t("cli.help.description"))
    parser.add_argument("input", help=t("cli.help.input"))
    parser.add_argument("--json", action="store_true", help=t("cli.help.json"))
    parser.add_argument("--lang", choices=SUPPORTED_LANGUAGES, default=DEFAULT_LANGUAGE, help=t("cli.help.lang"))
    parser.add_argument("--select", metavar=t("cli.help.select_metavar"), help=t("cli.help.select"))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line tool and return its exit code"""

    arguments = list(sys.argv[1:])
    if argv is not None:
        arguments = list(argv)
    parser = build_parser(Translator(_requested_language(arguments)))
    options = parser.parse_args(arguments)
    t = Translator(options.lang)
    result = analyze_input(options.input, select=options.select)
    if options.json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    else:
        print(render(result, t))
    return exit_code(result)


def exit_code(result: AnalysisResult) -> int:
    """Return 2 for refused input, 1 for other errors and 0 otherwise"""

    if result.status is not AnalysisStatus.ERROR or result.error is None:
        return EXIT_OK
    if result.error.code.startswith(INPUT_ERROR_PREFIX):
        return EXIT_INPUT_ERROR
    return EXIT_ERROR


def render(result: AnalysisResult, t: Translator) -> str:
    """Build the human readable report"""

    lines = [t("cli.title")]
    if result.ignored_arguments:
        ignored = " ".join(_safe(argument) for argument in result.ignored_arguments)
        lines.append("")
        lines.append(f"{t('cli.ignored_arguments')}{t('cli.separator')}{ignored}")
    _render_source(result, t, lines)
    lines.append("")
    lines.append(f"{t('cli.status')}{t('cli.separator')}{t('status.' + result.status.value, language=_safe(result.language))}")
    if result.status is AnalysisStatus.ERROR and result.error is not None:
        params = {key: _safe(value) for key, value in result.error.params.items()}
        lines.append(f"{INDENT}{t(result.error.code, **params)}")
    for note in result.notes:
        lines.append(f"{INDENT}{t(note)}")
    if result.status is AnalysisStatus.MULTIPLE_SERVERS:
        _render_candidates(result, t, lines)
    if result.status is AnalysisStatus.COMPILED and result.compiled_files:
        _heading(lines, t("cli.limits.heading"))
        for path in result.compiled_files[:MAX_LISTED_ITEMS]:
            lines.append(f"{INDENT}- {t('cli.limits.compiled')}{t('cli.separator')}{_safe(path)}")
    for server in result.servers:
        _render_server(server, t, lines)
    _render_verdict(result, t, lines)
    return "\n".join(lines)


def _safe(value: object) -> str:
    """Neutralize any value coming from analyzed code or downloaded metadata"""

    if value is None:
        return ""
    return neutralize(str(value))


def _heading(lines: list[str], title: str) -> None:
    """Append a section heading"""

    lines.append("")
    lines.append(f"== {title} ==")


def _render_source(result: AnalysisResult, t: Translator, lines: list[str]) -> None:
    """Describe what was downloaded and why"""

    source = result.source
    if source is None:
        return
    _heading(lines, t("cli.source.heading"))
    lines.append(f"{INDENT}{t('cli.source.kind')}{t('cli.separator')}{t('source_kind.' + source.kind.value)}")
    lines.append(f"{INDENT}{t('cli.source.name')}{t('cli.separator')}{_safe(source.name)}")
    if source.version:
        version = _safe(source.version)
        if source.requested_version:
            version = t("cli.source.version_requested", version=version, requested=_safe(source.requested_version))
        lines.append(f"{INDENT}{t('cli.source.version')}{t('cli.separator')}{version}")
    if source.reference:
        lines.append(f"{INDENT}{t('cli.source.reference')}{t('cli.separator')}{_safe(source.reference)}")
    if source.revision and not source.repository:
        lines.append(f"{INDENT}{t('cli.source.revision')}{t('cli.separator')}{_safe(source.revision)}")
    if source.subdir:
        lines.append(f"{INDENT}{t('cli.source.subdir')}{t('cli.separator')}{_safe(source.subdir)}")
    if source.repository:
        linked = t("cli.source.linked", repository=_safe(source.repository), revision=_safe(source.revision))
        lines.append(f"{INDENT}{t('cli.source.repository')}{t('cli.separator')}{linked}")
    if source.integrity:
        label = t("cli.source.integrity_verified")
        if source.kind is SourceKind.GITHUB:
            label = t("cli.source.integrity_archive")
        lines.append(f"{INDENT}{t('cli.source.integrity')}{t('cli.separator')}{_safe(source.integrity)} ({label})")
    lines.append(f"{INDENT}{t('cli.source.artifact')}{t('cli.separator')}{t('artifact.' + source.artifact)}")
    lines.append(f"{INDENT}{t('cli.source.url')}{t('cli.separator')}{_safe(source.url)}")
    lines.append(f"{INDENT}{t('cli.source.origin')}{t('cli.separator')}{t('origin.' + source.origin.value)}")
    lines.append(f"{INDENT}{t('cli.source.why')}{t('cli.separator')}{t(source.reason)}")


def _render_candidates(result: AnalysisResult, t: Translator, lines: list[str]) -> None:
    """List the servers found when there is more than one"""

    _heading(lines, t("cli.candidates.heading", count=len(result.available_servers)))
    for candidate in result.available_servers:
        details = [candidate.language]
        if candidate.name:
            details.append(_safe(candidate.name))
        lines.append(f"{INDENT}- {_safe(candidate.path)} ({', '.join(details)})")
    if result.available_servers_truncated:
        lines.append(f"{INDENT}{t('cli.candidates.truncated')}")
    lines.append(f"{INDENT}{t('cli.candidates.hint')}")


def _render_server(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """Describe one analyzed server"""

    _heading(lines, t("cli.server.heading", path=_safe(server.path), language=server.language))
    if server.name:
        lines.append(f"{INDENT}{t('cli.server.name')}{t('cli.separator')}{_safe(server.name)}")
    if server.sdk:
        lines.append(f"{INDENT}{t('cli.server.sdk')}{t('cli.separator')}{_safe(server.sdk)}")
    lines.append(f"{INDENT}{t('cli.server.files', count=server.files_analyzed)}")
    _render_tools(server, t, lines)
    counted = [finding for finding in server.findings if finding.location_kind is LocationKind.SERVER_CODE]
    others = [finding for finding in server.findings if finding.location_kind is not LocationKind.SERVER_CODE]
    for tool in server.tools:
        if tool.location_kind is not LocationKind.SERVER_CODE:
            others.extend(tool.findings)
    shared = [finding for finding in counted if finding.shared_by_tools]
    if shared:
        _heading(lines, t("cli.shared.heading"))
        _render_findings(shared, t, lines)
    _heading(lines, t("cli.server_caps.heading"))
    _render_findings([finding for finding in counted if not finding.shared_by_tools], t, lines)
    if others:
        _heading(lines, t("cli.not_counted.heading"))
        _render_findings(others, t, lines)
    _render_domains(server, t, lines)
    _render_sensitive(server, t, lines)
    _render_install(server, t, lines)
    _render_invisible(server, t, lines)
    _render_limits(server, t, lines)


def _render_tools(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """Describe each tool and the capabilities found in its body"""

    _heading(lines, t("cli.tools.heading", count=len(server.tools)))
    if not server.tools:
        lines.append(f"{INDENT}{t('cli.tools.none')}")
        return
    for tool in server.tools:
        lines.append(f"{INDENT}- {_safe(tool.name)}  {_safe(tool.file)}:{tool.line}{_tool_marks(tool, t)}")
        lines.append(f"{INDENT * 3}{_tool_description(tool, t)}")
        announced = _announced(tool, t)
        if announced:
            lines.append(f"{INDENT * 3}{t('cli.tool.announces')}{t('cli.separator')}{announced}")
        if tool.parameters:
            names = ", ".join(_safe(parameter.name) for parameter in tool.parameters)
            lines.append(f"{INDENT * 3}{t('cli.tool.parameters')}{t('cli.separator')}{names}")
        _render_tool_findings(tool, t, lines)


def _render_tool_findings(tool: Tool, t: Translator, lines: list[str]) -> None:
    """Show each capability of a tool once, with how the tool reaches it"""

    if not tool.findings:
        lines.append(f"{INDENT * 3}{t('cli.tool.capabilities')}{t('cli.separator')}{t('cli.tool.no_capabilities')}")
        return
    lines.append(f"{INDENT * 3}{t('cli.tool.capabilities')}{t('cli.separator')}")
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in tool.findings:
        grouped[finding.capability.value].append(finding)
    for capability in sorted(grouped):
        items = _representative(grouped[capability])
        text = f"{INDENT * 4}- {capability} ({t('capability.' + capability)}){t('cli.separator')}{_reach(items[0], t)}"
        if len(items) > 1:
            text = f"{text}, {t('cli.others', count=len(items) - 1)}"
        lines.append(text)


def _reach(finding: Finding, t: Translator) -> str:
    """Say whether a finding is in the tool itself or reached through other functions"""

    place = f"{_safe(finding.file)}:{finding.line}"
    if not finding.call_chain:
        text = t("cli.directly", place=place)
    else:
        chain = " -> ".join(_safe(step.function) for step in finding.call_chain)
        text = t("cli.via", chain=chain, place=place)
    if finding.url_kind is not None:
        text = f"{text}, {t('cli.url_kind.' + finding.url_kind.value)}"
    return text


def _representative(findings: list[Finding]) -> list[Finding]:
    """Order findings so the nearest one with a readable URL comes first"""

    def rank(finding: Finding) -> tuple[int, int]:
        """Prefer short call chains, then findings whose URL kind is known"""

        unknown = 0
        if finding.url_kind is UrlKind.UNKNOWN:
            unknown = 1
        return len(finding.call_chain), unknown

    return sorted(findings, key=rank)


def _announced(tool: Tool, t: Translator) -> str:
    """Summarize the title and behavior hints declared by the author"""

    parts = []
    if tool.title is not None:
        title = f'"{_safe(tool.title)}"'
        if tool.title_is_dynamic:
            title = t("cli.value.computed")
        parts.append(f"{t('cli.tool.title')} {title}")
    for key, value in tool.annotations.items():
        parts.append(f"{t('annotation.' + key)}{t('cli.separator')}{t('cli.value.' + str(value).lower())}")
    if tool.annotations_are_dynamic:
        parts.append(t("cli.tool.annotations_dynamic"))
    return "; ".join(parts)


def _tool_marks(tool: Tool, t: Translator) -> str:
    """Return the markers shown after a tool location"""

    marks = [t("declaration." + tool.declaration.value)]
    if tool.location_kind is not LocationKind.SERVER_CODE:
        marks.append(t("location." + tool.location_kind.value))
    if tool.name_is_dynamic:
        marks.append(t("cli.tool.dynamic_name"))
    return "  [" + ", ".join(marks) + "]"


def _tool_description(tool: Tool, t: Translator) -> str:
    """Return the first line of a tool description, made safe for the terminal"""

    line = first_line(tool.description)
    if not line and tool.description_is_dynamic:
        return t("cli.tool.description_dynamic")
    if not line:
        return t("cli.tool.no_description")
    text = f'"{_safe(line)}"'
    if tool.description_is_dynamic:
        text = f"{text} {t('cli.tool.description_partly_dynamic')}"
    return text


def _render_findings(findings: list[Finding], t: Translator, lines: list[str]) -> None:
    """Group findings by capability and show a few examples of each"""

    if not findings:
        lines.append(f"{INDENT}{t('cli.none')}")
        return
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.capability.value].append(finding)
    for capability in sorted(grouped):
        items = grouped[capability]
        label = f"{capability} ({t('capability.' + capability)})"
        lines.append(f"{INDENT}- {label}{t('cli.separator')}{t('cli.places', count=len(items))}")
        for finding in items[:EXAMPLES_PER_CAPABILITY]:
            where = f"{_safe(finding.file)}:{finding.line}"
            if finding.function:
                where = f"{where} {t('cli.in_function', name=_safe(finding.function))}"
            snippet = _safe(finding.snippet)
            if finding.url_kind is not None:
                snippet = f"{snippet}  [{t('cli.url_kind.' + finding.url_kind.value)}]"
            lines.append(f"{INDENT * 3}{where}: {snippet}")


def _render_domains(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """List the domains of literal URLs"""

    _heading(lines, t("cli.domains.heading"))
    counted = [item for item in server.domains if item.location_kind is LocationKind.SERVER_CODE]
    if not counted:
        lines.append(f"{INDENT}{t('cli.none')}")
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in counted:
        where = f"{_safe(item.file)}:{item.line}"
        if item.tool:
            where = f"{where} {t('cli.in_tool', name=_safe(item.tool))}"
        grouped[item.domain].append(where)
    for index, domain in enumerate(sorted(grouped)):
        if index >= MAX_LISTED_ITEMS:
            lines.append(f"{INDENT}{t('cli.more', count=len(grouped) - MAX_LISTED_ITEMS)}")
            break
        places = grouped[domain]
        lines.append(f"{INDENT}- {_safe(domain)} ({t('cli.places', count=len(places))}), {places[0]}")
    ignored = len(server.domains) - len(counted)
    if ignored:
        lines.append(f"{INDENT}{t('cli.domains.not_counted', count=ignored)}")


def _render_sensitive(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """List literal mentions of sensitive paths"""

    _heading(lines, t("cli.sensitive.heading"))
    if not server.sensitive_paths:
        lines.append(f"{INDENT}{t('cli.none')}")
    for item in server.sensitive_paths[:MAX_LISTED_ITEMS]:
        where = f"{_safe(item.file)}:{item.line}"
        if item.tool:
            where = f"{where} {t('cli.in_tool', name=_safe(item.tool))}"
        if item.location_kind is not LocationKind.SERVER_CODE:
            where = f"{where} [{t('location.' + item.location_kind.value)}]"
        lines.append(f"{INDENT}- {t('sensitive.' + item.category)}{t('cli.separator')}\"{_safe(item.match)}\" {where}")
    if len(server.sensitive_paths) > MAX_LISTED_ITEMS:
        lines.append(f"{INDENT}{t('cli.more', count=len(server.sensitive_paths) - MAX_LISTED_ITEMS)}")


def _render_install(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """List install-time scripts"""

    _heading(lines, t("cli.install.heading"))
    if not server.install_scripts:
        lines.append(f"{INDENT}{t('cli.none')}")
    for script in server.install_scripts:
        lines.append(
            f"{INDENT}- {t('install.' + script.kind)} {_safe(script.file)}:{script.line}: {_safe(script.command)}"
        )


def _render_invisible(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """List invisible Unicode characters with their positions"""

    _heading(lines, t("cli.invisible.heading"))
    if not server.invisible_unicode:
        lines.append(f"{INDENT}{t('cli.none')}")
    for item in server.invisible_unicode[:MAX_LISTED_ITEMS]:
        codepoints = " ".join(item.codepoints[:8])
        if len(item.codepoints) > 8:
            codepoints = f"{codepoints} ... ({len(item.codepoints)})"
        text = f"{INDENT}- {_safe(item.file)}:{item.line}:{item.column} {t('invisible.' + item.category.value)} {codepoints}"
        if item.hidden_text:
            text = f'{text} {t("cli.invisible.hidden")}{t("cli.separator")}"{_safe(item.hidden_text)}"'
        if item.in_description and item.tool:
            text = f"{text} {t('cli.invisible.in_description', name=_safe(item.tool))}"
        elif item.tool:
            text = f"{text} {t('cli.in_tool', name=_safe(item.tool))}"
        lines.append(text)
    if len(server.invisible_unicode) > MAX_LISTED_ITEMS:
        lines.append(f"{INDENT}{t('cli.more', count=len(server.invisible_unicode) - MAX_LISTED_ITEMS)}")


def _render_limits(server: ServerAnalysis, t: Translator, lines: list[str]) -> None:
    """List what could not be fully read"""

    entries = []
    for path in server.compiled_files[:MAX_LISTED_ITEMS]:
        entries.append(f"{t('cli.limits.compiled')}{t('cli.separator')}{_safe(path)}")
    for path in server.minified_files[:MAX_LISTED_ITEMS]:
        entries.append(f"{t('cli.limits.minified')}{t('cli.separator')}{_safe(path)}")
    for error in server.parse_errors[:MAX_LISTED_ITEMS]:
        entries.append(f"{t('cli.limits.parse_error')}{t('cli.separator')}{_safe(error.file)}:{error.line}:{error.column}")
    for skipped in server.skipped_files[:MAX_LISTED_ITEMS]:
        entries.append(f"{t('cli.limits.skipped')}{t('cli.separator')}{_safe(skipped.file)} ({t('skipped.' + skipped.reason)})")
    if not entries:
        return
    _heading(lines, t("cli.limits.heading"))
    for entry in entries:
        lines.append(f"{INDENT}- {entry}")


def _render_verdict(result: AnalysisResult, t: Translator, lines: list[str]) -> None:
    """Show the verdict, its reasons and its limits"""

    verdict = result.verdict
    _heading(lines, t("cli.verdict.heading"))
    color = t("color." + verdict.color.value)
    if verdict.provisional:
        color = f"{color} ({t('cli.verdict.provisional')})"
    lines.append(f"{INDENT}{color}")
    for reason in verdict.reasons:
        lines.append(f"{INDENT}- {t('reason.' + reason)}")
    if verdict.provisional:
        lines.append(f"{INDENT}{t('cli.verdict.provisional_note')}")
    lines.append(f"{INDENT}{t('cli.verdict.disclaimer')}")


if __name__ == "__main__":
    sys.exit(main())
