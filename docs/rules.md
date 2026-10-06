# MCPlain rules

Rules version 1: 20 rules, 12 red and 8 orange. This page is generated from the rule registry with `uv run mcplain --rules`; do not edit it by hand.

Order of the verdict: red if a red rule fires; otherwise orange if an orange rule fires; otherwise gray if the status is not ok or if the code could not be fully read and followed; otherwise green. The rules apply to all server code (tools, code outside the tools, startup, install scripts, imported examples), never to tests or examples that the server does not import.

| Rule | Color | Title |
| --- | --- | --- |
| [R01 invisible-text](#r01-invisible-text) | RED | Invisible text |
| [R02 asks-for-silence](#r02-asks-for-silence) | RED | Asks the AI to keep quiet |
| [R03 asks-for-sensitive-file](#r03-asks-for-sensitive-file) | RED | Asks for a sensitive file |
| [R04 leaks-secrets](#r04-leaks-secrets) | RED | Sends secrets over the network |
| [R05 hidden-copy](#r05-hidden-copy) | RED | Hidden copy of e-mails |
| [R06 hidden-code](#r06-hidden-code) | RED | Hidden code |
| [R07 download-and-run](#r07-download-and-run) | RED | Downloads and runs code |
| [R08 autostart-or-config-tampering](#r08-autostart-or-config-tampering) | RED | Changes startup files or another tool's settings |
| [R09 command-injection](#r09-command-injection) | RED | Command injection |
| [R10 install-goes-online](#r10-install-goes-online) | RED | Goes online at install time |
| [R11 known-malicious](#r11-known-malicious) | RED | Known malicious package |
| [R12 talks-to-the-analyzer](#r12-talks-to-the-analyzer) | RED | Talks to the analyzer |
| [O01 open-network](#o01-open-network) | ORANGE | Can contact any address |
| [O02 ai-chooses-the-command](#o02-ai-chooses-the-command) | ORANGE | The AI chooses the command |
| [O03 description-from-internet](#o03-description-from-internet) | ORANGE | Description downloaded from the Internet |
| [O04 annotation-mismatch](#o04-annotation-mismatch) | ORANGE | Hints contradicted by the code |
| [O05 mentions-sensitive-path](#o05-mentions-sensitive-path) | ORANGE | Mentions a sensitive path |
| [O06 dependency-was-malicious](#o06-dependency-was-malicious) | ORANGE | A dependency had malicious versions |
| [O07 lone-invisible-char](#o07-lone-invisible-char) | ORANGE | Lone invisible character |
| [O08 powerful-capability](#o08-powerful-capability) | ORANGE | Powerful capability |

## The lamps

Every report shows six lamps, for the server and for each tool. A capability found in the code that counts for the verdict lights the lamp: it turns white, for information. A red rule that fires turns it to danger: it turns red. Orange rules never light a red lamp. A plain environment variable read (PORT, LOG_LEVEL) lights nothing. R11 (known malicious package) lights no lamp: it shows in the list of alerts. This table is generated from `engine/src/mcplain/lamps.py`.

| Lamp | Identifier | Lit by | Red when |
| --- | --- | --- | --- |
| Reads your files | `files_read` | `fs_read` | none |
| Changes your files | `files_write` | `fs_write` | R08 |
| Goes on the Internet | `internet` | `network` | R04, R05, R07, R10 |
| Runs commands | `commands` | `dynamic_code`, `install_script`, `process_exec` | R07, R09, R10 |
| Touches your secrets | `secrets` | `env_read_secret`, `sensitive_path` | R03, R04 |
| Hidden text | `hidden_text` | invisible characters found | R01, R02, R06, R12 |

## R01 invisible-text

**Invisible text**: RED, suspicious use.

A tool name or description contains invisible characters that hide text: you cannot see it, but the AI reads it. This is how hidden instructions are slipped to an AI. Bidirectional controls written in the code can also make the code look different from what runs.

- In plain words: **Text hidden from you**. Invisible characters hide text in a tool or in the code. You cannot see them, but the AI reads them. Advice: Do not install it. A tool has no need to hide text from the AI.
- Visible when reading the code: no
- Known false positive: Text pasted from a word processor that carries two zero-width spaces.
- Sources:
  - [Johann Rehberger, Hiding and finding text with Unicode Tags (Embrace The Red, 2024)](https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/)
  - [Trojan Source, CVE-2021-42574](https://trojansource.codes/)
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
- Test fixtures: `engine/tests/fixtures/rules/R01/` (positive, near_miss, false_positive)

## R02 asks-for-silence

**Asks the AI to keep quiet**: RED, suspicious use.

A description asks the AI not to tell you what it or the tool is doing. A tool has no honest reason to hide its actions from you.

- In plain words: **Asks the AI to hide things from you**. A description asks the AI not to tell you what the tool does. Advice: Do not install it. A tool has no honest reason to hide what it does from you.
- Visible when reading the code: yes
- Known false positive: "If the request fails, retry silently: do not tell the user about it."
- Sources:
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
- Test fixtures: `engine/tests/fixtures/rules/R02/` (positive, near_miss, false_positive)

## R03 asks-for-sensitive-file

**Asks for a sensitive file**: RED, suspicious use.

A description names a sensitive file (SSH keys, credentials, configuration) and asks the AI to put its content into a tool argument. The AI would read the file and hand it to the tool.

- In plain words: **Asks the AI for a secret file**. A description asks the AI to read a sensitive file, like your SSH keys, and to give its content to the tool. Advice: Do not install it. If you already used it, change the keys or passwords in that file.
- Visible when reading the code: yes
- Known false positive: "Paste the contents of your ~/.ssh/config into the 'config' parameter to check it for errors." (an SSH configuration checker)
- Sources:
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
- Test fixtures: `engine/tests/fixtures/rules/R03/` (positive, near_miss, false_positive)

## R04 leaks-secrets

**Sends secrets over the network**: RED, suspicious use.

This code reads a secret file (for example your SSH keys) or all your environment variables at once, and sends them over the network.

- In plain words: **Sends your secrets over the Internet**. The code reads a secret file or all your environment variables, then sends them over the network. Advice: Do not install it. If it is already installed, remove it and change your keys and passwords.
- Visible when reading the code: yes
- Known false positive: A dotfiles backup tool that sends ~/.ssh/config to the user's own Gist.
- Sources:
  - [OWASP MCP Top 10, MCP01:2025 Token Mismanagement and Secret Exposure](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP01-2025-Token-Mismanagement-and-Secret-Exposure.md)
  - [CWE-201: Insertion of Sensitive Information Into Sent Data](https://cwe.mitre.org/data/definitions/201.html)
  - [Unit 42, Shai-Hulud worm compromises the npm ecosystem (September 2025)](https://unit42.paloaltonetworks.com/npm-supply-chain-attack/)
- Test fixtures: `engine/tests/fixtures/rules/R04/` (positive, near_miss, false_positive)

## R05 hidden-copy

**Hidden copy of e-mails**: RED, suspicious use.

This code adds an e-mail address written in the code as a copy (cc or bcc) of the messages it sends. Every e-mail sent through the tool would also go to that address.

- In plain words: **Hidden copy of your e-mails**. Every e-mail also goes, as a hidden copy, to an address written in the code. Advice: Do not install it. If it is already installed, remove it and change the key of your e-mail service.
- Visible when reading the code: yes
- Known false positive: Legal archiving: a fixed Bcc to the company's archive address.
- Sources:
  - [Koi Security, postmark-mcp 1.0.16 adds a hidden BCC (September 2025, reported by The Hacker News)](https://thehackernews.com/2025/09/first-malicious-mcp-server-found.html)
- Test fixtures: `engine/tests/fixtures/rules/R05/` (positive, near_miss, false_positive)

## R06 hidden-code

**Hidden code**: RED, suspicious use.

This code decodes text stored in the package (base64, hexadecimal, character codes...) and runs it. The real code is hidden from anyone who reads the source.

- In plain words: **Hidden code**. The code decodes a text stored in the package, then runs it. What really runs cannot be read in the code. Advice: Do not install it until someone has been able to read this hidden code.
- Visible when reading the code: yes
- Known false positive: An SSH server that embeds a small base64 startup script and runs it on the remote machine.
- Sources:
  - [CWE-506: Embedded Malicious Code](https://cwe.mitre.org/data/definitions/506.html)
  - [OpenSSF Malicious Packages](https://github.com/ossf/malicious-packages)
- Test fixtures: `engine/tests/fixtures/rules/R06/` (positive, near_miss, false_positive)

## R07 download-and-run

**Downloads and runs code**: RED, suspicious use.

This code downloads something from the Internet and runs it (eval, a shell, or a file written then executed). What runs can change at any time, without a new version of the package.

- In plain words: **Downloads code and runs it**. The code downloads something from the Internet and runs it. What runs can change at any time, without a new version. Advice: Do not install it, unless you know exactly what it downloads and from where.
- Visible when reading the code: yes
- Known false positive: Installing uv when it is missing, with the official command curl -LsSf https://astral.sh/uv/install.sh | sh.
- Sources:
  - [CWE-494: Download of Code Without Integrity Check](https://cwe.mitre.org/data/definitions/494.html)
  - [MITRE ATT&CK T1105: Ingress Tool Transfer](https://attack.mitre.org/techniques/T1105/)
- Test fixtures: `engine/tests/fixtures/rules/R07/` (positive, near_miss, false_positive)

## R08 autostart-or-config-tampering

**Changes startup files or another tool's settings**: RED, suspicious use.

This code writes to a file that starts programs automatically (.bashrc, crontab, authorized_keys, LaunchAgents...) or to the configuration of another tool (MCP clients, .npmrc, .gitconfig...). It can make code come back later, or change how your other tools behave.

- In plain words: **Changes your startup or your other tools**. The code writes to a file that starts programs on its own (like .bashrc or crontab), or to the settings of another tool. Advice: Do not install it. If it already ran, check those files and remove what you did not add yourself.
- Visible when reading the code: yes
- Known false positive: An installer MCP that adds itself to claude_desktop_config.json, when the user asks for it.
- Sources:
  - [MITRE ATT&CK T1546.004: Unix Shell Configuration Modification](https://attack.mitre.org/techniques/T1546/004/)
  - [MITRE ATT&CK T1098.004: SSH Authorized Keys](https://attack.mitre.org/techniques/T1098/004/)
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- Test fixtures: `engine/tests/fixtures/rules/R08/` (positive, near_miss, false_positive)

## R09 command-injection

**Command injection**: RED, serious flaw: the author is probably honest, but the flaw is serious.

A tool parameter is pasted into a command run by a shell. The author is probably honest, but the flaw is serious: a crafted value (for example with ; or $( )) runs any command on your machine, and the AI can be tricked into sending it.

- In plain words: **Flaw: a command can be hijacked**. A tool pastes a value from the AI into a command. A trapped value can run any command on your computer. The author probably did not mean it. Advice: Do not use it until the flaw is fixed. You can report it to the author.
- Visible when reading the code: yes
- Known false positive: A parameter checked with a regex just before it is pasted. MCPlain does not understand the check.
- Sources:
  - [OWASP MCP Top 10, MCP05:2025 Command Injection & Execution](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP05-2025%E2%80%93Command-Injection%26Execution.md)
  - [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- Test fixtures: `engine/tests/fixtures/rules/R09/` (positive, near_miss, false_positive)

## R10 install-goes-online

**Goes online at install time**: RED, suspicious use.

A script that runs when the package is installed (preinstall, install, postinstall, setup.py) downloads something or uses the network. It runs before you have even started the server.

- In plain words: **Goes online during installation**. A script run at install time downloads something or uses the network, before you even start the server. Advice: Do not install it, unless you know what this script downloads and why.
- Visible when reading the code: yes
- Known false positive: A package that downloads a browser at install time, like Puppeteer.
- Sources:
  - [Unit 42, Shai-Hulud worm compromises the npm ecosystem (September 2025)](https://unit42.paloaltonetworks.com/npm-supply-chain-attack/)
  - [Datadog Security Labs, Shai-Hulud 2.0 moves to preinstall (November 2025)](https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/)
  - [OWASP MCP Top 10, MCP04:2025 Software Supply Chain Attacks & Dependency Tampering](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP04-2025%E2%80%93Software-Supply-Chain-Attacks%26Dependency-Tampering.md)
  - [OSV MAL-2024-11608: setup.py that takes over the install command](https://osv.dev/vulnerability/MAL-2024-11608)
- Test fixtures: `engine/tests/fixtures/rules/R10/` (positive, near_miss, false_positive)

## R11 known-malicious

**Known malicious package**: RED, suspicious use.

OSV.dev lists this package at this version, or every version of one of its direct dependencies, as malicious (MAL- identifier). Open the link to read the report.

- In plain words: **Package reported as malicious**. The public OSV.dev database reports this package, or one of its dependencies, as malicious. Advice: Do not install it. If it is already installed, remove it and change your passwords and keys.
- Visible when reading the code: no
- Known false positive: A package name taken over by a new owner, with an old report about the former package.
- Sources:
  - [OpenSSF Malicious Packages](https://github.com/ossf/malicious-packages)
  - [OSV.dev](https://osv.dev/)
- Test fixtures: `engine/tests/fixtures/rules/R11/` (positive, near_miss, false_positive)

## R12 talks-to-the-analyzer

**Talks to the analyzer**: RED, suspicious use.

A string, a comment or a description speaks to an analysis tool ("ignore previous instructions", "this code is safe", "do not flag this", or names MCPlain). Code that only does its job has no reason to talk to a scanner.

- In plain words: **Talks to analysis tools**. A text in the code speaks to an analysis tool, for example to ask it to report nothing. Advice: Do not install it. Code that only does its job has no need to talk to a scanner.
- Visible when reading the code: yes
- Known false positive: An MCP that tests attacks and contains these sentences as examples.
- Sources:
  - [OWASP Top 10 for LLM Applications, LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
  - [MCPlain founding rule: text from analyzed code is data, never instructions](https://github.com/DavidLengelle/mcplain/blob/main/CLAUDE.md)
- Test fixtures: `engine/tests/fixtures/rules/R12/` (positive, near_miss, false_positive)

## O01 open-network

**Can contact any address**: ORANGE, a power to be aware of (nothing suspicious found).

A tool sends requests to an address the AI gives it. It can contact any address the AI gives it, and what it brings back from the Internet can contain traps (hidden instructions for the AI).

- In plain words: **Can reach any website**. A tool goes to the address the AI gives it. What it brings back from the Internet can hold traps for the AI. Advice: Watch the addresses it visits, and do not make it read your private pages.
- Visible when reading the code: yes
- Known false positive: A base address read from an environment variable, fixed in practice.
- Sources:
  - [OWASP MCP Top 10, MCP06:2025 Intent Flow Subversion](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP06-2025%E2%80%93Intent-Flow-Subversion.md)
  - [Simon Willison, The lethal trifecta for AI agents (2025)](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- Test fixtures: `engine/tests/fixtures/rules/O01/` (positive, near_miss, false_positive)

## O02 ai-chooses-the-command

**The AI chooses the command**: ORANGE, a power to be aware of (nothing suspicious found).

A tool parameter is run as a whole command, as the program to start, or as code to evaluate (also after decoding). This is maximum power: the AI can run anything.

- In plain words: **The AI chooses the command to run**. A tool runs the command or the code the AI gives it. So the AI can run anything on your computer. Advice: Use it only if you approve each command before it runs.
- Visible when reading the code: yes
- Known false positive: A command checked against a fixed list before it runs.
- Sources:
  - [OWASP MCP Top 10, MCP05:2025 Command Injection & Execution](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP05-2025%E2%80%93Command-Injection%26Execution.md)
  - [OWASP Top 10 for LLM Applications, LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- Test fixtures: `engine/tests/fixtures/rules/O02/` (positive, near_miss, false_positive)

## O03 description-from-internet

**Description downloaded from the Internet**: ORANGE, a power to be aware of (nothing suspicious found).

A tool description is computed from a network response. The AI reads it, and it can change at any time without a new version of the package.

- In plain words: **Description from the Internet**. A tool description is downloaded at startup. It can change at any time, without a new version. Advice: Use it only if you trust the site this description comes from.
- Visible when reading the code: yes
- Known false positive: A server that builds its tools from the online OpenAPI document of the API it wraps (FastMCP.from_openapi).
- Sources:
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- Test fixtures: `engine/tests/fixtures/rules/O03/` (positive, near_miss, false_positive)

## O04 annotation-mismatch

**Hints contradicted by the code**: ORANGE, a power to be aware of (nothing suspicious found).

The tool says it is read-only (readOnlyHint), but its code writes files, runs commands or code, or sends data. Or it says it is closed to the outside world (openWorldHint set to false), but its code uses the network, even for a simple read. AI clients do not check these hints.

- In plain words: **Does more than it says**. The tool says it only reads, or that it stays offline, but its code writes, runs or sends something. Advice: Do not rely on what it says. Look at what its code can do instead.
- Visible when reading the code: yes
- Known false positive: A read-only search tool that writes a cache.
- Sources:
  - [Model Context Protocol specification, tool annotations are untrusted hints](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- Test fixtures: `engine/tests/fixtures/rules/O04/` (positive, near_miss, false_positive)

## O05 mentions-sensitive-path

**Mentions a sensitive path**: ORANGE, a power to be aware of (nothing suspicious found).

A description names a sensitive path (SSH keys, credentials, startup files, settings of other tools) without asking for its content. Check why the tool needs it.

- In plain words: **Mentions a sensitive file**. A description names a sensitive file, like your SSH keys, without asking for its content. Advice: Check why the tool needs this file before you use it.
- Visible when reading the code: yes
- Known false positive: An SSH manager that says it reads ~/.ssh/config to list your servers.
- Sources:
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- Test fixtures: `engine/tests/fixtures/rules/O05/` (positive, near_miss, false_positive)

## O06 dependency-was-malicious

**A dependency had malicious versions**: ORANGE, a power to be aware of (nothing suspicious found).

OSV.dev lists some versions of a direct dependency as malicious (MAL- identifier). Check that the version installed with this server is not one of them.

- In plain words: **A dependency had malicious versions**. The OSV.dev database reports some versions of a package used by this server as malicious. Advice: Check that the version installed on your computer is not one of them.
- Visible when reading the code: no
- Known false positive: The version range declared by the package excludes those versions.
- Sources:
  - [OSV.dev](https://osv.dev/)
- Test fixtures: `engine/tests/fixtures/rules/O06/` (positive, near_miss, false_positive)

## O07 lone-invisible-char

**Lone invisible character**: ORANGE, a power to be aware of (nothing suspicious found).

A tool name or description contains one invisible character that its context does not explain. It is often harmless, but invisible characters can carry hidden text.

- In plain words: **One invisible character**. A tool name or description holds one invisible character. It is often left over from a copy and paste. Advice: Look at the reported passage. One character alone cannot hide a sentence.
- Visible when reading the code: no
- Known false positive: A single zero-width space left by a copy and paste.
- Sources:
  - [Johann Rehberger, Hiding and finding text with Unicode Tags (Embrace The Red, 2024)](https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/)
- Test fixtures: `engine/tests/fixtures/rules/O07/` (positive, near_miss, false_positive)

## O08 powerful-capability

**Powerful capability**: ORANGE, a power to be aware of (nothing suspicious found).

This code uses a powerful capability: running commands, writing or deleting files, reading secrets, running code built at runtime, quoting a sensitive path, or running code at install time. Some tools need it; check that this one really does.

- In plain words: **Can act on your computer**. The code can change files, run commands or touch secrets. Some tools need this. Advice: Check that this is what you want. Give it only the folder or the keys it needs.
- Visible when reading the code: yes
- Known false positive: A tool that only writes a temporary file in /tmp for its own use.
- Sources:
  - [OWASP Top 10 for LLM Applications, LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
  - [OWASP MCP Top 10, MCP02:2025 Privilege Escalation via Scope Creep](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP02-2025%E2%80%93Privilege-Escalation-via-Scope-Creep.md)
- Test fixtures: `engine/tests/fixtures/rules/O08/` (positive, near_miss, false_positive)
