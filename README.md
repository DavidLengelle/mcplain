# MCPlain

MCPlain is a security scanner for MCP (Model Context Protocol) servers, made for beginners.

You paste a GitHub link, an `npx` command or a `uvx` command. MCPlain downloads the code,
reads it without ever running it, and explains in plain words what the server can do:
network access, reading or writing files, running commands, reading secrets, and more.

**Status: under construction.** Only the analysis engine exists for now (`engine/`).
The website will come later (`web/`).

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

## License

AGPL-3.0, see [LICENSE](LICENSE).
