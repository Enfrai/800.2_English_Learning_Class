import { NextRequest, NextResponse } from "next/server";

// Fixed deployment target, never a client-supplied destination or redirect.
const lessonApi = process.env.LESSON_API_URL || "http://nginx/api/lesson";
const noStore = { "Cache-Control": "no-store" };
const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
// US-008 adds /lessons/{id}/review and /lessons/{id}/maori-content.
const route = new RegExp(`^(?:tags|lessons(?:/${uuid}(?:/materials|/review|/maori-content|/copy)?)?|materials/${uuid}(?:/download)?)$`);

/** Bridge only the existing Lesson routes; backend /me still validates session/role. */
async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!route.test(path)) return NextResponse.json({ detail: "Not found" }, { status: 404, headers: noStore });
  const cookies = request.cookies.getAll("ako_session");
  if (cookies.length !== 1 || !cookies[0].value || request.headers.has("authorization")) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401, headers: noStore });
  }
  if (request.method !== "GET") {
    // The gateway preserves Host and public port. Match Origin before converting
    // cookie authentication to Bearer, otherwise this adapter would bypass CSRF.
    const expected = process.env.SESSION_PUBLIC_ORIGIN || `${request.nextUrl.protocol}//${request.headers.get("host")}`;
    if (!request.headers.get("origin") || request.headers.get("origin") !== expected) {
      return NextResponse.json({ detail: "Origin not allowed" }, { status: 403, headers: noStore });
    }
  }
  let body: ArrayBuffer | undefined;
  if (request.method !== "GET") {
    const limit = 11 * 1024 * 1024;
    if (Number(request.headers.get("content-length") || 0) > limit) {
      return NextResponse.json({ detail: "Upload exceeds 10 MB file limit" }, { status: 413, headers: noStore });
    }
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      if (reader) while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > limit) {
          await reader.cancel();
          return NextResponse.json({ detail: "Upload exceeds 10 MB file limit" }, { status: 413, headers: noStore });
        }
        chunks.push(value);
      }
      const combined = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { combined.set(chunk, offset); offset += chunk.byteLength; }
      body = combined.buffer;
    } catch {
      return NextResponse.json({ detail: "Unable to read request" }, { status: 400, headers: noStore });
    }
  }
  try {
    const response = await fetch(`${lessonApi}/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers: { Authorization: `Bearer ${cookies[0].value}`, ...(request.headers.get("content-type") ? { "Content-Type": request.headers.get("content-type")! } : {}) },
      body,
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10000),
    });
    return new NextResponse(response.status === 204 ? null : await response.arrayBuffer(), {
      status: response.status,
      headers: { ...noStore, "X-Content-Type-Options": "nosniff", "Content-Type": response.headers.get("content-type") || "application/json", ...(response.headers.get("content-disposition") ? { "Content-Disposition": response.headers.get("content-disposition")! } : {}) },
    });
  } catch {
    return NextResponse.json({ detail: "Lesson service unavailable" }, { status: 502, headers: noStore });
  }
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
