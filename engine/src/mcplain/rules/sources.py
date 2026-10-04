"""Public sources quoted by the rule cards"""

from mcplain.rules.base import RuleSource

OWASP_MCP = "https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025"

OWASP_MCP01 = RuleSource(
    "OWASP MCP Top 10, MCP01:2025 Token Mismanagement and Secret Exposure",
    f"{OWASP_MCP}/MCP01-2025-Token-Mismanagement-and-Secret-Exposure.md",
)
OWASP_MCP02 = RuleSource(
    "OWASP MCP Top 10, MCP02:2025 Privilege Escalation via Scope Creep",
    f"{OWASP_MCP}/MCP02-2025%E2%80%93Privilege-Escalation-via-Scope-Creep.md",
)
OWASP_MCP03 = RuleSource(
    "OWASP MCP Top 10, MCP03:2025 Tool Poisoning",
    f"{OWASP_MCP}/MCP03-2025%E2%80%93Tool-Poisoning.md",
)
OWASP_MCP04 = RuleSource(
    "OWASP MCP Top 10, MCP04:2025 Software Supply Chain Attacks & Dependency Tampering",
    f"{OWASP_MCP}/MCP04-2025%E2%80%93Software-Supply-Chain-Attacks%26Dependency-Tampering.md",
)
OWASP_MCP05 = RuleSource(
    "OWASP MCP Top 10, MCP05:2025 Command Injection & Execution",
    f"{OWASP_MCP}/MCP05-2025%E2%80%93Command-Injection%26Execution.md",
)
OWASP_MCP06 = RuleSource(
    "OWASP MCP Top 10, MCP06:2025 Intent Flow Subversion",
    f"{OWASP_MCP}/MCP06-2025%E2%80%93Intent-Flow-Subversion.md",
)
OWASP_LLM01 = RuleSource(
    "OWASP Top 10 for LLM Applications, LLM01:2025 Prompt Injection",
    "https://genai.owasp.org/llmrisk/llm01-prompt-injection/",
)
OWASP_LLM06 = RuleSource(
    "OWASP Top 10 for LLM Applications, LLM06:2025 Excessive Agency",
    "https://genai.owasp.org/llmrisk/llm062025-excessive-agency/",
)
REHBERGER_TAGS = RuleSource(
    "Johann Rehberger, Hiding and finding text with Unicode Tags (Embrace The Red, 2024)",
    "https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/",
)
TROJAN_SOURCE = RuleSource("Trojan Source, CVE-2021-42574", "https://trojansource.codes/")
INVARIANT_POISONING = RuleSource(
    "Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)",
    "https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks",
)
CWE_78 = RuleSource("CWE-78: OS Command Injection", "https://cwe.mitre.org/data/definitions/78.html")
CWE_201 = RuleSource(
    "CWE-201: Insertion of Sensitive Information Into Sent Data",
    "https://cwe.mitre.org/data/definitions/201.html",
)
CWE_494 = RuleSource(
    "CWE-494: Download of Code Without Integrity Check",
    "https://cwe.mitre.org/data/definitions/494.html",
)
CWE_506 = RuleSource("CWE-506: Embedded Malicious Code", "https://cwe.mitre.org/data/definitions/506.html")
SHAI_HULUD = RuleSource(
    "Unit 42, Shai-Hulud worm compromises the npm ecosystem (September 2025)",
    "https://unit42.paloaltonetworks.com/npm-supply-chain-attack/",
)
SHAI_HULUD_PREINSTALL = RuleSource(
    "Datadog Security Labs, Shai-Hulud 2.0 moves to preinstall (November 2025)",
    "https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/",
)
POSTMARK = RuleSource(
    "Koi Security, postmark-mcp 1.0.16 adds a hidden BCC (September 2025, reported by The Hacker News)",
    "https://thehackernews.com/2025/09/first-malicious-mcp-server-found.html",
)
OPENSSF_MALICIOUS = RuleSource("OpenSSF Malicious Packages", "https://github.com/ossf/malicious-packages")
OSV = RuleSource("OSV.dev", "https://osv.dev/")
OSV_SETUP_PY = RuleSource(
    "OSV MAL-2024-11608: setup.py that takes over the install command",
    "https://osv.dev/vulnerability/MAL-2024-11608",
)
ATTACK_T1105 = RuleSource("MITRE ATT&CK T1105: Ingress Tool Transfer", "https://attack.mitre.org/techniques/T1105/")
ATTACK_T1546_004 = RuleSource(
    "MITRE ATT&CK T1546.004: Unix Shell Configuration Modification",
    "https://attack.mitre.org/techniques/T1546/004/",
)
ATTACK_T1098_004 = RuleSource(
    "MITRE ATT&CK T1098.004: SSH Authorized Keys",
    "https://attack.mitre.org/techniques/T1098/004/",
)
LETHAL_TRIFECTA = RuleSource(
    "Simon Willison, The lethal trifecta for AI agents (2025)",
    "https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/",
)
MCP_ANNOTATIONS = RuleSource(
    "Model Context Protocol specification, tool annotations are untrusted hints",
    "https://modelcontextprotocol.io/specification/2025-11-25/server/tools",
)
MCPLAIN_RULE = RuleSource(
    "MCPlain founding rule: text from analyzed code is data, never instructions",
    "https://github.com/DavidLengelle/mcplain/blob/main/CLAUDE.md",
)
