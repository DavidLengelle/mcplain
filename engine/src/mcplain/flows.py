"""Fixed tables of data flow sources, sinks and propagators, one set per language"""

from enum import StrEnum


class FlowSourceKind(StrEnum):
    """Class that lists where a tracked value comes from"""

    TOOL_PARAMETER = "tool_parameter"
    SENSITIVE_FILE = "sensitive_file"
    SENSITIVE_PATH = "sensitive_path"
    ENVIRONMENT = "environment"
    ENCODED_LITERAL = "encoded_literal"
    NETWORK_RESPONSE = "network_response"


class FlowSinkKind(StrEnum):
    """Class that lists where a tracked value can end up"""

    NETWORK = "network"
    SHELL = "shell"
    PROCESS = "process"
    CODE = "code"
    FILE_WRITE = "file_write"
    RUN_FILE = "run_file"
    TOOL_DESCRIPTION = "tool_description"


ROLE_DATA = "data"
ROLE_COMMAND = "command"
ROLE_PROGRAM = "program"
ROLE_ARGUMENTS = "arguments"
ROLE_CODE = "code"
ROLE_PATH = "path"
ROLE_CONTENT = "content"
ROLE_DESCRIPTION = "description"

RELEVANT_FLOWS: frozenset[tuple[FlowSourceKind, FlowSinkKind]] = frozenset(
    {
        (FlowSourceKind.SENSITIVE_FILE, FlowSinkKind.NETWORK),
        (FlowSourceKind.ENVIRONMENT, FlowSinkKind.NETWORK),
        (FlowSourceKind.ENCODED_LITERAL, FlowSinkKind.CODE),
        (FlowSourceKind.ENCODED_LITERAL, FlowSinkKind.SHELL),
        (FlowSourceKind.ENCODED_LITERAL, FlowSinkKind.PROCESS),
        (FlowSourceKind.ENCODED_LITERAL, FlowSinkKind.RUN_FILE),
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.CODE),
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.SHELL),
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.RUN_FILE),
        (FlowSourceKind.NETWORK_RESPONSE, FlowSinkKind.TOOL_DESCRIPTION),
        (FlowSourceKind.SENSITIVE_PATH, FlowSinkKind.FILE_WRITE),
        (FlowSourceKind.TOOL_PARAMETER, FlowSinkKind.SHELL),
        (FlowSourceKind.TOOL_PARAMETER, FlowSinkKind.CODE),
        (FlowSourceKind.TOOL_PARAMETER, FlowSinkKind.PROCESS),
    }
)
WRITTEN_FILE_SOURCES: frozenset[FlowSourceKind] = frozenset(
    {FlowSourceKind.NETWORK_RESPONSE, FlowSourceKind.ENCODED_LITERAL}
)

