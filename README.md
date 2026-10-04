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

## License

AGPL-3.0, see [LICENSE](LICENSE).
