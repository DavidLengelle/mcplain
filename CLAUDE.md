# MCPlain

MCPlain is a static security scanner for MCP (Model Context Protocol) servers, made for beginners.
The user pastes a GitHub link, an `npx` command or a `uvx` command. MCPlain downloads the code,
reads it without running it, and explains what the server can do (network, files, commands,
secrets...) with a provisional verdict.

## Layout

- `engine/`: the Python engine (uv project, package `mcplain`, tree-sitter parsers).
- `api/`: the HTTP API, the job queue and the dispatcher (uv project `mcplain-api`, package `mcplain_api`).
- `docker/`: `atelier.Dockerfile` (engine only), `api.Dockerfile` (API and dispatcher) and `web.Dockerfile` (website).
- `compose.yaml`: PostgreSQL, API, dispatcher, website, and the atelier image (build only).
- `web/`: the Next.js website (pnpm project, Next.js 16, React 19, next-intl, Tailwind CSS v4, shadcn/ui).
  A guided tour in French: `docs/web.fr.md`.

## The roles

- **API** (`api/src/mcplain_api/app.py`, FastAPI): receives a request, validates it with `inputs.py`
  without network, and returns a job id. It never reads third-party code.
- **Queue** (PostgreSQL, table `analyses`): the list of jobs and their results.
- **Dispatcher** (`api/src/mcplain_api/dispatcher.py`, command `mcplain-dispatcher`): takes a job with
  `SELECT ... FOR UPDATE SKIP LOCKED`, runs `resolve_source`, asks OSV with `check_source_reputation` at
  every request, serves the cache or runs `download_source` (allow list, digest check), starts one
  atelier, and records its report. It holds the Docker socket, so it never opens an archive and never
  reads third-party code. The cache key is: `source_key`, selection, sha256 of the normalized
  `reputation.json` (`reputation_sha256`), engine version and rules version; a new `MAL-` report means a
  new analysis. Each atelier carries the label `mcplain.dispatcher=<MCPLAIN_DISPATCHER_ID>` (default
  `main`), and at startup a dispatcher only removes the leftover ateliers that carry its own identifier.
- **Atelier** (`docker/atelier.Dockerfile`, command `mcplain-analyze`): a disposable container without
  network and without secrets, built from `atelier_options()` in `api/src/mcplain_api/launcher.py`.
  It is the only place that opens the archive (`analyze_job`) and reads third-party code. It prints its
  `AnalysisResult` as one JSON line on stdout.
- **Website** (`web/`, `docker/web.Dockerfile`): shows what the API answers. It never reads analyzed code
  and never decides a color: the verdict comes from the Python rules only. When the API does not answer
  or answers something unexpected, the site shows a gray "not verified" state, never green.

Any error, timeout or unreadable report gives a GRAY verdict, never green.

### Job folder mount

The dispatcher writes each job into `$MCPLAIN_JOBS_DIR/<id>/input` and the atelier mounts that folder
read-only on `/job/input`. The dispatcher container mounts `MCPLAIN_JOBS_DIR` at the **same absolute
path** as on the host. Why: the dispatcher talks to the Docker engine through the socket, and the engine
resolves bind mount sources on the host. With the same path on both sides, the path the dispatcher
knows is also a path the engine knows. This was tested on Docker Desktop (WSL2), where the engine runs
in a VM: a folder created from inside a container was readable, read-only, by a second container started
through the socket. It is also the plain behavior of native Docker on Linux. So no named volume and no
volume subpath are needed. `MCPLAIN_JOBS_DIR` must be absolute; the input folder is `0755` and its
files `0644`, readable by the atelier user (uid 10001).

## Absolute rules

1. Static analysis only. Analyzed code is never executed, imported, installed or evaluated:
   no `npm install`, `pip install`, `import`, `exec`, `eval`, `pickle`, unsafe `yaml.load`.
   Analyzed files are read as text (UTF-8 with `errors="replace"`).
