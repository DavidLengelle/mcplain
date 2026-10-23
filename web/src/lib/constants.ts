export const SOURCE_CODE_URL = "https://github.com/DavidLengelle/mcplain";
export const TOP_ID = "top";
export const SHEET_ID = "fiche";
export const DETAILS_ID = "details";
export const TOOL_ZONE_ID = "analyser";

export const EXAMPLES = [
  "uvx mcp-server-fetch",
  "npx -y @modelcontextprotocol/server-filesystem",
  "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
];

export const CHAPTER_IDS = ["mcp", "usage", "danger", "histoire", "proteger", "lire", "exemple", "limites", "lexique"] as const;

export type ChapterId = (typeof CHAPTER_IDS)[number];

export const GUIDE_SOURCES = {
  mcpIntro: "https://modelcontextprotocol.io/docs/getting-started/intro",
  toolPoisoning: "https://invariantlabs.ai/blog/mcp-security-notification",
  lethalTrifecta: "https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/",
  postmark: "https://postmarkapp.com/blog/information-regarding-malicious-postmark-mcp-package",
  darkReading: "https://www.darkreading.com/application-security/malicious-mcp-server-exfiltrates-secrets-bcc",
  hackerNews: "https://thehackernews.com/2025/09/first-malicious-mcp-server-found.html",
} as const;

export const POSTMARK_CLEAN_VERSIONS_START = ["1.0.0", "1.0.1", "1.0.2"];
export const POSTMARK_CLEAN_VERSIONS_END = ["1.0.14", "1.0.15"];
export const POSTMARK_TRAPPED_VERSION = "1.0.16";

const URL_SCHEME = /^https:\/\//;

export function exampleLabel(example: string): string {
  return example.replace(URL_SCHEME, "");
}
