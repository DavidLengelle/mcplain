"""Tests of the base functions and outside libraries added to the tables in engine 0.8.0: each one lights its capabilities"""

from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.capabilities import JAVASCRIPT_LIBRARIES, PYTHON_LIBRARIES, Capability

READ = Capability.FS_READ
WRITE = Capability.FS_WRITE
RUN = Capability.PROCESS_EXEC
NET = Capability.NETWORK
CODE = Capability.DYNAMIC_CODE
LOCAL = Capability.LOCAL_CONNECTION
DOCKER = Capability.DOCKER_SOCKET
SECRET = Capability.ENV_READ_SECRET
PYTHON_HEAD = (
    "import asyncio\nimport bz2\nimport dbm\nimport gzip\nimport importlib\nimport importlib.util\nimport imaplib\nimport io\n"
    "import lzma\nimport nntplib\nimport os\nimport poplib\nimport shelve\nimport socketserver\nimport sqlite3\nimport ssl\n"
    "import tarfile\nimport tempfile\nimport webbrowser\nimport xmlrpc.client\nimport zipfile\nfrom http.server import HTTPServer\n"
    "from pathlib import Path\n"
)
JAVASCRIPT_HEAD = 'import fs from "node:fs";\nimport { Worker } from "node:worker_threads";\nimport { createRequire } from "node:module";\n'

PYTHON_CALLS: list[tuple[str, list[Capability]]] = [
    ("os.open(p, os.O_WRONLY | os.O_CREAT)", [WRITE]),
    ("os.open(p, os.O_RDONLY)", [READ]),
    ("os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)", [READ]),
    ("os.open(p, os.O_DIRECTORY | os.O_NOATIME | os.O_NOCTTY | os.O_BINARY | os.O_NOINHERIT)", [READ]),
    ("os.open(p, flags=os.O_RDONLY)", [READ]),
    ("os.open(p, os.O_RDONLY | os.O_TRUNC)", [WRITE]),
    ("os.open(p, os.O_RDONLY | 0)", [WRITE]),
    ("os.open(p, q)", [WRITE]),
    ("os.read(q, 10)", [READ]),
    ("os.pread(q, 10, 0)", [READ]),
    ("os.readv(q, [])", [READ]),
    ("os.preadv(q, [], 0)", [READ]),
    ("os.fstat(q)", [READ]),
    ("os.fwalk(p)", [READ]),
    ("os.write(q, b'x')", [WRITE]),
    ("os.pwrite(q, b'x', 0)", [WRITE]),
    ("os.writev(q, [])", [WRITE]),
    ("os.pwritev(q, [], 0)", [WRITE]),
    ("os.ftruncate(q, 0)", [WRITE]),
    ("os.fchmod(q, 0o600)", [WRITE]),
    ("os.fchown(q, 1, 1)", [WRITE]),
    ("os.mkfifo(p)", [WRITE]),
    ("os.mknod(p)", [WRITE]),
    ("os.sendfile(q, q, 0, 10)", [WRITE]),
    ("os.copy_file_range(q, q, 10)", [WRITE]),
    ("os.fdopen(q)", [READ]),
    ("os.fdopen(q, 'w')", [WRITE]),
    ("os.fdopen(q, mode=p)", [WRITE]),
    ("os.path.exists(p)", [READ]),
    ("os.path.lexists(p)", [READ]),
    ("os.path.isfile(p)", [READ]),
    ("os.path.isdir(p)", [READ]),
    ("os.path.islink(p)", [READ]),
    ("os.path.getsize(p)", [READ]),
    ("os.path.getmtime(p)", [READ]),
    ("os.path.getatime(p)", [READ]),
    ("os.path.getctime(p)", [READ]),
    ("os.startfile(p)", [RUN]),
    ("io.FileIO(p)", [READ]),
    ("io.FileIO(p, 'w')", [WRITE]),
    ("io.open_code(p)", [READ]),
    ("tempfile.mkstemp()", [WRITE]),
    ("tempfile.mkdtemp()", [WRITE]),
    ("tempfile.NamedTemporaryFile()", [WRITE]),
    ("tempfile.TemporaryFile()", [WRITE]),
    ("tempfile.SpooledTemporaryFile()", [WRITE]),
    ("tempfile.TemporaryDirectory()", [WRITE]),
    ("zipfile.ZipFile(p)", [READ]),
    ("zipfile.ZipFile(p, 'a')", [WRITE]),
    ("zipfile.ZipFile(p, mode=q)", [WRITE]),
    ("tarfile.open(p, 'r:gz')", [READ]),
    ("tarfile.open(p, 'w:gz')", [WRITE]),
    ("tarfile.TarFile(p, 'x')", [WRITE]),
    ("gzip.open(p)", [READ]),
    ("gzip.open(p, 'wb')", [WRITE]),
    ("gzip.GzipFile(p, 'ab')", [WRITE]),
    ("bz2.open(p, 'wb')", [WRITE]),
    ("bz2.BZ2File(p)", [READ]),
    ("lzma.open(p, 'xb')", [WRITE]),
    ("lzma.LZMAFile(p)", [READ]),
    ("dbm.open(p)", [READ]),
    ("dbm.open(p, 'c')", [WRITE]),
    ("dbm.open(p, flag='n')", [WRITE]),
    ("sqlite3.connect(p)", [WRITE]),
    ("sqlite3.connect(':memory:')", []),
    ("shelve.open(p)", [WRITE]),
    ("q.extractall(p)", [WRITE]),
    ("webbrowser.open(p)", [RUN]),
    ("webbrowser.open_new(p)", [RUN]),
    ("webbrowser.open_new_tab(p)", [RUN]),
    ("q.subprocess_exec(p, 'git')", [RUN]),
    ("q.subprocess_shell(p, 'ls')", [RUN]),
    ("poplib.POP3_SSL(p)", [NET]),
    ("imaplib.IMAP4_SSL(p)", [NET]),
    ("nntplib.NNTP(p)", [NET]),
    ("xmlrpc.client.ServerProxy(p)", [NET]),
    ("ssl.get_server_certificate((p, 443))", [NET]),
    ("HTTPServer((p, 8080), q)", [NET]),
    ("socketserver.TCPServer((p, 8080), q)", [NET]),
    ("socketserver.ThreadingUDPServer((p, 53), q)", [NET]),
    ("q.create_connection(p, 'example.com', 443)", [NET]),
    ("q.create_datagram_endpoint(p, remote_addr=('example.com', 53))", [NET]),
    ("q.create_server(p, 'localhost', 8080)", [NET]),
    ("q.sock_connect(p, ('example.com', 443))", [NET]),
    ("asyncio.open_unix_connection(p)", [LOCAL]),
    ("asyncio.start_unix_server(q, p)", [LOCAL]),
    ("q.create_unix_connection(p, '/tmp/notes.sock')", [LOCAL]),
    ("asyncio.open_unix_connection('/var/run/docker.sock')", [DOCKER]),
    ("importlib.util.module_from_spec(q)", [CODE]),
    ("q.loader.exec_module(p)", [CODE]),
    ("importlib.reload(q)", [CODE]),
]

