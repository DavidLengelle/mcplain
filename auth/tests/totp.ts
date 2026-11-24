import { createHmac } from "node:crypto";

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
const PERIOD_SECONDS = 30;
const DIGITS = 6;

export function base32Bytes(text: string): Buffer {
  let bits = "";
  for (const letter of text.replace(/=+$/, "").toUpperCase()) {
    const value = BASE32.indexOf(letter);
    if (value < 0) {
      throw new Error("not base32");
    }
    bits += value.toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(Number.parseInt(bits.slice(index, index + 8), 2));
  }
  return Buffer.from(bytes);
}

export function secretOf(totpUri: string): string {
  return new URL(totpUri).searchParams.get("secret") ?? "";
}

export function totpCode(secret: string, moment: number = Date.now(), shift: number = 0): string {
  const counter = Math.floor(moment / 1000 / PERIOD_SECONDS) + shift;
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(BigInt(counter));
  const digest = createHmac("sha1", base32Bytes(secret)).update(message).digest();
  const offset = (digest[digest.length - 1] ?? 0) & 0x0f;
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 10 ** DIGITS;
  return value.toString().padStart(DIGITS, "0");
}

export function wrongCode(secret: string): string {
  const right = new Set([totpCode(secret, Date.now(), -1), totpCode(secret), totpCode(secret, Date.now(), 1)]);
  let candidate = 0;
  while (right.has(candidate.toString().padStart(DIGITS, "0"))) {
    candidate += 1;
  }
  return candidate.toString().padStart(DIGITS, "0");
}