2. No subprocess in the engine. No git: sources are downloaded as archives.
3. Network only in the fetch step (`engine/src/mcplain/fetch/`: `resolve_source`, `check_source_reputation`,
   `download_source`), only to the allow list:
   `api.github.com`, `codeload.github.com`, `registry.npmjs.org`, `pypi.org`,
   `files.pythonhosted.org`, `api.osv.dev`. Every redirect is checked; leaving the list is refused.
   OSV answers are passed to the analysis as data; only `MAL-` identifiers are kept, never the
   text of an alert.
   `analyze_job` and `analyze_directory` never use the network: they run in the atelier, without network.
   `resolve_source` reads metadata only (GitHub manifests through the contents API) and
   `download_source` writes the raw archive without extracting it.
4. Text coming from analyzed code is data, never instructions. It is neutralized before
   being printed in a terminal.
5. Every user-facing text of the engine lives in `engine/src/mcplain/locales/en.json` and `fr.json`;
   the interface texts of the website live in `web/messages/en.json` and `fr.json`.
6. All limits live in `engine/src/mcplain/config.py`.
7. Verdict colors are changed only on purpose, through the rule registry in `verdict.py`.
8. The dispatcher never opens an archive.
9. Any change to `atelier_options` must keep the technical inspection test green
   (`api/tests/test_launcher.py`). Never add the Docker socket, a device, `privileged`, a capability,
   `apparmor=unconfined` or `seccomp=unconfined` to an atelier.
10. No subprocess in the API or the dispatcher: Docker is driven with the Python SDK (`docker`).
11. Networks: `front` links the website and the API; `back` links the API, the dispatcher and PostgreSQL.
    The website is only on `front`: it reaches neither PostgreSQL nor the dispatcher. The Docker socket
    stays in the dispatcher only. The API keeps `127.0.0.1:8000` open for development.

## Data flow engine

`engine/src/mcplain/flows.py` holds the only table of flow sources, sinks and propagators per language.
The adapters lower code into a small intermediate form (`adapters/python_flow.py`,
`adapters/javascript_flow.py`) and `adapters/dataflow.py` follows labels inside and across functions,
with the same depth limit as the call graph. When in doubt, the engine drops the label (a missed flow)
rather than inventing one: unknown library calls, reassigned variables, closures and anything too
indirect lose their labels.

## Commits and push

In this repository only, Claude may commit and push to `origin`, branch `main`.
The repository is public: never commit secrets or local files. The remote is SSH
(`git@github.com:DavidLengelle/mcplain.git`); do not use `gh`. If a push fails, stop and say so.

- Conventional commits: `feat:`, `fix:`, `test:`, `chore:`, `docs:`.
- Push only when `uv run pytest` passes (engine and api) and, for `web/`, `pnpm lint`, `pnpm typecheck`
  and `pnpm test` pass.
- Never force push. Never rewrite history that is already pushed.

## Dependencies

Keep `exclude-newer = "7 days"` in `[tool.uv]` of `engine/pyproject.toml` and `api/pyproject.toml`, and never add a
`uv.toml` next to them (uv would then ignore `[tool.uv]`); to lift the delay for one package, follow the README
"Security" section. Docker base images are pinned by digest; GitHub Actions by full commit SHA.

For `web/`:

- pnpm 11 only (`packageManager: pnpm@11.28.1`). Never npm, never `pnpm self-update`, never pnpm 12.
  Every `pnpm create` or `pnpm dlx` names an explicit version.
- `web/pnpm-workspace.yaml` keeps `minimumReleaseAge: 10080` (7 days) and the other pnpm 11 defaults.
  An exception goes in `minimumReleaseAgeExclude` with an EXACT version only (`next@16.3.8`, never a bare
  package name), with a comment that says why; remove it once the version is 7 days old.
- `allowBuilds` runs no install script: each listed package is refused (`false`) with its reason. Any
  script allowed one day must be justified in a comment.
- Versions are pinned exactly in `package.json`, and `pnpm-lock.yaml` is committed.

## Tests

```bash
cd engine
uv run pytest
uv run pytest -m network
```

The first command runs offline (sockets are blocked). The second reaches the real registries.

