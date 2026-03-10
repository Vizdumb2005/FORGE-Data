import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes without conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format an ISO date string into a human-readable form. */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** Truncate a string to `maxLen` characters, appending "…" if truncated. */
export function truncate(str: string, maxLen: number): string {
  return str.length > maxLen ? str.slice(0, maxLen - 1) + "…" : str;
}

/** Return initials from a full name or email. */
export function initials(nameOrEmail: string): string {
  const parts = nameOrEmail.split(/[\s@]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Sleep for `ms` milliseconds. */
export const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Parse an SSE stream line into a JSON payload, or null if it's a comment / empty. */
export function parseSseLine<T>(line: string): T | null {
  if (!line.startsWith("data:")) return null;
  const raw = line.slice(5).trim();
  if (raw === "[DONE]") return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}
