import { NextResponse, type NextRequest } from "next/server";

// Fixed internal gateway URL; never derive the backend destination from Host headers.
const userApi = process.env.USER_API_URL || "http://nginx/api/user";

export async function middleware(request: NextRequest) {
  const noStore = { "Cache-Control": "no-store" };
  const cookie = request.cookies.get("ako_session");
  const login = () => {
    // Next middleware requires an absolute redirect. Its internal request URL
    // may contain the Next server's port, so use the incoming public Host here.
    // This host is never used for backend fetches.
    const target = new URL(request.url);
    target.host = request.headers.get("host") || target.host;
    target.pathname = "/";
    target.search = "";
    return NextResponse.redirect(target, { headers: noStore });
  };
  if (!cookie) return login();
  try {
    const headers = { Cookie: `ako_session=${cookie.value}` };
    const response = await fetch(`${userApi}/session`, { headers, cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (response.status === 401) return login();
    if (!response.ok) throw new Error("Session service unavailable");
    const user = await response.json();
    const path = request.nextUrl.pathname;
    let allowed = ["teacher", "coordinator"].includes(user.role);
    if (path.startsWith("/teacher")) allowed = user.role === "teacher";
    if (path.startsWith("/coordinator") || path.startsWith("/account-management")) allowed = user.role === "coordinator";
    if (allowed && path.startsWith("/account-management")) {
      const access = await fetch(`${userApi}/account-management/access`, { headers, cache: "no-store", signal: AbortSignal.timeout(5000) });
      if (access.status === 401) return login();
      if (access.status !== 403 && !access.ok) throw new Error("Authorization unavailable");
      allowed = access.ok;
    }
    if (!allowed) {
      const expiresAt = Date.parse(response.headers.get("X-Session-Expires-At") || "");
      const remaining = Number.isFinite(expiresAt) ? Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000)) : 0;
      const home = user.role === "teacher" ? "/teacher" : "/coordinator";
      // A direct response preserves HTTP 403; Next's page rewrite can become 200.
      // No protected page or account data is rendered. The denial page also exits
      // at the session deadline without making any activity request.
      return new NextResponse(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="refresh" content="${remaining};url=/"><title>Access denied</title></head><body><main><p role="alert">You do not have permission</p><a href="${home}">Return home</a></main></body></html>`, {
        status: 403, headers: { ...noStore, "Content-Type": "text/html; charset=utf-8", "X-Content-Type-Options": "nosniff" },
      });
    }
    return NextResponse.next({ headers: noStore });
  } catch {
    return new NextResponse("Unable to verify your session. Please try again.", { status: 503, headers: noStore });
  }
}

export const config = { matcher: ["/teacher/:path*", "/coordinator/:path*", "/account-management/:path*", "/forbidden"] };
