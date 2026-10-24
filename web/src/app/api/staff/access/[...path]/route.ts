import { NextRequest, NextResponse } from "next/server";

// Fixed deployment target, never a client-supplied destination or redirect.
const accessApi = process.env.ACCESS_API_URL || "http://nginx/api/access";
const noStore = { "Cache-Control": "no-store" };
const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const route = new RegExp(`^sessions/${uuid}/attendance(?:/(?:${uuid}|new-learner))?$`);

/** Bridge only the existing Attendance routes; backend /me still validates session/role. */
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
  try {
    const response = await fetch(`${accessApi}/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers: { Authorization: `Bearer ${cookies[0].value}`, "Content-Type": "application/json" },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10000),
    });
    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers: { ...noStore, "Content-Type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Attendance service unavailable" }, { status: 502, headers: noStore });
  }
}

export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
