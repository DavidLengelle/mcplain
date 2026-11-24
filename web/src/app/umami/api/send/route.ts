import {
  cleanSend,
  forwardedHeaders,
  proxyHops,
  readLimited,
  SEND_BODY_MAX_BYTES,
  umamiBaseUrl,
  visitorAddress,
  websiteId,
} from "@/lib/umami";

export const dynamic = "force-dynamic";

const JSON_MEDIA_TYPE = "application/json";
const ANSWER_MAX_CHARACTERS = 4096;
const TIMEOUT_MILLISECONDS = 5000;

function empty(status: number): Response {
  return new Response(null, { status, headers: { "Cache-Control": "no-store" } });
}

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export async function POST(request: Request): Promise<Response> {
  const site = websiteId();
  if (site === null) {
    return empty(404);
  }
  const mediaType = (request.headers.get("content-type") ?? "").split(";")[0]?.trim().toLowerCase();
  if (mediaType !== JSON_MEDIA_TYPE) {
    return empty(415);
  }
  const text = await readLimited(request, SEND_BODY_MAX_BYTES);
  if (text === null) {
    return empty(413);
  }
  const clean = cleanSend(parse(text), site, new URL(request.url).origin);
  if (clean === null) {
    return empty(400);
  }
  const address = visitorAddress(request.headers.get("x-forwarded-for"), proxyHops());
  try {
    const answer = await fetch(`${umamiBaseUrl()}/api/send`, {
      method: "POST",
      headers: forwardedHeaders(request.headers, address),
      body: JSON.stringify(clean),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MILLISECONDS),
    });
    const body = await answer.text();
    if (body.length > ANSWER_MAX_CHARACTERS) {
      return empty(502);
    }
    return new Response(body, { status: answer.status, headers: { "Content-Type": JSON_MEDIA_TYPE, "Cache-Control": "no-store" } });
  } catch {
    return empty(502);
  }
}

function notFound(): Response {
  return new Response(null, { status: 404, headers: { "Cache-Control": "no-store" } });
}

export const GET = notFound;
export const HEAD = notFound;
export const PUT = notFound;
export const PATCH = notFound;
export const DELETE = notFound;
export const OPTIONS = notFound;
