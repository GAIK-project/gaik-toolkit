// Request body limits, held while the body arrives.
//
// The limits are the API's own (api/upload_limits.json, read by the API's
// UploadLimitMiddleware too): a whole-request size and a number of file parts
// per route. A body is refused by its declared Content-Length before this code
// reads any of it, and otherwise as soon as the bytes it reads pass the limit,
// when it cancels its reader. Next.js itself buffers each request for the proxy,
// up to proxyClientMaxBodySize in next.config.ts, so these limits bound what is
// copied and parsed here, not what the server receives.
import table from "@/api/upload_limits.json";

const MIB = 1024 * 1024;

export interface BodyLimit {
  maxBytes: number;
  maxFiles: number;
  message: string;
}

interface Entry {
  max_mb: number;
  max_files: number;
  message: string;
}

const toLimit = (entry: Entry): BodyLimit => ({
  maxBytes: Math.floor(entry.max_mb * MIB),
  maxFiles: entry.max_files,
  message: entry.message,
});

export const DEFAULT_LIMIT = toLimit(table.default);
const ROUTES: Record<string, BodyLimit> = Object.fromEntries(
  Object.entries(table.routes as Record<string, Entry>).map(([path, entry]) => [
    path,
    toLimit(entry),
  ]),
);

/** The largest whole-request limit of any route, in bytes. */
export const LARGEST_LIMIT_BYTES = Math.max(
  ...Object.values(ROUTES).map((limit) => limit.maxBytes),
);

/**
 * The limit of an API path as the backend routes it ("/parse", not
 * "/api/parse"): an exact entry, else the longest entry ending in "/" that the
 * path starts with, else the default.
 */
export function bodyLimitFor(apiPath: string): BodyLimit {
  if (Object.hasOwn(ROUTES, apiPath)) return ROUTES[apiPath];
  let best: string | null = null;
  for (const path of Object.keys(ROUTES))
    if (path.endsWith("/") && apiPath.startsWith(path))
      if (best === null || path.length > best.length) best = path;
  return best === null ? DEFAULT_LIMIT : ROUTES[best];
}

/** The text for a request with more file parts than its route takes. */
export function tooManyFilesMessage(maxFiles: number): string {
  if (maxFiles === 0) return "This request takes no files.";
  return `Too many files: at most ${maxFiles} ${maxFiles === 1 ? "file" : "files"} per request.`;
}

/** True when the request declares a Content-Length over `maxBytes`. */
export function declaresMoreThan(request: Request, maxBytes: number): boolean {
  const declared = request.headers.get("content-length");
  if (declared === null || declared.trim() === "") return false;
  const n = Number(declared);
  return !Number.isFinite(n) || n > maxBytes;
}

/**
 * The request body, read while it stays within `maxBytes`, or null when it
 * declares or carries more. This copy stops at the first chunk past the limit
 * and cancels its reader; what Next.js has buffered already stays buffered.
 */
export async function readBodyWithin(
  request: Request,
  maxBytes: number,
): Promise<ArrayBuffer | null> {
  if (declaresMoreThan(request, maxBytes)) {
    await request.body?.cancel().catch(() => {});
    return null;
  }
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel().catch(() => {});
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

export type FormRead =
  | { ok: true; form: FormData }
  | { ok: false; status: 413 }
  | { ok: false; status: 400; error: string };

/**
 * A multipart form read within the route's limit: refused (413) when the body
 * passes `maxBytes`, refused (400) when it is not form data or carries more
 * than `maxFiles` files. The caller words the 413 in its own terms.
 */
export async function readFormWithin(
  request: Request,
  limit: Pick<BodyLimit, "maxBytes" | "maxFiles">,
): Promise<FormRead> {
  const body = await readBodyWithin(request, limit.maxBytes);
  if (body === null) return { ok: false, status: 413 };
  let form: FormData;
  try {
    form = await new Response(body, {
      headers: { "content-type": request.headers.get("content-type") ?? "" },
    }).formData();
  } catch {
    return { ok: false, status: 400, error: "Invalid form data." };
  }
  let files = 0;
  for (const [, value] of form) if (typeof value !== "string") files += 1;
  if (files > limit.maxFiles)
    return {
      ok: false,
      status: 400,
      error: tooManyFilesMessage(limit.maxFiles),
    };
  return { ok: true, form };
}
