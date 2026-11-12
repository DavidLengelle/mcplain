# Reference reports

These files are produced by the real engine, never written by hand. Do not edit them: generate them again.
They are written with ASCII escapes (`json.dumps(..., ensure_ascii=True)`), so no raw invisible character
enters the repository.

| File | Verdict | How it was made |
| --- | --- | --- |
| `server-filesystem.view.json` | orange, served from the cache | local stack: `POST /api/analyses` with `npx -y @modelcontextprotocol/server-filesystem`, then `GET /api/analyses/{id}` |
| `mcp-server-time.view.json` | green, served from the cache | local stack, `uvx mcp-server-time` |
| `github-mcp-server.view.json` | gray, language not supported (Go), served from the cache | local stack, `https://github.com/github/github-mcp-server` |
| `npm-not-found.view.json` | gray, failed download | local stack, `npx -y @mcplain-demo/this-package-does-not-exist` |
| `modelcontextprotocol-servers.view.json` | several servers, no verdict | local stack, `https://github.com/modelcontextprotocol/servers` |
| `awesome-mcp-servers.view.json` | list of links | local stack, `https://github.com/punkpeye/awesome-mcp-servers` |
| `postmark-like.result.json` | red | command line, from `engine/`: `uv run mcplain --local tests/fixtures/postmark_like --json` |
| `fixed-domains.result.json` | green, fixed domains | command line, from `engine/`: `uv run mcplain --local tests/fixtures/rules/O01/near_miss --json` |
| `network-unresolved.result.json` | gray, network library not followed, with coverage | command line, from `engine/`: `uv run mcplain --local tests/fixtures/python_network_elsewhere --json` |
| `partial-tracking.result.json` | gray, a call not followed, with coverage | command line, from `engine/`: `uv run mcplain --local tests/fixtures/python_partial_tracking --json` |
| `orange-partial.result.json` | orange, O08, read in part, with coverage | command line, from `engine/`: `uv run mcplain --local tests/fixtures/corpus/orange/native-launcher --json` |
| `install-command.result.json` | orange, O10 with the client name | command line, from `engine/`: `uv run mcplain --local tests/fixtures/rules/O10/positive --json` |
| `install-request.result.json` | orange, O11 with the domain | command line, from `engine/`: `uv run mcplain --local tests/fixtures/rules/O11/positive --json` |

`*.view.json` files are what the API answers; `*.result.json` files are engine results, wrapped in a view by
the test helpers (`tests/unit/reports.ts`, `tests/e2e/reports.ts`). Generate them again after a change of the
engine output, with the stack built from the same commit (`docker compose build atelier`, then
`docker compose up -d --build`).

## ALTCHA challenge of the simulated API

`altcha-challenge.json` is a challenge of cost 1 that expires in 2099, signed with a test only key. The simulated API of
`pnpm test:e2e` (`tests/e2e/messages-server.mjs`) serves it on `GET /api/altcha/challenge`, so that the invisible widget
solves it as in a real browser. It was made from `api/` with
`uv run python -c "...create_challenge('PBKDF2/SHA-256', 1, expires_at=datetime(2099, 1, 1, tzinfo=UTC), hmac_secret=...)..."`.
The real API never accepts it: its key is another one.