PATH_CALLS: list[tuple[str, list[Capability]]] = [
    ("Path(p).open('w')", [WRITE]),
    ("Path(p).open()", [READ]),
    ("Path(p).open(mode=q)", [WRITE]),
    ("(Path(p) / 'notes.txt').open('a')", [WRITE]),
    ("Path(p).resolve().parent.open('x')", [WRITE]),
    ("Path(p).rename(q)", [WRITE]),
    ("Path(p).replace(q)", [WRITE]),
    ("Path(p).lchmod(0o600)", [WRITE]),
    ("Path(p).copy(q)", [WRITE]),
    ("Path(p).move(q)", [WRITE]),
    ("Path(p).copy_into(q)", [WRITE]),
    ("Path(p).move_into(q)", [WRITE]),
    ("Path(p).exists()", [READ]),
    ("Path(p).is_file()", [READ]),
    ("Path(p).is_dir()", [READ]),
    ("Path(p).walk()", [READ]),
    ("Path(p).readlink()", [READ]),
    ("q.open(p, 'w')", [WRITE]),
    ("q.open('a')", [WRITE]),
    ("q.open()", []),
    ("q.open(p)", []),
    ("q.replace('a', 'b')", []),
    ("q.rename(columns=p)", []),
    ("q.exists()", []),
]

