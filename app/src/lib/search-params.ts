export interface SearchParams {
  q: string;
  from?: Date;
  /** Exclusive: the day after the `to` the user gave. */
  to?: Date;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Reads `q`, `from` and `to` (inclusive days, YYYY-MM-DD, UTC) from a search request. */
export function parseSearchParams(params: URLSearchParams): SearchParams | { error: string } {
  const q = (params.get("q") ?? "").trim();
  if (!q) return { error: "q is required" };
  if (q.length > 500) return { error: "q must be at most 500 characters" };

  const from = day(params.get("from"));
  const to = day(params.get("to"));
  if (from === null || to === null) return { error: "from and to must be days, YYYY-MM-DD" };
  if (from && to && from > to) return { error: "from must not be after to" };

  return { q, from, to: to && new Date(to.getTime() + 86_400_000) };
}

/** undefined when absent, null when malformed. */
function day(value: string | null): Date | undefined | null {
  if (!value) return undefined;
  if (!DAY.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return isNaN(date.getTime()) ? null : date;
}
