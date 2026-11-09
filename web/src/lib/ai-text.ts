import type { Message, Tool } from "./analysis";

export const AI_STATUSES = ["ready", "pending", "rejected", "failed", "paused", "disabled", "none", "template"] as const;
export const AI_RESUMES = ["tomorrow", "next_month", "later"] as const;
export const WAITING_STATUSES: readonly AiStatus[] = ["pending", "none"];

export type AiStatus = (typeof AI_STATUSES)[number];
export type AiResume = (typeof AI_RESUMES)[number];
export type AiKind = "notice" | "translation";

export type ToolTitle = { tool_index: number; title: string; sentence: string };

export type NoticeContent = {
  summary: string;
  use_cases: string[];
  tool_titles: ToolTitle[];
  alert: string | null;
};

export type TranslationItem = { id: string; text: string };

export type TranslationContent = { items: TranslationItem[] };

export type FallbackNotice = { variant: "tools" | "no_tools"; messages: Message[]; actions: string[] };

export type AiAnswer<Content> = {
  status: AiStatus;
  source: "ai" | "template";
  fallback: FallbackNotice | null;
  content: Content | null;
  resume: AiResume | null;
};

export type NoticeAnswer = AiAnswer<NoticeContent>;
export type TranslationAnswer = AiAnswer<TranslationContent>;

type Fields = Record<string, unknown>;

class InvalidAnswer extends Error {}

function fail(): never {
  throw new InvalidAnswer("the API answered with an unexpected shape");
}

function fieldsOf(value: unknown): Fields {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail();
  }
  return value as Fields;
}

function textOf(value: unknown): string {
  if (typeof value !== "string") {
    fail();
  }
  return value;
}

function listOf<T>(value: unknown, item: (entry: unknown) => T): T[] {
  if (!Array.isArray(value)) {
    fail();
  }
  return value.map(item);
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  const candidate = textOf(value);
  if (!(allowed as readonly string[]).includes(candidate)) {
    fail();
  }
  return candidate as T;
}

function message(value: unknown): Message {
  const fields = fieldsOf(value);
  const params: Record<string, string> = {};
  for (const [key, entry] of Object.entries(fieldsOf(fields.params))) {
    params[key] = textOf(entry);
  }
  return { code: textOf(fields.code), params };
}

function fallbackNotice(value: unknown): FallbackNotice | null {
  if (value === null || value === undefined) {
    return null;
  }
  const fields = fieldsOf(value);
  return {
    variant: oneOf(fields.variant, ["tools", "no_tools"] as const),
    messages: listOf(fields.messages, message),
    actions: listOf(fields.actions, textOf),
  };
}

function toolTitle(value: unknown): ToolTitle {
  const fields = fieldsOf(value);
  if (typeof fields.tool_index !== "number" || !Number.isInteger(fields.tool_index)) {
    fail();
  }
  return { tool_index: fields.tool_index, title: textOf(fields.title), sentence: textOf(fields.sentence) };
}

function noticeContent(value: unknown): NoticeContent {
  const fields = fieldsOf(value);
  let alert: string | null = null;
  if (fields.alert !== null && fields.alert !== undefined) {
    alert = textOf(fields.alert);
  }
  return {
    summary: textOf(fields.summary),
    use_cases: listOf(fields.use_cases, textOf),
    tool_titles: listOf(fields.tool_titles, toolTitle),
    alert,
  };
}

function translationItem(value: unknown): TranslationItem {
  const fields = fieldsOf(value);
  return { id: textOf(fields.id), text: textOf(fields.text) };
}

function translationContent(value: unknown): TranslationContent {
  return { items: listOf(fieldsOf(value).items, translationItem) };
}

function answerOf<Content>(value: unknown, content: (entry: unknown) => Content): AiAnswer<Content> {
  const fields = fieldsOf(value);
  let parsed: Content | null = null;
  if (fields.content !== null && fields.content !== undefined) {
    parsed = content(fields.content);
  }
  let resume: AiResume | null = null;
  if (fields.resume !== null && fields.resume !== undefined) {
    resume = oneOf(fields.resume, AI_RESUMES);
  }
  return {
    status: oneOf(fields.status, AI_STATUSES),
    source: oneOf(fields.source, ["ai", "template"] as const),
    fallback: fallbackNotice(fields.fallback),
    content: parsed,
    resume,
  };
}

function guarded<T>(read: () => T): T | null {
  try {
    return read();
  } catch (error) {
    if (error instanceof InvalidAnswer) {
      return null;
    }
    throw error;
  }
}

export function parseNoticeAnswer(value: unknown): NoticeAnswer | null {
  return guarded(() => answerOf(value, noticeContent));
}

export function parseTranslationAnswer(value: unknown): TranslationAnswer | null {
  return guarded(() => answerOf(value, translationContent));
}

export function isWaiting(status: AiStatus): boolean {
  return WAITING_STATUSES.includes(status);
}

export function withPlainTitles(tools: Tool[], answer: NoticeAnswer | null): Tool[] {
  if (answer === null || answer.content === null) {
    return tools;
  }
  const titles = new Map(answer.content.tool_titles.map((title) => [title.tool_index, title]));
  return tools.map((tool, index) => {
    const title = titles.get(index);
    if (title === undefined) {
      return tool;
    }
    return { ...tool, plain_title: title.title, plain_sentence: title.sentence };
  });
}

export function translationOfTool(answer: TranslationAnswer | null, index: number): string | null {
  if (answer === null || answer.content === null) {
    return null;
  }
  const found = answer.content.items.find((item) => item.id === `tool_${index}`);
  if (found === undefined) {
    return null;
  }
  return found.text;
}
