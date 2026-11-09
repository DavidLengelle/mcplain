"use client";

import { useEffect, useState } from "react";

import { isWaiting, type AiAnswer, type AiKind } from "@/lib/ai-text";
import { askAiText, readAiText } from "@/lib/api-client";

export const AI_POLL_MILLISECONDS = 2000;
export const AI_MAX_WAIT_MILLISECONDS = 30 * 1000;

export type AiTextState<Content> = { answer: AiAnswer<Content> | null; waiting: boolean };

export function useAiText<Content>(
  kind: AiKind,
  id: string,
  lang: string,
  enabled: boolean,
  parse: (value: unknown) => AiAnswer<Content> | null,
): AiTextState<Content> {
  const [state, setState] = useState<AiTextState<Content>>({ answer: null, waiting: false });

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const controller = new AbortController();
    const started = Date.now();
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    function follow(answer: AiAnswer<Content> | null, previous: AiAnswer<Content> | null) {
      if (!active) {
        return;
      }
      const shown = answer ?? previous;
      if (answer === null || !isWaiting(answer.status)) {
        setState({ answer: shown, waiting: false });
        return;
      }
      if (Date.now() - started >= AI_MAX_WAIT_MILLISECONDS) {
        setState({ answer: shown, waiting: false });
        return;
      }
      setState({ answer: shown, waiting: true });
      timer = setTimeout(() => {
        readAiText(id, kind, lang, controller.signal).then((value) => follow(parse(value), shown));
      }, AI_POLL_MILLISECONDS);
    }

    askAiText(id, kind, lang, controller.signal).then((value) => follow(parse(value), null));
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [enabled, id, kind, lang, parse]);

  return state;
}
