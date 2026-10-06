# Reference reports

These files are produced by the real engine, never written by hand. Do not edit them: generate them again.
They are written with ASCII escapes (`json.dumps(..., ensure_ascii=True)`), so no raw invisible character
enters the repository.

| File | Verdict | How it was made |
| --- | --- | --- |
| `server-filesystem.view.json` | orange, served from the cache | local stack: `POST /api/analyses` with `npx -y @modelcontextprotocol/server-filesystem`, then `GET /api/analyses/{id}` |
| `mcp-server-time.view.json` | green | local stack, `uvx mcp-server-time` |
| `github-mcp-server.view.json` | gray, language not supported (Go) | local stack, `https://github.com/github/github-mcp-server` |
| `npm-not-found.view.json` | gray, failed download | local stack, `npx -y @mcplain-demo/this-package-does-not-exist` |
| `modelcontextprotocol-servers.view.json` | several servers, no verdict | local stack, `https://github.com/modelcontextprotocol/servers` |
| `awesome-mcp-servers.view.json` | list of links | local stack, `https://github.com/punkpeye/awesome-mcp-servers` |
| `postmark-like.result.json` | red | command line, from `engine/`: `uv run mcplain --local tests/fixtures/postmark_like --json` |
| `fixed-domains.result.json` | green, fixed domains | command line, from `engine/`: `uv run mcplain --local tests/fixtures/rules/O01/near_miss --json` |

`*.view.json` files are what the API answers; `*.result.json` files are engine results, wrapped in a view by
the test helpers (`tests/unit/reports.ts`, `tests/e2e/reports.ts`). Generate them again after a change of the
engine output, with the stack built from the same commit (`docker compose build atelier`, then
`docker compose up -d --build`).
