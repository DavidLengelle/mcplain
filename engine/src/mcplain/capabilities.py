"""Fixed list of capabilities and the per-language tables that detect them"""

import re
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase


class Capability(StrEnum):
    """Class that lists every capability MCPlain can report"""

    NETWORK = "network"
    FS_READ = "fs_read"
    FS_WRITE = "fs_write"
    PROCESS_EXEC = "process_exec"
    ENV_READ = "env_read"
    ENV_READ_SECRET = "env_read_secret"
    DYNAMIC_CODE = "dynamic_code"
    BASE64_DECODE = "base64_decode"
    SENSITIVE_PATH = "sensitive_path"
    INSTALL_SCRIPT = "install_script"


POWERFUL_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.PROCESS_EXEC,
        Capability.FS_WRITE,
        Capability.ENV_READ_SECRET,
        Capability.DYNAMIC_CODE,
        Capability.SENSITIVE_PATH,
        Capability.INSTALL_SCRIPT,
    }
)


class RuleKind(StrEnum):
    """Class that tells how a rule pattern must be compared"""

    MODULE = "module"
    GLOBAL = "global"
    METHOD = "method"


@dataclass(frozen=True)
class ApiRule:
    """Class that maps an API name pattern to a capability"""

    pattern: str
    capability: Capability
    kind: RuleKind


def _rules(kind: RuleKind, capability: Capability, *patterns: str) -> tuple[ApiRule, ...]:
    """Build one rule per pattern with the same kind and capability"""

    return tuple(ApiRule(pattern, capability, kind) for pattern in patterns)


PYTHON_RULES: tuple[ApiRule, ...] = (
    *_rules(
        RuleKind.MODULE,
        Capability.NETWORK,
        "requests.*",
        "httpx.*",
        "urllib.request.*",
        "urllib3.*",
        "aiohttp.*",
        "socket.*",
        "http.client.*",
        "websockets.*",
        "websocket.*",
        "ftplib.*",
        "smtplib.*",
        "telnetlib.*",
        "paramiko.*",
        "pycurl.*",
        "yagmail.*",
        "postmarker.*",
        "sendgrid.*",
        "asyncio.open_connection",
        "asyncio.start_server",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.PROCESS_EXEC,
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
        "os.system",
        "os.popen",
        "os.exec*",
        "os.spawn*",
        "os.posix_spawn*",
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "pty.spawn",
        "pexpect.*",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.FS_WRITE,
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.removedirs",
        "os.rename",
        "os.renames",
        "os.replace",
        "os.mkdir",
        "os.makedirs",
        "os.chmod",
        "os.chown",
        "os.symlink",
        "os.link",
        "os.truncate",
        "os.utime",
        "os.lchmod",
        "os.lchown",
        "shutil.copy*",
        "shutil.move",
        "shutil.rmtree",
        "shutil.make_archive",
        "shutil.unpack_archive",
        "shutil.chown",
    ),
    *_rules(
        RuleKind.METHOD,
        Capability.FS_WRITE,
        "write_text",
        "write_bytes",
        "unlink",
        "rmdir",
        "mkdir",
        "touch",
        "symlink_to",
        "hardlink_to",
        "chmod",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.FS_READ,
        "os.listdir",
        "os.scandir",
        "os.walk",
        "os.stat",
        "os.lstat",
        "os.access",
        "os.readlink",
        "glob.glob",
        "glob.iglob",
    ),
    *_rules(
        RuleKind.METHOD,
        Capability.FS_READ,
        "read_text",
        "read_bytes",
        "iterdir",
        "glob",
        "rglob",
        "stat",
        "lstat",
    ),
    *_rules(RuleKind.GLOBAL, Capability.DYNAMIC_CODE, "eval", "exec", "compile", "__import__"),
    *_rules(
        RuleKind.MODULE,
        Capability.DYNAMIC_CODE,
        "importlib.import_module",
        "importlib.__import__",
        "runpy.run_path",
        "runpy.run_module",
        "pickle.load",
        "pickle.loads",
        "marshal.load",
        "marshal.loads",
        "builtins.eval",
        "builtins.exec",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.BASE64_DECODE,
        "base64.b64decode",
        "base64.urlsafe_b64decode",
        "base64.standard_b64decode",
        "base64.decodebytes",
        "binascii.a2b_base64",
    ),
)

