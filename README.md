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
```

Set `GITHUB_TOKEN` to raise the GitHub API limit (60 requests per hour without a token).

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
