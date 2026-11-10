import type { Pool } from "pg";

export type MailKind = "verify_email" | "reset_password";

export type Mail = { kind: MailKind; lang: string; recipient: string; link: string };

export type Deposit = (mail: Mail) => Promise<void>;

export const LANG_HEADER = "x-mcplain-lang";
const LANGUAGES = new Set(["en", "fr"]);
const DEFAULT_LANG = "en";

export function mailLanguage(request: Request | undefined): string {
  const value = request?.headers.get(LANG_HEADER)?.trim().toLowerCase();
  if (value !== undefined && LANGUAGES.has(value)) {
    return value;
  }
  return DEFAULT_LANG;
}

export function outboxDeposit(pool: Pool): Deposit {
  return async (mail) => {
    await pool.query(
      "INSERT INTO public.mail_outbox (id, kind, lang, recipient, link, created_at) VALUES ($1, $2, $3, $4, $5, now())",
      [crypto.randomUUID(), mail.kind, mail.lang, mail.recipient, mail.link],
    );
  };
}