NETWORK_CLIENT_METHODS: frozenset[str] = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
)
URL_AFTER_METHOD: frozenset[str] = frozenset({"request", "stream"})
NETWORK_SEND_METHODS: frozenset[str] = frozenset(
    {
        "post",
        "put",
        "patch",
        "delete",
        "send",
        "sendall",
        "sendto",
        "sendmail",
        "send_message",
        "sendMail",
        "sendEmail",
        "upload",
        "write",
    }
)
NETWORK_BODY_KEYS: frozenset[str] = frozenset({"data", "json", "content", "files", "body", "form"})
SAFE_HTTP_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
PYTHON_NETWORK_CLIENTS: frozenset[str] = frozenset(
    {
        "httpx.Client",
        "httpx.AsyncClient",
        "requests.Session",
        "requests.session",
        "aiohttp.ClientSession",
        "urllib3.PoolManager",
    }
)
PYTHON_URL_FUNCTIONS: frozenset[str] = frozenset({"urllib.request.urlopen", "urllib.request.Request"})
PYTHON_CLIENT_URL_KEYWORDS: tuple[str, ...] = ("base_url",)
PYTHON_OPEN_GLOBALS: frozenset[str] = frozenset({"open"})
PYTHON_OPEN_FUNCTIONS: frozenset[str] = frozenset({"io.open", "codecs.open", "aiofiles.open"})
PYTHON_WRITE_MODE_CHARS = "wax+"
PYTHON_ENV_MAPPINGS: frozenset[str] = frozenset({"os.environ", "os.environb"})
PYTHON_ENV_GETTERS: frozenset[str] = frozenset(
    {"os.getenv", "os.getenvb", "os.environ.get", "os.environ.setdefault", "os.environ.pop"}
)
PYTHON_TEXT_HELPERS: frozenset[str] = frozenset({"textwrap.dedent", "inspect.cleandoc"})

JAVASCRIPT_RULES: tuple[ApiRule, ...] = (
    *_rules(
        RuleKind.GLOBAL,
        Capability.NETWORK,
        "fetch",
        "globalThis.fetch",
        "WebSocket",
        "XMLHttpRequest",
        "EventSource",
        "Deno.connect",
        "Bun.connect",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.NETWORK,
        "axios",
        "axios.*",
        "http.*",
        "https.*",
        "http2.*",
        "net.*",
        "tls.*",
        "dgram.*",
        "dns.*",
        "undici",
        "undici.*",
        "ws",
        "ws.*",
        "node-fetch",
        "node-fetch.*",
        "got",
        "got.*",
        "superagent",
        "superagent.*",
        "request",
        "request.*",
        "ky",
        "ky.*",
        "cross-fetch",
        "cross-fetch.*",
        "isomorphic-fetch",
        "socket.io-client",
        "socket.io-client.*",
        "nodemailer",
        "nodemailer.*",
        "postmark",
        "postmark.*",
        "@sendgrid/mail",
        "@sendgrid/mail.*",
        "resend",
        "resend.*",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.PROCESS_EXEC,
        "child_process.*",
        "execa",
        "execa.*",
        "cross-spawn",
        "cross-spawn.*",
        "shelljs.exec",
    ),
    *_rules(
        RuleKind.GLOBAL,
        Capability.PROCESS_EXEC,
        "Bun.spawn",
        "Bun.spawnSync",
        "Bun.$",
        "Deno.Command",
        "Deno.run",
    ),
    *_rules(RuleKind.METHOD, Capability.PROCESS_EXEC, "execSync", "spawnSync", "execFileSync"),
    *_rules(
        RuleKind.MODULE,
        Capability.FS_WRITE,
        "fs.writeFile*",
        "fs.appendFile*",
        "fs.unlink*",
        "fs.rm",
        "fs.rmSync",
        "fs.rmdir*",
        "fs.mkdir*",
        "fs.mkdtemp*",
        "fs.rename*",
        "fs.copyFile*",
        "fs.cp",
        "fs.cpSync",
        "fs.createWriteStream",
        "fs.truncate*",
        "fs.chmod*",
        "fs.chown*",
        "fs.lchmod*",
        "fs.lchown*",
        "fs.utimes*",
        "fs.lutimes*",
        "fs.symlink*",
        "fs.link*",
        "fs.write",
        "fs.writeSync",
        "fs.writev*",
        "fs.outputFile*",
        "fs.outputJson*",
        "fs.writeJson*",
        "fs.remove*",
        "fs.move*",
        "fs.copy*",
        "fs.emptyDir*",
        "fs.ensureFile*",
        "fs.ensureDir*",
    ),
    *_rules(
        RuleKind.GLOBAL,
        Capability.FS_WRITE,
        "Deno.writeFile",
        "Deno.writeTextFile",
        "Deno.remove",
        "Bun.write",
    ),
    *_rules(
        RuleKind.METHOD,
        Capability.FS_WRITE,
        "writeFile",
        "writeFileSync",
        "appendFile",
        "appendFileSync",
        "createWriteStream",
        "unlinkSync",
        "rmSync",
        "mkdirSync",
    ),
    *_rules(
        RuleKind.MODULE,
        Capability.FS_READ,
        "fs.readFile*",
        "fs.readdir*",
        "fs.readlink*",
        "fs.read",
        "fs.readSync",
        "fs.opendir*",
        "fs.createReadStream",
        "fs.readJson*",
        "fs.stat*",
        "fs.lstat*",
        "fs.fstat*",
        "fs.realpath*",
        "fs.access*",
        "fs.exists*",
    ),
    *_rules(RuleKind.GLOBAL, Capability.FS_READ, "Deno.readFile", "Deno.readTextFile", "Bun.file"),
    *_rules(
        RuleKind.METHOD,
        Capability.FS_READ,
        "readFile",
        "readFileSync",
        "readdirSync",
        "createReadStream",
    ),
    *_rules(RuleKind.GLOBAL, Capability.DYNAMIC_CODE, "eval", "globalThis.eval", "Function"),
    *_rules(RuleKind.MODULE, Capability.DYNAMIC_CODE, "vm.*"),
    *_rules(RuleKind.GLOBAL, Capability.BASE64_DECODE, "atob"),
)

