"""Pydantic models shared by every MCPlain module, all serializable to JSON"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from mcplain.capabilities import Capability, PathKind
from mcplain.flows import FlowSinkKind, FlowSourceKind


class InputKind(StrEnum):
    """Class that lists the kinds of input MCPlain accepts"""

    GITHUB_REPO = "github_repo"
    GITHUB_SUBDIR = "github_subdir"
    NPM = "npm"
    PYPI = "pypi"


class InputSpec(BaseModel):
    """Class that describes a validated user input"""

    kind: InputKind
    owner: str | None = None
    repo: str | None = None
    ref: str | None = None
    subdir: str | None = None
    package: str | None = None
    version: str | None = None
    tree_path: str | None = None
    ignored_arguments: list[str] = Field(default_factory=list)


class SourceKind(StrEnum):
    """Class that lists where analyzed code can come from"""

    GITHUB = "github"
    NPM = "npm"
    PYPI = "pypi"


class SourceOrigin(StrEnum):
    """Class that tells whether the published package or the GitHub code was analyzed"""

    PUBLISHED_PACKAGE = "published_package"
    GITHUB_CODE = "github_code"


class AnalyzedSource(BaseModel):
    """Class that records exactly what was downloaded and analyzed"""

    kind: SourceKind
    name: str
    version: str | None = None
    requested_version: str | None = None
    revision: str | None = None
    reference: str | None = None
    subdir: str | None = None
    integrity: str | None = None
    url: str
    artifact: str
    origin: SourceOrigin
    reason: str
    repository: str | None = None


class LocationKind(StrEnum):
    """Class that tells what role a file plays in the project"""

    SERVER_CODE = "server_code"
    TEST_OR_EXAMPLE = "test_or_example"
    BUILD_SCRIPT = "build_script"


class UrlKind(StrEnum):
    """Class that tells how the URL of a network call is known"""

    LITERAL = "literal"
    DYNAMIC = "dynamic"
    UNKNOWN = "unknown"


class CallStep(BaseModel):
    """Class that describes one function on the path from a tool to a finding"""

    function: str
    file: str
    line: int


class TrackingGap(StrEnum):
    """Class that lists why the call graph could not follow every call of a tool"""

    DICT_CALL = "dict_call"
    DYNAMIC_ATTRIBUTE = "dynamic_attribute"
    UNKNOWN_TYPE = "unknown_type"
    AMBIGUOUS = "ambiguous"
    MAX_DEPTH = "max_depth"


class OutsideKind(StrEnum):
    """Class that tells when server code outside the tools runs"""

    STARTUP = "startup"
    INSTALL = "install"
    NEVER_CALLED = "never_called"


class Finding(BaseModel):
    """Class that describes one capability seen at one place in the code"""

    capability: Capability
    file: str
    line: int
    column: int
    snippet: str
    function: str | None = None
    location_kind: LocationKind
    detail: str | None = None
    call_chain: list[CallStep] = Field(default_factory=list)
    shared_by_tools: bool = False
    outside: OutsideKind | None = None
    url_kind: UrlKind | None = None
    url_host: str | None = None
    sends: bool | None = None


class FlowPoint(BaseModel):
    """Class that locates one end of a data flow"""

    file: str
    line: int
    function: str | None = None
    snippet: str = ""


class Flow(BaseModel):
    """Class that describes a value that goes from a source to a sink, with the functions it crosses"""

    source: FlowSourceKind
    source_detail: str = ""
    path_kinds: list[PathKind] = Field(default_factory=list)
    source_point: FlowPoint
    sink: FlowSinkKind
    sink_role: str
    sink_detail: str = ""
    sink_point: FlowPoint
    steps: list[CallStep] = Field(default_factory=list)
    pasted: bool = False
    decoded: bool = False
    written_file: bool = False
    tool: str | None = None
    shared_by_tools: bool = False
    outside: OutsideKind | None = None
    location_kind: LocationKind


class DeclarationKind(StrEnum):
    """Class that lists the ways a tool can be declared"""

    DECORATOR = "decorator"
    ADD_TOOL = "add_tool"
    FROM_FUNCTION = "from_function"
    LOW_LEVEL = "low_level"
    SERVER_TOOL = "server_tool"
    REGISTER_TOOL = "register_tool"
    ADD_TOOL_OBJECT = "add_tool_object"
    TOOL_CLASS = "tool_class"


AnnotationValue = bool | Literal["computed"]


class ToolParameter(BaseModel):
    """Class that describes one parameter of a tool"""

    name: str
    type: str | None = None
    description: str | None = None


class Tool(BaseModel):
    """Class that describes one tool declared by the server"""

    name: str
    name_is_dynamic: bool = False
    description: str
    description_is_dynamic: bool
    parameters: list[ToolParameter] = Field(default_factory=list)
    parameters_are_dynamic: bool = False
    file: str
    line: int
    declaration: DeclarationKind
    location_kind: LocationKind
    title: str | None = None
    title_is_dynamic: bool = False
    annotations: dict[str, AnnotationValue] = Field(default_factory=dict)
    annotations_are_dynamic: bool = False
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[TrackingGap] = Field(default_factory=list)


class DomainRef(BaseModel):
    """Class that records a literal URL and its domain"""

    domain: str
    url: str
    file: str
    line: int
    location_kind: LocationKind
    tool: str | None = None


class SensitivePathRef(BaseModel):
    """Class that records a literal mention of a sensitive path"""

    category: str
    kinds: list[PathKind] = Field(default_factory=list)
    match: str
    file: str
    line: int
    location_kind: LocationKind
    tool: str | None = None


class InstallScript(BaseModel):
    """Class that records code that runs when the package is installed"""

    kind: str
    file: str
    line: int
    command: str
    downloads: bool = False


class TextMatchKind(StrEnum):
    """Class that lists the kinds of suspicious text found in strings and comments"""

    PIPE_TO_SHELL = "pipe_to_shell"
    ANALYZER_TALK = "analyzer_talk"


class TextMatch(BaseModel):
    """Class that records a suspicious passage of a string or a comment"""

    kind: TextMatchKind
    file: str
    line: int
    quote: str
    in_comment: bool = False
    tool: str | None = None
    location_kind: LocationKind


class CopyRecipient(BaseModel):
    """Class that records an e-mail address written in the code as a cc or bcc recipient"""

    field: str
    address: str
    file: str
    line: int
    quote: str
    tool: str | None = None
    location_kind: LocationKind


class InvisibleCategory(StrEnum):
    """Class that lists the families of invisible Unicode characters"""

    ZERO_WIDTH = "zero_width"
    BIDI_CONTROL = "bidi_control"
    TAG = "tag"
    VARIATION_SELECTOR = "variation_selector"
    CONTROL = "control"


class InvisibleUnicode(BaseModel):
    """Class that records a run of invisible characters and where it is"""

    file: str
    line: int
    column: int
    category: InvisibleCategory
    codepoints: list[str]
    hidden_text: str | None = None
    in_description: bool = False
    in_source: bool = False
    tool: str | None = None
    location_kind: LocationKind


class ParseError(BaseModel):
    """Class that records a file that could not be parsed completely"""

    file: str
    line: int
    column: int
    location_kind: LocationKind = LocationKind.SERVER_CODE


class SkippedFile(BaseModel):
    """Class that records a file that was not analyzed and why"""

    file: str
    reason: str
    size: int
    location_kind: LocationKind = LocationKind.SERVER_CODE


class ServerAnalysis(BaseModel):
    """Class that holds everything found in one MCP server"""

    path: str
    name: str | None = None
    language: str
    sdk: str | None = None
    tools: list[Tool] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    domains: list[DomainRef] = Field(default_factory=list)
    sensitive_paths: list[SensitivePathRef] = Field(default_factory=list)
    install_scripts: list[InstallScript] = Field(default_factory=list)
    invisible_unicode: list[InvisibleUnicode] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    text_matches: list[TextMatch] = Field(default_factory=list)
    copy_recipients: list[CopyRecipient] = Field(default_factory=list)
    compiled_files: list[str] = Field(default_factory=list)
    minified_files: list[str] = Field(default_factory=list)
    parse_errors: list[ParseError] = Field(default_factory=list)
    skipped_files: list[SkippedFile] = Field(default_factory=list)
    files_analyzed: int = 0


class ServerCandidate(BaseModel):
    """Class that describes a folder that looks like an MCP server"""

    path: str
    language: str
    name: str | None = None
    sdk: str | None = None
    manifest: str | None = None


class VerdictColor(StrEnum):
    """Class that lists the verdict colors"""

    RED = "red"
    ORANGE = "orange"
    GREEN = "green"
    GRAY = "gray"


class AlertKind(StrEnum):
    """Class that tells whether an alert points to a suspicious use, a serious flaw or a power to be aware of"""

    SUSPICIOUS_USE = "suspicious_use"
    SERIOUS_FLAW = "serious_flaw"
    POWER_TO_KNOW = "power_to_know"


class Alert(BaseModel):
    """Class that describes one place where a rule fires"""

    rule: str
    color: VerdictColor
    kind: AlertKind
    tool: str | None = None
    shared_by_tools: bool = False
    outside: OutsideKind | None = None
    file: str | None = None
    line: int | None = None
    function: str | None = None
    source: FlowPoint | None = None
    steps: list[CallStep] = Field(default_factory=list)
    quote: str | None = None
    detail: str | None = None


class Verdict(BaseModel):
    """Class that holds the verdict color, the alerts and the codes that explain it"""

    color: VerdictColor
    alerts: list[Alert] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    rules_version: str = ""
    rules_count: int = 0
    contacted_domains: list[str] = Field(default_factory=list)


class ReputationStatus(StrEnum):
    """Class that tells whether the reputation of the packages could be checked"""

    CHECKED = "checked"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"


class MaliciousReport(BaseModel):
    """Class that holds one OSV malicious package identifier; the text of the alert is never kept"""

    id: str
    all_versions: bool = False


class PackageReputation(BaseModel):
    """Class that holds the malicious package reports of the analyzed package or of a direct dependency"""

    name: str
    ecosystem: str
    version: str | None = None
    dependency: bool = False
    malicious: list[MaliciousReport] = Field(default_factory=list)


class Reputation(BaseModel):
    """Class that holds what OSV.dev says about the analyzed package and its direct dependencies"""

    status: ReputationStatus
    queried: int = 0
    packages: list[PackageReputation] = Field(default_factory=list)


class AnalysisStatus(StrEnum):
    """Class that lists the possible outcomes of an analysis"""

    OK = "ok"
    MULTIPLE_SERVERS = "multiple_servers"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    COMPILED = "compiled"
    NOT_A_SERVER = "not_a_server"
    ERROR = "error"


class ErrorInfo(BaseModel):
    """Class that holds a translatable error code and its parameters"""

    code: str
    params: dict[str, str] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    """Class that holds the complete result of one analysis"""

    status: AnalysisStatus
    source: AnalyzedSource | None = None
    local_path: str | None = None
    reputation: Reputation | None = None
    ignored_arguments: list[str] = Field(default_factory=list)
    servers: list[ServerAnalysis] = Field(default_factory=list)
    available_servers: list[ServerCandidate] = Field(default_factory=list)
    available_servers_truncated: bool = False
    language: str | None = None
    compiled_files: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    error: ErrorInfo | None = None
    verdict: Verdict
