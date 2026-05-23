/** Parse API timestamps (GMT strings, ISO, or naive UTC) for local display. */
export function parseApiTimestamp(ts?: string | null): Date | null {
  if (!ts) return null;
  const trimmed = ts.trim();
  if (!trimmed) return null;

  // RFC/GMT strings from Flask/MySQL — parse as-is
  if (/GMT|Z|[+-]\d{2}:\d{2}$/.test(trimmed)) {
    const d = new Date(trimmed);
    if (!Number.isNaN(d.getTime())) return d;
  }

  // Naive datetime — treat as UTC
  const normalized = trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T");
  const d = new Date(normalized.endsWith("Z") ? normalized : `${normalized}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatLocalTime(ts?: string | null, fallback = "—"): string {
  const d = parseApiTimestamp(ts);
  if (!d) return ts?.trim() || fallback;
  return d.toLocaleString();
}