JAVASCRIPT_OPEN_FUNCTIONS: frozenset[str] = frozenset({"fs.open", "fs.openSync"})
JAVASCRIPT_WRITE_FLAG_CHARS = "wa+"
JAVASCRIPT_NETWORK_CLIENTS: frozenset[str] = frozenset(
    {"axios.create", "got.extend", "ky.create", "ky.extend", "undici.Client", "undici.Pool"}
)
JAVASCRIPT_URL_GLOBALS: frozenset[str] = frozenset({"fetch", "globalThis.fetch", "WebSocket", "EventSource"})
JAVASCRIPT_URL_KEYS: tuple[str, ...] = ("url", "href", "hostname", "host")
JAVASCRIPT_CLIENT_URL_KEYS: tuple[str, ...] = ("baseURL", "prefixUrl", "origin")
JAVASCRIPT_ENV_OBJECTS: frozenset[str] = frozenset({"process.env", "Bun.env"})
JAVASCRIPT_ENV_GETTERS: frozenset[str] = frozenset({"Deno.env.get"})
JAVASCRIPT_BUFFER_DECODERS: frozenset[str] = frozenset({"Buffer.from"})
JAVASCRIPT_BASE64_ENCODINGS: frozenset[str] = frozenset({"base64", "base64url"})
JAVASCRIPT_STRING_TIMERS: frozenset[str] = frozenset({"setTimeout", "setInterval"})
JAVASCRIPT_MODULE_ALIASES: dict[str, str] = {
    "fs/promises": "fs",
    "fs-extra": "fs",
    "graceful-fs": "fs",
    "dns/promises": "dns",
}
JAVASCRIPT_CHAIN_REWRITES: tuple[tuple[str, str], ...] = (
    ("fs.promises.", "fs."),
    ("dns.promises.", "dns."),
)


def match_rule(rules: tuple[ApiRule, ...], name: str, kind: RuleKind) -> ApiRule | None:
    """Return the first rule of the given kind that matches a name"""

    for rule in rules:
        if rule.kind is kind and fnmatchcase(name, rule.pattern):
            return rule
    return None


