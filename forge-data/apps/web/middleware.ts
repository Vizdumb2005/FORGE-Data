import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/register", "/setup", "/api/"];
const AUTH_PATHS = ["/login", "/register"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Allow Next.js internals and static assets
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/icons")
  ) {
    return NextResponse.next();
  }

  // Check setup status — only for non-setup, non-API paths to avoid loops
  if (!pathname.startsWith("/setup") && !pathname.startsWith("/api/")) {
    try {
      const apiBase =
        process.env.API_URL ?? "http://api:8000";
      const res = await fetch(`${apiBase}/api/v1/setup/status`, {
        cache: "no-store",
        signal: AbortSignal.timeout(2000),
      });
      if (res.ok) {
        const data = (await res.json()) as { needs_setup: boolean };
        if (data.needs_setup) {
          return NextResponse.redirect(new URL("/setup", req.url));
        }
      }
    } catch {
      // If the API is unreachable during startup, don't block the request
    }
  }

  const token = req.cookies.get("forge_access_token")?.value;
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const isAuthPath = AUTH_PATHS.some((p) => pathname.startsWith(p));

  if (token && isAuthPath) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }

  if (!token && !isPublic) {
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const requestHeaders = new Headers(req.headers);
  const host = req.headers.get("host") || "";
  requestHeaders.set("x-forwarded-host", host);
  requestHeaders.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)" ],
};
