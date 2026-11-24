import { umamiBaseUrl, websiteId } from "@/lib/umami";

export const dynamic = "force-dynamic";

const SCRIPT_MAX_CHARACTERS = 100_000;
const TIMEOUT_MILLISECONDS = 5000;

export async function GET(): Promise<Response> {
  if (websiteId() === null) {
    return new Response(null, { status: 404 });
  }
  try {
    const answer = await fetch(`${umamiBaseUrl()}/script.js`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MILLISECONDS),
    });
    const body = await answer.text();
    if (!answer.ok || body.length > SCRIPT_MAX_CHARACTERS) {
      return new Response(null, { status: 502 });
    }
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "application/javascript; charset=utf-8", "Cache-Control": "public, max-age=3600" },
    });
  } catch {
    return new Response(null, { status: 502 });
  }
}

function notFound(): Response {
  return new Response(null, { status: 404, headers: { "Cache-Control": "no-store" } });
}

export const POST = notFound;
export const PUT = notFound;
export const PATCH = notFound;
export const DELETE = notFound;
export const OPTIONS = notFound;