def normalize_javascript_module(specifier: str) -> str:
    """Return the canonical name of a JavaScript module specifier"""

    name = specifier.strip()
    if name.startswith("node:"):
        name = name[len("node:"):]
    return JAVASCRIPT_MODULE_ALIASES.get(name, name)


def rewrite_javascript_chain(qualified: str) -> str:
    """Fold equivalent JavaScript API chains into their canonical form"""

    for prefix, replacement in JAVASCRIPT_CHAIN_REWRITES:
        if qualified.startswith(prefix):
            return replacement + qualified[len(prefix):]
    return qualified


SECRET_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "KEY",
        "KEYS",
        "APIKEY",
        "TOKEN",
        "TOKENS",
        "SECRET",
        "SECRETS",
        "PASSWORD",
        "PASSWORDS",
        "PASSWD",
        "PASS",
        "PASSPHRASE",
        "CREDENTIAL",
        "CREDENTIALS",
        "CREDS",
        "COOKIE",
        "COOKIES",
        "DSN",
        "JWT",
        "BEARER",
        "OAUTH",
    }
)
SECRET_NAME_SUFFIXES: tuple[str, ...] = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIALS")


def is_secret_name(name: str) -> bool:
    """Tell whether an environment variable name looks like a secret"""

    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).upper()
    tokens = [token for token in re.split(r"[^A-Z0-9]+", spaced) if token]
    for token in tokens:
        if token in SECRET_NAME_TOKENS:
            return True
        if len(token) > 4 and token.endswith(SECRET_NAME_SUFFIXES):
            return True
    return False


class PathKind(StrEnum):
    """Class that tells why a sensitive path matters: it holds secrets, starts code, or configures a tool"""

    SECRET = "secret"
    AUTOSTART = "autostart"
    TOOL_CONFIG = "tool_config"


@dataclass(frozen=True)
class SensitivePath:
    """Class that maps a path pattern to a category name and its kinds"""

    category: str
    kinds: frozenset[PathKind]
    pattern: re.Pattern[str]


def _path(category: str, kinds: tuple[PathKind, ...], pattern: str, flags: int = 0) -> SensitivePath:
    """Build one sensitive path entry"""

    return SensitivePath(category, frozenset(kinds), re.compile(pattern, flags))


SECRET = (PathKind.SECRET,)
AUTOSTART = (PathKind.AUTOSTART,)
TOOL_CONFIG = (PathKind.TOOL_CONFIG,)

