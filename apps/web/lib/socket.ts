"use client";

export function getSocketBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SOCKET_URL?.trim();
  if (explicit) return explicit;

  if (typeof window !== "undefined") {
    const { protocol, hostname, port, origin } = window.location;
    if (port === "3000") {
      return `${protocol}//${hostname}:8000`;
    }
    return origin;
  }

  return "http://localhost:8000";
}

