export interface SearchParams {
  q: string;
  /** Only photos taken at or after this instant. */
  from?: Date;
  /** Only photos taken before this instant. */
  to?: Date;
}

/** An ISO 8601 instant with an explicit zone, e.g. 2025-07-01T00:00:00.000Z or ...T00:00+02:00. */
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;

/**
 * Reads `q`, `from` and `to` from a search request. The range is half-open, [from, to), and given
 * as instants rather than days: the browser turns the days the user picked into its own local
 * midnights, the same days the Timeline is sectioned by (see localDayRange).
 */
export function parseSearchParams(params: URLSearchParams): SearchParams | { error: string } {
  const q = (params.get("q") ?? "").trim();
  if (!q) return { error: "q is required" };
  if (q.length > 500) return { error: "q must be at most 500 characters" };

  const from = instant(params.get("from"));
  const to = instant(params.get("to"));
  if (from === null || to === null) return { error: "from and to must be ISO 8601 instants with a zone" };
  if (from && to && from >= to) return { error: "from must be before to" };

  return { q, from, to };
}

/** undefined when absent, null when malformed. */
function instant(value: string | null): Date | undefined | null {
  if (!value) return undefined;
  if (!INSTANT.test(value)) return null;
  const date = new Date(value);
  return isNaN(date.getTime()) ? null : date;
}

/**
 * The instants bounding the local days `fromDay` to `toDay` (YYYY-MM-DD, both inclusive, either
 * optional) in the time zone this code runs in: in the browser, the user's.
 */
export function localDayRange(fromDay: string, toDay: string): { from?: string; to?: string } {
  const midnight = (day: string, plusDays = 0) => {
    const [year, month, date] = day.split("-").map(Number);
    return new Date(year, month - 1, date + plusDays).toISOString();
  };
  return {
    from: fromDay ? midnight(fromDay) : undefined,
    to: toDay ? midnight(toDay, 1) : undefined,
  };
}