JAVASCRIPT_CALLS: list[tuple[str, list[Capability]]] = [
    ("fs.ftruncate(q, 0)", [WRITE]),
    ("fs.ftruncateSync(q)", [WRITE]),
    ("fs.fchmod(q, 0o600)", [WRITE]),
    ("fs.fchmodSync(q, 0o600)", [WRITE]),
    ("fs.fchown(q, 1, 1)", [WRITE]),
    ("fs.fchownSync(q, 1, 1)", [WRITE]),
    ("fs.futimes(q, 1, 1)", [WRITE]),
    ("fs.futimesSync(q, 1, 1)", [WRITE]),
    ("fs.readv(q, [])", [READ]),
    ("fs.readvSync(q, [])", [READ]),
    ("fs.watch(p)", [READ]),
    ("fs.watchFile(p, q)", [READ]),
    ("fs.glob(p)", [READ]),
    ("fs.globSync(p)", [READ]),
    ("fs.openAsBlob(p)", [READ]),
    ("new Worker(p)", [CODE]),
    ("new Worker(p, { eval: true })", [CODE]),
    ("process.dlopen(q, p)", [CODE]),
    ("createRequire(p)(q)", [CODE]),
    ("createRequire(p)('./package.json')", []),
]


def python_findings(tmp_path: Path, head: str, call: str) -> list[Capability]:
    """Return the capabilities found in one function of a Python file holding one call"""

    (tmp_path / "server.py").write_text(f"{head}\n\ndef work(p, q):\n    return {call}\n", encoding="utf-8")
    return [finding.capability for finding in PythonAdapter().analyze(tmp_path).findings]


def javascript_findings(tmp_path: Path, head: str, body: str) -> list[Capability]:
    """Return the capabilities found in one function of a JavaScript module"""

    (tmp_path / "package.json").write_text('{"name": "notes", "type": "module"}', encoding="utf-8")
    (tmp_path / "index.js").write_text(f"{head}\nexport function work(p, q) {{\n{body}\n}}\n", encoding="utf-8")
    return [finding.capability for finding in JavaScriptAdapter().analyze(tmp_path).findings]


@pytest.mark.parametrize(("call", "expected"), PYTHON_CALLS)
def test_python_base_functions(tmp_path: Path, call: str, expected: list[Capability]) -> None:
    """os, io, tempfile, archives, databases on a file, browsers, asyncio loops, mail and import helpers are classified"""

    assert python_findings(tmp_path, PYTHON_HEAD, call) == expected


@pytest.mark.parametrize(("call", "expected"), PATH_CALLS)
def test_path_methods_count_only_on_a_path(tmp_path: Path, call: str, expected: list[Capability]) -> None:
    """open, rename, replace and the others count on a pathlib path; on another object only .open with a write mode does"""

    assert python_findings(tmp_path, PYTHON_HEAD, call) == expected


def test_a_name_that_holds_a_path_or_a_parameter_annotated_path_is_a_path(tmp_path: Path) -> None:
    """A name assigned once to a path, or a parameter annotated Path, gives its methods their file capability"""

    source = (
        "from pathlib import Path\n\n\ndef work(folder: Path, name):\n    target = Path(name) / 'notes.txt'\n"
        "    target.replace(name)\n    folder.rename(name)\n"
    )
    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    assert [finding.capability for finding in PythonAdapter().analyze(tmp_path).findings] == [WRITE, WRITE]


def test_replace_on_an_object_of_unknown_type_stays_unseen(tmp_path: Path) -> None:
    """The known hole, kept in the roadmap: dest = make_target(); dest.replace(tmp) gives nothing"""

    source = "def make_target():\n    return 1\n\n\ndef work(tmp):\n    dest = make_target()\n    dest.replace(tmp)\n"
    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    assert PythonAdapter().analyze(tmp_path).findings == []


