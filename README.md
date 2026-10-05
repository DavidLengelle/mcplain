# MCPlain

MCPlain is a security scanner for MCP (Model Context Protocol) servers, made for beginners.

You paste a GitHub link, an `npx` command or a `uvx` command. MCPlain downloads the code,
reads it without ever running it, and explains in plain words what the server can do:
network access, reading or writing files, running commands, reading secrets, and more.

**Status: under construction.** The analysis engine (`engine/`), the HTTP API with its isolated
analysis workers (`api/`) and a first version of the website (`web/`, in English and French) exist.

## Try the engine

```bash
cd engine
uv run mcplain https://github.com/modelcontextprotocol/servers/tree/main/src/fetch
uv run mcplain "npx -y @modelcontextprotocol/server-filesystem" --lang fr
uv run mcplain "uvx mcp-server-fetch" --json
uv run mcplain --local path/to/a/server/folder
uv run mcplain --rules --lang fr
```

Set `GITHUB_TOKEN` to raise the GitHub API limit (60 requests per hour without a token).
`--local` reads a folder on your disk without any network access.

## Architecture

```text
 browser
      |  http://127.0.0.1:3000  (pages, and /api/* passed on to the API)
      v
 +---------+   network "front": the website reaches the API only
 | website |   never reads third-party code, never decides a color
 +---------+
      |  POST /api/analyses {"input": "uvx mcp-server-fetch"}  ->  202 {"id": ...}
      v
 +---------+      +--------------------------+   network "back": API, dispatcher, PostgreSQL
 |   API   | ---> | PostgreSQL: analyses     |
 |   API   | ---> | PostgreSQL: analyses     |   the queue and the results
 +---------+      +--------------------------+
 never reads           ^            |  SELECT ... FOR UPDATE SKIP LOCKED
 third-party code      |  result    v
                  +------------------------------+
                  | dispatcher                   |  network (allow list only), Docker socket
                  |  1. resolve: exact version   |  never opens an archive,
                  |  2. download raw archive,    |  never reads third-party code
                  |     check digest, ask OSV    |
                  +------------------------------+
                         |  job folder, read-only        ^  one JSON line on stdout
                         v                               |
                  +------------------------------+
                  | atelier (one per analysis)   |  no network, no secret, read-only,
                  |  extract, read, apply rules  |  uid 10001, no capability, 1 GB, 120 s
                  +------------------------------+
```

The atelier is the only place where the downloaded archive is opened and the code is read. It is a
fresh container for each analysis, removed right after. Any error, timeout or unreadable report
gives a gray verdict, never green. OSV.dev is asked again at every request; the same version of the
same package, with the same reputation, is analyzed once and later requests reuse the result. A new
malicious report on OSV.dev means a new analysis.

## Run it locally

You need Docker with Docker Compose. Copy the settings, then fill in `.env`: a database password,
the absolute path of `var/jobs`, your user and group ids (`id -u`, `id -g`), and the group of the
Docker socket as seen from a container (`DOCKER_GID`).

```bash
cp .env.example .env
mkdir -p var/jobs
docker compose build atelier
docker compose up -d --build
curl -s -X POST http://127.0.0.1:8000/api/analyses -H "Content-Type: application/json" -d '{"input": "uvx mcp-server-fetch"}'
curl -s http://127.0.0.1:8000/api/analyses/<id>
```

The website is then on http://127.0.0.1:3000, and the API on `127.0.0.1:8000`. Both only listen on
`127.0.0.1`. `GITHUB_TOKEN` in `.env` is optional: it raises the GitHub API limit and only the
dispatcher receives it.

### The website in development

You need Node 24 and pnpm 11 (not npm). With the stack running for the API:

```bash
cd web
pnpm install --frozen-lockfile
pnpm dev
```

Open http://localhost:3000. The tests: `pnpm lint`, `pnpm typecheck`, `pnpm test` (Vitest) and
`pnpm test:e2e` (Playwright with a simulated API). A guided tour of the code, in French, is in
[docs/web.fr.md](docs/web.fr.md).

## What MCPlain checks

The verdict has four colors. Red: a red rule fired (code that hides, steals, plants or runs
something, or a serious flaw an attacker can use). Orange: an orange rule fired (a power or a
sign that deserves a careful look). Gray: no rule fired, but MCPlain could not read or follow
all the code. Green: no rule fired, and everything was read and followed.

Version 1 of the rules has 20 rules: 12 red and 8 orange. Each rule, its sources and its known
false positive are listed in [docs/rules.md](docs/rules.md) (in French:
[docs/rules.fr.md](docs/rules.fr.md)). `uv run mcplain --rules` prints the same catalog.

## What MCPlain cannot see

Finding nothing does not prove that a server is safe. MCPlain cannot see:

- **Changes after the analysis** (rug pull): a server can change its code or its tool
  descriptions after MCPlain read them. MCPlain analyzes one version, at one moment.
- **Traps read at runtime**: a web page, a file or an API answer that a tool reads can carry
  instructions for the AI. MCPlain reads the code, not the data the tools will read.
- **The code of the dependencies**: only their reputation on OSV.dev is checked (the analyzed
  package at its exact version, its direct dependencies by name).
- **Remote MCP servers**: a server reached over the network has no code to download.
- **Compiled code**: binaries, WebAssembly, `.pyc` files and native extensions cannot be read.
- **Flows too indirect for the tracking**: when in doubt, the data flow engine drops a value
  rather than inventing a flow (calls through unknown dictionaries, `getattr`, closures, more
  than 5 calls deep...). The report says when the tracking of a tool is incomplete, and such a
  server is never green.

## Security

The engine only uses dependency versions published at least 7 days ago.
This is set in `engine/pyproject.toml`:

```toml
[tool.uv]
exclude-newer = "7 days"
```

Why 7 days: when an attacker publishes a malicious version of a package, it is usually
spotted and removed within a few days. Waiting one week gives the registry time to remove it
before `uv lock` can pick it. The cost is that updates arrive one week late.

For an urgent security fix, lift the delay for that one package only (here `httpx`):

```toml
[tool.uv]
exclude-newer = "7 days"
exclude-newer-package = { httpx = false }
```

Then run `uv lock --upgrade-package httpx`. Remove the `exclude-newer-package` line once
the fixed version is more than 7 days old.

The website follows the same rule with pnpm 11, in `web/pnpm-workspace.yaml`:
`minimumReleaseAge: 10080` (7 days, in minutes). An urgent fix is allowed at its exact version only,
with a comment that says why:

```yaml
minimumReleaseAgeExclude:
  - next@16.3.8
```

No install script of a dependency runs (`allowBuilds`), and the lockfile is committed.
The website sends a strict Content Security Policy with a fresh nonce on every page, and shows every
text that comes from analyzed code as plain text, with invisible characters made visible.

## License

AGPL-3.0, see [LICENSE](LICENSE).
