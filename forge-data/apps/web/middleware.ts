import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/register", "/api/"];
const AUTH_PATHS = ["/login", "/register"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Allow public assets and Next.js internals
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/icons")
  ) {
    return NextResponse.next();
  }

  const token = req.cookies.get("forge_access_token")?.value;
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const isAuthPath = AUTH_PATHS.some((p) => pathname.startsWith(p));

  // Logged-in users shouldn't revisit /login or /register
  if (token && isAuthPath) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }

  // Protected routes require a token
  if (!token && !isPublic) {
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const requestHeaders = new Headers(req.headers);
  const host = req.headers.get("host") || "";
  console.log("[middleware] Processing:", pathname, "Host:", host);
  requestHeaders.set("x-forwarded-host", host);
  requestHeaders.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));

  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