@pytest.mark.parametrize(
    "source",
    [
        "import os\nO_RDONLY = os.O_WRONLY\n\n\ndef work(p):\n    return os.open(p, O_RDONLY)\n",
        "import os\nfrom os import O_RDONLY\nO_RDONLY = os.O_RDWR\n\n\ndef work(p):\n    return os.open(p, O_RDONLY)\n",
        "import os\n\n\ndef work(p):\n    return os.open(p, 0)\n",
        "import os\n\n\ndef work(p, flags):\n    return os.open(p, flags)\n",
        "import os\n\n\ndef work(p):\n    return os.open(p, getattr(os, 'O_RDONLY', 0))\n",
        "import os\n\n\ndef read_flags():\n    return os.O_RDONLY\n\n\ndef work(p):\n    return os.open(p, read_flags())\n",
        "import os\n\n\ndef work(p):\n    return os.open(p)\n",
    ],
)
def test_os_open_flags_that_are_not_read_constants_of_os_write(tmp_path: Path, source: str) -> None:
    """A local name like O_RDONLY, a number, a parameter, getattr, a helper or no flags: a write"""

    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    assert [finding.capability for finding in PythonAdapter().analyze(tmp_path).findings] == [WRITE]


@pytest.mark.parametrize(
    "source",
    [
        "from os import O_RDONLY, open\n\n\ndef work(p):\n    return open(p, O_RDONLY)\n",
        "import os as system\n\n\ndef work(p):\n    return system.open(p, system.O_RDONLY | system.O_NOFOLLOW)\n",
        "import os\nfrom os import O_NOFOLLOW as NO_FOLLOW\n\n\ndef work(p):\n    return os.open(p, (os.O_RDONLY | NO_FOLLOW))\n",
    ],
)
def test_os_open_with_read_constants_imported_or_aliased_reads(tmp_path: Path, source: str) -> None:
    """Read constants of os, written in full through an alias of os or imported from os, are a read"""

    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    assert [finding.capability for finding in PythonAdapter().analyze(tmp_path).findings] == [READ]


@pytest.mark.parametrize(("call", "expected"), JAVASCRIPT_CALLS)
def test_javascript_base_functions(tmp_path: Path, call: str, expected: list[Capability]) -> None:
    """fs calls on descriptors, watching and globbing, worker threads, native modules and createRequire are classified"""

    assert javascript_findings(tmp_path, JAVASCRIPT_HEAD, f"  return {call};") == expected


def test_a_require_made_by_create_require_under_another_name_is_require(tmp_path: Path) -> None:
    """const load = createRequire(...): a written name is an import, a built .json path a read, any other name code"""

    body = '  const load = createRequire(import.meta.url);\n  load("./package.json");\n  load(p + "/package.json");\n  return load(q);'
    assert javascript_findings(tmp_path, JAVASCRIPT_HEAD, body) == [READ, CODE]


def library_names(name: str) -> tuple[str, str]:
    """Return a module to import and a name inside it, for any library of the tables"""

    if "." in name:
        module, _, member = name.rpartition(".")
        return module, member
    return name, "client"


@pytest.mark.parametrize("library", PYTHON_LIBRARIES, ids=lambda library: library.name)
def test_every_python_library_lights_all_its_capabilities(tmp_path: Path, library: object) -> None:
    """Any use of an outside library MCPlain does not read counts for everything it may do"""

    if library.name.startswith("anyio.") or library.name.startswith("jwt."):
        module, member = library_names(library.name)
    else:
        module, member = library.name, "client"
    head = f"import {module}\n"
    found = python_findings(tmp_path, head, f"{module}.{member}(p)")
    assert found == list(library.capabilities)


@pytest.mark.parametrize("library", JAVASCRIPT_LIBRARIES, ids=lambda library: library.name)
def test_every_javascript_library_lights_all_its_capabilities(tmp_path: Path, library: object) -> None:
    """Any use of an outside library MCPlain does not read counts for everything it may do"""

    head = f'import library from "{library.name}";\n'
    found = javascript_findings(tmp_path, head, "  return library.connect(p);")
    assert found == list(library.capabilities)


def test_a_postgres_pool_lights_internet_and_keeps_the_green_lock(tmp_path: Path) -> None:
    """new pg.Pool() is a network use, but creating a client is not a request: the library stays not followed"""

    head = 'import pg from "pg";\n'
    (tmp_path / "package.json").write_text('{"name": "notes", "type": "module"}', encoding="utf-8")
    (tmp_path / "index.js").write_text(f"{head}\nexport function work(p) {{\n  return new pg.Pool({{ connectionString: p }});\n}}\n", encoding="utf-8")
    analysis = JavaScriptAdapter().analyze(tmp_path)
    assert [finding.capability for finding in analysis.findings] == [NET]
    assert [item.library for item in analysis.network_imports] == ["pg"]