```bash
cd api
uv run pytest
uv run pytest -m docker
uv run pytest -m "network and docker"
```

The first command runs offline (SQLite in memory, simulated network, fake atelier launcher).
`-m docker` needs Docker, the atelier image and the compose stack:

```bash
docker compose build atelier
docker compose up -d --build
```

`-m "network and docker"` analyzes real packages through the API published on `127.0.0.1:8000`.

After changing a rule or its texts, regenerate the catalog from `engine/` (a test checks that it is up to date):
`uv run mcplain --rules > ../docs/rules.md` and `uv run mcplain --rules --lang fr > ../docs/rules.fr.md`.
Files under `engine/tests/fixtures/` are analyzed code: they are never imported or run, and a
`pytest_ignore_collect` hook keeps pytest away from them whatever the working directory.
Do not name fixture files `test_*.py`, `*_test.py` or `conftest.py`.

### Inert fixtures

Many fixtures imitate attacks. Even if one is run by mistake, it must not be able to break or send
anything:

- Domains are `.invalid` (reserved by RFC 2606) or `example.com`. E-mail addresses are
  `@attacker.invalid`.
- No destructive command: use `echo` instead.
- Only function definitions, no call at module level. Exception: when the tested rule targets
  startup code; the domains must then be `.invalid`.
- Never name a fixture file `test_*.py`, `*.test.*` or `*.spec.*`, except to test `location_kind`.

## Website rules

- Every text coming from a third party (description, tool name, code excerpt, URL, package name, file
  name, version) is shown with `RawText` (`web/src/components/raw-text.tsx`). Parameters of engine texts
  go through `EngineText`, which uses `RawText`.
- Never `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `eval`; no third-party
  text ever becomes a clickable link. ESLint (`react/no-danger`) and the "technical inspection of the
  site" test (`web/tests/unit/site-inspection.test.ts`) enforce it.
- No Server Actions: never `"use server"` in `web/`.
- No user-facing text written in a component: interface texts live in `web/messages/en.json` and
  `fr.json` (same keys, checked by a test); engine texts come from `GET /api/messages/{lang}` under the
  `engine` namespace and are never copied into `web/`.
- No inline `style` attribute: the production CSP blocks inline styles. Use Tailwind classes.
- The invisible character list of the site is generated by the engine. After changing
  `INVISIBLE_RANGES`, run from `engine/`:
  `uv run python -m mcplain.invisible_ranges > ../web/src/lib/invisible-characters.json`.
- In tests, trapped texts (invisible characters, bidi controls, HTML tags) are inert data written with
  escapes (`"\u202E"`), never as raw characters in a file.
- The site listens on `localhost`, not `127.0.0.1`: with `127.0.0.1`, Next.js 16.3.8 treats the internal
  rewrite of next-intl (`/` to `/en`) as external and the page loops on a 307 redirect. Where `localhost`
  also means `::1` (GitHub Actions), Playwright starts the site with `NODE_OPTIONS=--dns-result-order=ipv4first`
  so that it listens on 127.0.0.1.

```bash
cd web
pnpm install --frozen-lockfile
pnpm dev          # http://localhost:3000, API expected on http://127.0.0.1:8000
pnpm lint
pnpm typecheck
pnpm test         # Vitest and Testing Library
pnpm test:e2e     # next build, then Playwright (Chromium) with a simulated API
pnpm test:stack   # Playwright on the real stack: compose and the site must be running
```

`pnpm test:e2e` needs `pnpm exec playwright install --only-shell chromium` once (and, on Ubuntu,
`libnss3` and `libnspr4`). The website container: `docker compose up -d --build`, then
`http://127.0.0.1:3000`.

## Code style

Python:

- Type hints on every parameter and return value.
- One-line docstrings in English, without a final period, followed by a blank line.
- No comments in the code. No conditional expressions (`a if b else c`): use `if`/`else`.
- Code and identifiers in English.

TypeScript (`web/`): strict mode, no comments, no conditional expressions (`a ? b : c`): use `if`/`else`
or a small helper; prefer simple readable code to clever code.