PYTHON_SHELL_CALLS: frozenset[str] = frozenset(
    {
        "os.system",
        "os.popen",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
        "asyncio.create_subprocess_shell",
        "commands.getoutput",
        "commands.getstatusoutput",
    }
)
PYTHON_SHELL_OPTION_CALLS: frozenset[str] = frozenset(
    {"subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.Popen"}
)
PYTHON_SHELL_KEYWORD = "shell"
PYTHON_COMMAND_KEYWORDS: tuple[str, ...] = ("args", "cmd", "command")
PYTHON_PROCESS_CALLS: dict[str, int] = {
    "os.execv": 0,
    "os.execve": 0,
    "os.execvp": 0,
    "os.execvpe": 0,
    "os.execl": 0,
    "os.execle": 0,
    "os.execlp": 0,
    "os.execlpe": 0,
    "os.spawnv": 1,
    "os.spawnve": 1,
    "os.spawnvp": 1,
    "os.spawnvpe": 1,
    "os.spawnl": 1,
    "os.spawnle": 1,
    "os.spawnlp": 1,
    "os.spawnlpe": 1,
    "os.posix_spawn": 0,
    "os.posix_spawnp": 0,
    "asyncio.create_subprocess_exec": 0,
    "pty.spawn": 0,
    "pexpect.spawn": 0,
    "pexpect.run": 0,
}
PYTHON_SHELL_METHODS: frozenset[str] = frozenset({"exec_command"})
PYTHON_CODE_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "builtins.eval",
        "builtins.exec",
        "builtins.compile",
        "importlib.import_module",
        "runpy.run_module",
        "pickle.load",
        "pickle.loads",
        "marshal.load",
        "marshal.loads",
        "dill.loads",
        "cloudpickle.loads",
    }
)
PYTHON_RUN_FILE_CALLS: frozenset[str] = frozenset({"runpy.run_path", "os.startfile", "os.chmod"})
PYTHON_RUN_FILE_METHODS: frozenset[str] = frozenset({"chmod"})
PYTHON_OPEN_CALLS: frozenset[str] = frozenset({"open", "io.open", "codecs.open", "aiofiles.open"})
PYTHON_COPY_CALLS: dict[str, int] = {
    "shutil.copy": 1,
    "shutil.copy2": 1,
    "shutil.copyfile": 1,
    "shutil.copytree": 1,
    "shutil.move": 1,
    "os.rename": 1,
    "os.renames": 1,
    "os.replace": 1,
    "os.symlink": 1,
    "os.link": 1,
}
PYTHON_PATH_WRITE_METHODS: frozenset[str] = frozenset({"write_text", "write_bytes"})
PYTHON_HANDLE_WRITE_METHODS: frozenset[str] = frozenset({"write", "writelines"})
PYTHON_PATH_READ_METHODS: frozenset[str] = frozenset({"read_text", "read_bytes", "open"})
PYTHON_DECODERS: frozenset[str] = frozenset(
    {
        "base64.b64decode",
        "base64.urlsafe_b64decode",
        "base64.standard_b64decode",
        "base64.b32decode",
        "base64.b16decode",
        "base64.a85decode",
        "base64.b85decode",
        "base64.decodebytes",
        "binascii.a2b_base64",
        "binascii.a2b_hex",
        "binascii.unhexlify",
        "codecs.decode",
        "zlib.decompress",
        "gzip.decompress",
        "bz2.decompress",
        "lzma.decompress",
        "bytes.fromhex",
        "bytearray.fromhex",
    }
)
PYTHON_CODE_ARRAY_CALLS: frozenset[str] = frozenset({"bytes", "bytearray"})
PYTHON_CHARACTER_FUNCTION = "chr"
PYTHON_PROPAGATORS: frozenset[str] = frozenset(
    {
        "str",
        "bytes",
        "bytearray",
        "dict",
        "list",
        "tuple",
        "set",
        "frozenset",
        "sorted",
        "reversed",
        "repr",
        "format",
        "iter",
        "next",
        "enumerate",
        "zip",
        "map",
        "filter",
        "json.dumps",
        "json.loads",
        "os.path.join",
        "os.path.expanduser",
        "os.path.expandvars",
        "os.path.abspath",
        "os.path.realpath",
        "os.path.normpath",
        "os.fspath",
        "pathlib.Path",
        "pathlib.PurePath",
        "pathlib.PosixPath",
        "pathlib.WindowsPath",
        "urllib.parse.urlparse",
        "urllib.parse.urlsplit",
        "urllib.parse.urlencode",
        "urllib.parse.quote",
        "urllib.parse.quote_plus",
        "urllib.parse.urljoin",
        "urllib.parse.urlunparse",
        "base64.b64encode",
        "base64.urlsafe_b64encode",
        "base64.encodebytes",
        "binascii.hexlify",
        "zlib.compress",
        "gzip.compress",
        "textwrap.dedent",
        "inspect.cleandoc",
        "yaml.dump",
        "yaml.safe_dump",
        "copy.copy",
        "copy.deepcopy",
    }
)
PYTHON_MUTATING_METHODS: frozenset[str] = frozenset(
    {"append", "extend", "add", "update", "insert", "appendleft", "extendleft", "setdefault"}
)
PYTHON_STRING_COMPOSERS: frozenset[str] = frozenset({"format", "join"})
PYTHON_TOOL_BUILDERS: frozenset[str] = frozenset({"from_openapi", "from_fastapi"})