SENSITIVE_PATH_PATTERNS: tuple[SensitivePath, ...] = (
    _path("ssh_keys", SECRET, r"(?<![\w.-])\.ssh(?![\w-])", re.IGNORECASE),
    _path("ssh_keys", SECRET, r"\b(?:id_(?:rsa|dsa|ecdsa|ed25519)(?:_sk)?|known_hosts)\b"),
    _path("ssh_authorized_keys", AUTOSTART, r"\bauthorized_keys2?\b"),
    _path(
        "cloud_credentials",
        SECRET,
        r"\.aws[\\/](?:credentials|config)\b|\.config[\\/]gcloud\b|\.azure[\\/]|"
        r"\.kube[\\/]config\b|\.docker[\\/]config\.json\b|application_default_credentials\.json",
        re.IGNORECASE,
    ),
    _path(
        "env_file",
        SECRET,
        r"(?<![\w.-])\.env(?!\.(?:example|sample|template|dist)\b)(?:\.[\w-]+)?(?![\w-])",
        re.IGNORECASE,
    ),
    _path(
        "shell_startup",
        AUTOSTART,
        r"(?<![\w.-])\.(?:bashrc|zshrc|profile|bash_profile|bash_login|bash_logout|zprofile|zshenv|zlogin)"
        r"(?![\w-])|\.config[\\/]fish[\\/]config\.fish",
    ),
    _path(
        "shell_history",
        SECRET,
        r"(?<![\w.-])\.(?:bash_history|zsh_history|python_history|node_repl_history|psql_history|mysql_history)"
        r"(?![\w-])",
    ),
    _path("git_credentials", SECRET, r"(?<![\w.-])\.git-credentials(?![\w-])"),
    _path("git_config", TOOL_CONFIG, r"(?<![\w.-])\.gitconfig(?![\w-])"),
    _path(
        "package_config",
        (PathKind.SECRET, PathKind.TOOL_CONFIG),
        r"(?<![\w.-])\.(?:npmrc|pypirc|yarnrc(?:\.yml)?)(?![\w-])",
    ),
    _path("package_credentials", SECRET, r"(?<![\w.-])\.netrc(?![\w-])|\.cargo[\\/]credentials(?:\.toml)?"),
    _path("system_accounts", SECRET, r"/etc/(?:passwd|shadow|gshadow|sudoers)\b"),
    _path(
        "browser_profile",
        SECRET,
        r"Google[\\/ ]Chrome|google-chrome|chromium[\\/]|BraveSoftware|Microsoft[\\/ ]Edge|"
        r"\.mozilla[\\/]firefox|Mozilla[\\/ ]Firefox|Firefox[\\/]Profiles|Opera Software|"
        r"\bLogin Data\b",
        re.IGNORECASE,
    ),
    _path(
        "crypto_wallet",
        SECRET,
        r"\bwallet\.dat\b|\.electrum\b|Electrum[\\/]wallets|\.bitcoin[\\/]|\.litecoin[\\/]|\.monero[\\/]|"
        r"\.ethereum[\\/]keystore|keystore[\\/]UTC--|Exodus[\\/]exodus\.wallet|atomic[\\/]Local Storage|"
        r"\.config[\\/]solana[\\/]id\.json|nkbihfbeogaeaoehlefnkodbefgpgknn|bfnaelmomeimhlpmgjnjophhpkkoljpa",
        re.IGNORECASE,
    ),
    _path(
        "password_store",
        SECRET,
        r"Library[\\/]Keychains|\.gnupg\b|\.password-store\b|\.local[\\/]share[\\/]keyrings",
    ),
    _path(
        "mcp_client_config",
        TOOL_CONFIG,
        r"claude_desktop_config\.json|\.cursor[\\/]mcp\.json|(?<![\w.-])\.claude\.json|"
        r"\.claude[\\/]settings(?:\.local)?\.json|(?<![\w.-])\.mcp\.json|windsurf[\\/]mcp_config\.json|"
        r"\.vscode[\\/]mcp\.json|Code[\\/]User[\\/](?:settings|mcp)\.json|cline_mcp_settings\.json|"
        r"(?<![\w.-])mcp_settings\.json|\.roo[\\/]mcp\.json|\.gemini[\\/]settings\.json|"
        r"\.codex[\\/]config\.toml|\.continue[\\/]config\.(?:json|yaml)|\.config[\\/]zed[\\/]settings\.json",
        re.IGNORECASE,
    ),
    _path("cron", AUTOSTART, r"\bcrontab\b|/etc/cron(?:\.d|\.hourly|\.daily|\.weekly|\.monthly)?\b|/var/spool/cron\b"),
    _path("systemd_unit", AUTOSTART, r"\.config[\\/]systemd[\\/]user\b|/etc/systemd/system\b"),
    _path("launch_agent", AUTOSTART, r"Library[\\/]Launch(?:Agents|Daemons)\b"),
    _path(
        "windows_startup",
        AUTOSTART,
        r"Start Menu[\\/]+Programs[\\/]+Startup|shell:startup|CurrentVersion[\\/]+Run(?:Once)?\b",
        re.IGNORECASE,
    ),
    _path("desktop_autostart", AUTOSTART, r"\.config[\\/]autostart\b"),
)
SENSITIVE_PATH_KINDS: dict[str, frozenset[PathKind]] = {
    entry.category: entry.kinds for entry in SENSITIVE_PATH_PATTERNS
}


def path_kinds(category: str) -> frozenset[PathKind]:
    """Return the kinds of one sensitive path category"""

    return SENSITIVE_PATH_KINDS.get(category, frozenset())


def find_sensitive_paths(text: str) -> list[tuple[str, str]]:
    """Return each sensitive path category and matched text found in a string"""

    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in SENSITIVE_PATH_PATTERNS:
        for match in entry.pattern.finditer(text):
            key = (entry.category, match.group(0))
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found
