"""Raw results of one analyzed file, with byte offsets not yet turned into lines"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mcplain.adapters.common import SourceText, TextValue
from mcplain.capabilities import Capability
from mcplain.models import AnnotationValue, DeclarationKind, ToolParameter, TrackingGap, UrlKind

if TYPE_CHECKING:
    from mcplain.adapters.dataflow import FlowFunction


@dataclass(frozen=True)
class PackageContext:
    """Class that lists the files of the analyzed package for import resolution"""

    files: frozenset[str]
    modules: dict[str, str] = field(default_factory=dict)


@dataclass
class RawFinding:
    """Class that holds a capability seen at a byte offset"""

    capability: Capability
    offset: int
    function: str | None = None
    detail: str | None = None
    url_kind: UrlKind | None = None
    url_host: str | None = None
    sends: bool | None = None


@dataclass(frozen=True)
class RawCall:
    """Class that holds a call or a function reference, by name, optional target file and dispatch key"""

    offset: int
    name: str
    file: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class RawFunction:
    """Class that holds a named function, its range and the scope where its name is visible"""

    name: str
    start: int
    end: int
    scope_start: int
    scope_end: int
    module_level: bool
    overload: bool = False


@dataclass(frozen=True)
class RawGap:
    """Class that holds a call the call graph cannot follow, and why"""

    offset: int
    gap: TrackingGap


@dataclass(frozen=True)
class RawHandler:
    """Class that holds a low-level tools/call handler, inline or given by name"""

    start: int = 0
    end: int = 0
    reference: RawCall | None = None


@dataclass(frozen=True)
class RawBlock:
    """Class that holds a branch that runs when the tool name equals a literal"""

    literal: str
    start: int
    end: int


@dataclass
class RawTool:
    """Class that holds a tool declaration before positions are resolved"""

    name: str
    description: TextValue
    offset: int
    declaration: DeclarationKind
    name_is_dynamic: bool = False
    parameters: list[ToolParameter] = field(default_factory=list)
    parameters_are_dynamic: bool = False
    bodies: list[tuple[int, int]] = field(default_factory=list)
    entries: list[RawCall] = field(default_factory=list)
    text_ranges: list[tuple[int, int]] = field(default_factory=list)
    title: TextValue | None = None
    annotations: dict[str, AnnotationValue] = field(default_factory=dict)
    annotations_are_dynamic: bool = False
    description_range: tuple[int, int] | None = None


@dataclass
class RawString:
    """Class that holds one decoded string literal"""

    value: TextValue
    offset: int
    sensitive: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RawCopy:
    """Class that holds an e-mail address written as a cc or bcc recipient"""

    offset: int
    field: str
    address: str


@dataclass
class FileReport:
    """Class that holds everything an adapter found in one file"""

    path: str
    source: SourceText
    findings: list[RawFinding] = field(default_factory=list)
    tools: list[RawTool] = field(default_factory=list)
    strings: list[RawString] = field(default_factory=list)
    functions: list[RawFunction] = field(default_factory=list)
    function_ranges: list[tuple[int, int]] = field(default_factory=list)
    calls: list[RawCall] = field(default_factory=list)
    method_calls: list[RawCall] = field(default_factory=list)
    gaps: list[RawGap] = field(default_factory=list)
    call_handlers: list[RawHandler] = field(default_factory=list)
    dispatch_blocks: list[RawBlock] = field(default_factory=list)
    imported_files: list[str] = field(default_factory=list)
    reexports: dict[str, tuple[str, str]] = field(default_factory=dict)
    star_exports: list[str] = field(default_factory=list)
    default_export: str | None = None
    error_offset: int | None = None
    flow_functions: list["FlowFunction"] = field(default_factory=list)
    comments: list[tuple[int, str]] = field(default_factory=list)
    copies: list[RawCopy] = field(default_factory=list)