JAVASCRIPT_SHELL_CALLS: frozenset[str] = frozenset(
    {"child_process.exec", "child_process.execSync", "shelljs.exec"}
)
JAVASCRIPT_SHELL_OPTION_CALLS: dict[str, int] = {
    "child_process.spawn": 2,
    "child_process.spawnSync": 2,
    "child_process.execFile": 2,
    "child_process.execFileSync": 2,
    "execa": 2,
    "execa.execa": 2,
    "execa.sync": 2,
    "execa.execaSync": 2,
    "cross-spawn": 2,
    "cross-spawn.sync": 2,
}
JAVASCRIPT_SHELL_OPTION = "shell"
JAVASCRIPT_PROCESS_CALLS: frozenset[str] = frozenset(
    {
        "child_process.fork",
        "execa.execaCommand",
        "execa.execaCommandSync",
        "Bun.spawn",
        "Bun.spawnSync",
        "Deno.Command",
        "Deno.run",
    }
)
JAVASCRIPT_SHELL_METHODS: frozenset[str] = frozenset({"exec_command", "execCommand"})
JAVASCRIPT_CODE_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "globalThis.eval",
        "Function",
        "vm.runInNewContext",
        "vm.runInThisContext",
        "vm.runInContext",
        "vm.compileFunction",
        "vm.Script",
        "vm.SourceTextModule",
    }
)
JAVASCRIPT_TIMERS: frozenset[str] = frozenset({"setTimeout", "setInterval", "setImmediate"})
JAVASCRIPT_LOADERS: frozenset[str] = frozenset({"require", "import"})
JAVASCRIPT_RUN_FILE_CALLS: frozenset[str] = frozenset({"fs.chmod", "fs.chmodSync", "Deno.chmod"})
JAVASCRIPT_WRITE_CALLS: dict[str, tuple[int, int]] = {
    "fs.writeFile": (0, 1),
    "fs.writeFileSync": (0, 1),
    "fs.appendFile": (0, 1),
    "fs.appendFileSync": (0, 1),
    "fs.outputFile": (0, 1),
    "fs.outputFileSync": (0, 1),
    "fs.writeJson": (0, 1),
    "fs.writeJsonSync": (0, 1),
    "fs.outputJson": (0, 1),
    "fs.outputJsonSync": (0, 1),
    "Deno.writeFile": (0, 1),
    "Deno.writeTextFile": (0, 1),
    "Bun.write": (0, 1),
}
JAVASCRIPT_COPY_CALLS: dict[str, int] = {
    "fs.copyFile": 1,
    "fs.copyFileSync": 1,
    "fs.rename": 1,
    "fs.renameSync": 1,
    "fs.cp": 1,
    "fs.cpSync": 1,
    "fs.copy": 1,
    "fs.copySync": 1,
    "fs.move": 1,
    "fs.moveSync": 1,
    "fs.symlink": 1,
    "fs.symlinkSync": 1,
}
JAVASCRIPT_STREAM_CALLS: frozenset[str] = frozenset({"fs.createWriteStream"})
JAVASCRIPT_HANDLE_WRITE_METHODS: frozenset[str] = frozenset({"write", "end"})
JAVASCRIPT_READ_CALLS: frozenset[str] = frozenset(
    {
        "fs.readFile",
        "fs.readFileSync",
        "fs.createReadStream",
        "fs.readJson",
        "fs.readJsonSync",
        "fs.readJSON",
        "Deno.readFile",
        "Deno.readTextFile",
        "Bun.file",
    }
)
JAVASCRIPT_DECODERS: frozenset[str] = frozenset(
    {
        "atob",
        "zlib.inflateSync",
        "zlib.inflateRawSync",
        "zlib.gunzipSync",
        "zlib.unzipSync",
        "zlib.brotliDecompressSync",
        "zlib.inflate",
        "zlib.gunzip",
    }
)
JAVASCRIPT_BUFFER_FROM = "Buffer.from"
JAVASCRIPT_DECODING_ENCODINGS: frozenset[str] = frozenset({"base64", "base64url", "hex"})
JAVASCRIPT_CHARACTER_FUNCTION = "String.fromCharCode"
JAVASCRIPT_CHARACTER_FUNCTIONS: frozenset[str] = frozenset({"String.fromCharCode", "String.fromCodePoint"})
JAVASCRIPT_PROPAGATORS: frozenset[str] = frozenset(
    {
        "String",
        "JSON.stringify",
        "JSON.parse",
        "Buffer.from",
        "Buffer.concat",
        "encodeURIComponent",
        "encodeURI",
        "decodeURIComponent",
        "decodeURI",
        "btoa",
        "escape",
        "Object.entries",
        "Object.values",
        "Object.keys",
        "Object.fromEntries",
        "Object.assign",
        "Array.from",
        "Array.of",
        "Promise.resolve",
        "Promise.all",
        "path.join",
        "path.resolve",
        "path.normalize",
        "path.format",
        "path.posix.join",
        "path.win32.join",
        "url.format",
        "url.pathToFileURL",
        "querystring.stringify",
        "util.format",
        "structuredClone",
    }
)
JAVASCRIPT_MUTATING_METHODS: frozenset[str] = frozenset({"push", "unshift", "set", "add", "append", "splice"})
JAVASCRIPT_ELEMENT_CALLBACKS: frozenset[str] = frozenset(
    {"map", "forEach", "filter", "find", "findLast", "some", "every", "flatMap", "sort"}
)
JAVASCRIPT_VALUE_CALLBACKS: frozenset[str] = frozenset({"then", "on", "once", "addListener", "addEventListener"})
JAVASCRIPT_RESULT_CALLBACKS: frozenset[str] = frozenset({"map", "flatMap", "then"})
JAVASCRIPT_REDUCERS: frozenset[str] = frozenset({"reduce", "reduceRight"})
JAVASCRIPT_PROMISE = "Promise"
JAVASCRIPT_TOOL_BUILDERS: frozenset[str] = frozenset({"fromOpenApi", "fromOpenAPI", "from_openapi"})
