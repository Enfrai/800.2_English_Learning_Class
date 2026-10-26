/* Forward protected classroom, QR, report and learner history requests.
 * Updated: Shuohui Liu, 26 Oct 2026
 * Updated: Pei Wu, 26 Oct 2026 (call the Accessment service on the internal network)
 */

import { NextRequest, NextResponse } from "next/server";

// Fixed deployment target, never a client-supplied destination or redirect.
// Straight to the service on the internal network, not through Nginx: every
// server-side call would otherwise share the web container's one rate limit.
const accessApi = process.env.ACCESS_API_URL || "http://access-service:8000";
const noStore = { "Cache-Control": "no-store" };
const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
// US-015 adds sessions/{id}/corrections.
const historyRoute = new RegExp(`^learners/${uuid}/attendance-history$`);
const route = new RegExp(`^sessions(?:/today|/${uuid}(?:/(?:attendance(?:/(?:${uuid}|new-learner))?|corrections|lesson|check-in))?)?$`);

/** Bridge attendance and class-session routes; backend /me validates session/role.
 * Updated: Shuohui Liu, 26 Oct 2026
 */
async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!route.test(path) && !historyRoute.test(path) && path !== "reports/attendance") return NextResponse.json({ detail: "Not found" }, { status: 404, headers: noStore });
  const cookies = request.cookies.getAll("ako_session");
  const sessionCookieCount = (request.headers.get("cookie") || "").split(";").filter(part => part.trim().split("=", 1)[0] === "ako_session").length;
  if (sessionCookieCount !== 1 || cookies.length !== 1 || !cookies[0].value || request.headers.has("authorization")) {
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
    return new NextResponse(response.status === 204 ? null : await response.arrayBuffer(), {
      status: response.status,
      headers: { ...noStore, "X-Content-Type-Options": "nosniff",
        "Content-Type": response.headers.get("content-type") || "application/json",
        ...(response.headers.get("content-disposition") ? { "Content-Disposition": response.headers.get("content-disposition")! } : {}),
      },
    });
  } catch {
    return NextResponse.json({ detail: "Attendance service unavailable" }, { status: 502, headers: noStore });
  }
}

export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
