import { buildCleanupReport, CleanupInput, daysInRange, planDeletion } from "@/lib/safe-days";

const photo = (day: string, path = `${day}.jpg`) => ({ id: `id-${path}`, filename: path, takenAt: new Date(`${day}T12:00:00Z`), originalGcsPath: path });

const input = (overrides: Partial<CleanupInput> = {}): CleanupInput => ({
  photos: [],
  exports: [{ id: "E1", exportedAt: new Date("2026-10-05T23:27:35Z"), years: [2026] }],
  problems: [],
  originalNames: new Set(),
  deletedDays: new Set(),
  ...overrides,
});

const withOriginals = (days: string[], overrides: Partial<CleanupInput> = {}) =>
  input({ photos: days.map((d) => photo(d)), originalNames: new Set(days.map((d) => `${d}.jpg`)), ...overrides });

const problemOn = (day: string) => ({
  kind: "failed",
  path: "x.jpg",
  reason: "boom",
  takenAt: new Date(`${day}T23:59:00Z`),
});

describe("buildCleanupReport", () => {
  it("makes consecutive safe days one range with the item count", () => {
    const report = buildCleanupReport(withOriginals(["2026-03-01", "2026-03-02", "2026-03-02"]));

    expect(report.safeRanges).toEqual([{ start: "2026-03-01", end: "2026-03-02", itemCount: 3 }]);
    expect(report.unsafeDays).toEqual([]);
  });

  it("does not break a range at days with no media", () => {
    const report = buildCleanupReport(withOriginals(["2026-03-01", "2026-03-09"]));

    expect(report.safeRanges).toEqual([{ start: "2026-03-01", end: "2026-03-09", itemCount: 2 }]);
  });

  it("breaks a range at an unsafe day and lists ranges newest first", () => {
    const base = withOriginals(["2026-03-01", "2026-03-02", "2026-03-03"]);
    base.originalNames = new Set(["2026-03-01.jpg", "2026-03-03.jpg"]);

    const report = buildCleanupReport(base);

    expect(report.safeRanges.map((r) => r.start)).toEqual(["2026-03-03", "2026-03-01"]);
    expect(report.unsafeDays).toEqual([{ day: "2026-03-02", itemCount: 1, reasons: ["original_missing"] }]);
  });

  it("is not safe when a year is missing from every export", () => {
    const report = buildCleanupReport(withOriginals(["2025-06-01"]));

    expect(report.safeRanges).toEqual([]);
    expect(report.unsafeDays[0].reasons).toEqual(["not_covered"]);
  });

  it("is not safe on or after the export date", () => {
    const report = buildCleanupReport(withOriginals(["2026-10-04", "2026-10-05", "2026-10-06"]));

    expect(report.safeRanges).toEqual([{ start: "2026-10-04", end: "2026-10-04", itemCount: 1 }]);
    expect(report.unsafeDays.map((d) => [d.day, d.reasons])).toEqual([
      ["2026-10-06", ["after_export"]],
      ["2026-10-05", ["after_export"]],
    ]);
  });

  it("is covered when any export has the year and is later than the day", () => {
    const report = buildCleanupReport(
      withOriginals(["2026-10-06"], {
        exports: [
          { id: "E1", exportedAt: new Date("2026-10-05T00:00:00Z"), years: [2026] },
          { id: "E2", exportedAt: new Date("2026-10-20T00:00:00Z"), years: [2026] },
        ],
      })
    );

    expect(report.safeRanges).toHaveLength(1);
  });

  it.each(["2026-03-01", "2026-03-02", "2026-03-03"])("an unresolved problem on %s blocks 2026-03-02", (day) => {
    const report = buildCleanupReport(withOriginals(["2026-03-02"], { problems: [problemOn(day)] }));

    expect(report.unsafeDays[0].reasons).toEqual(["problem_nearby"]);
  });

  it("is not blocked by a problem two days away", () => {
    const report = buildCleanupReport(withOriginals(["2026-03-02"], { problems: [problemOn("2026-03-04")] }));

    expect(report.safeRanges).toHaveLength(1);
  });

  it("lists problems without a date separately and does not let them block a day", () => {
    const problem = { kind: "no_sidecar", path: "IMG_9.jpg", reason: "No Sidecar found", takenAt: null };

    const report = buildCleanupReport(withOriginals(["2026-03-02"], { problems: [problem] }));

    expect(report.undatedProblems).toEqual([problem]);
    expect(report.safeRanges).toHaveLength(1);
  });

  it("is not safe when any Original of the day is missing from the bucket", () => {
    const report = buildCleanupReport(
      input({
        photos: [photo("2026-03-02", "a.jpg"), photo("2026-03-02", "b.jpg")],
        originalNames: new Set(["a.jpg"]),
      })
    );

    expect(report.unsafeDays[0].reasons).toEqual(["original_missing"]);
  });

  it("counts an item stored on YouTube as present", () => {
    const report = buildCleanupReport(
      input({ photos: [{ id: "v", filename: "v.mp4", takenAt: new Date("2026-03-02T00:00:00Z"), youtubeVideoId: "abc" }] })
    );

    expect(report.safeRanges).toHaveLength(1);
  });

  it("reports every reason a day is unsafe", () => {
    const report = buildCleanupReport(input({ photos: [photo("2025-01-01")] }));

    expect(report.unsafeDays[0].reasons).toEqual(["not_covered", "original_missing"]);
  });

  it("leaves days already marked deleted off the safe ranges without breaking a range", () => {
    const report = buildCleanupReport(
      withOriginals(["2026-03-01", "2026-03-02", "2026-03-03"], { deletedDays: new Set(["2026-03-02"]) })
    );

    expect(report.safeRanges).toEqual([{ start: "2026-03-01", end: "2026-03-03", itemCount: 2 }]);
    expect(report.deletedDays).toEqual(["2026-03-02"]);
  });
});

describe("daysInRange", () => {
  it("lists every day from start to end", () => {
    expect(daysInRange("2026-02-27", "2026-03-02")).toEqual(["2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"]);
  });
});

describe("planDeletion", () => {
  const days = ["2026-03-01", "2026-03-02", "2026-03-03"];

  it("records the items, counts and evidence of a safe range", () => {
    const base = withOriginals(days, { problems: [problemOn("2026-06-01")] });

    const plan = planDeletion(base, "2026-03-01", "2026-03-02");

    expect(plan).toEqual({
      ok: true,
      entry: expect.objectContaining({
        start: "2026-03-01",
        end: "2026-03-02",
        itemCount: 2,
        days: { "2026-03-01": 1, "2026-03-02": 1 },
        items: [
          { id: "id-2026-03-01.jpg", filename: "2026-03-01.jpg", day: "2026-03-01", original: "2026-03-01.jpg" },
          { id: "id-2026-03-02.jpg", filename: "2026-03-02.jpg", day: "2026-03-02", original: "2026-03-02.jpg" },
        ],
        exports: [{ id: "E1", exportedAt: new Date("2026-10-05T23:27:35Z"), years: [2026] }],
        unresolvedProblems: 1,
        originalsListed: 3,
      }),
    });
  });

  it("refuses a range containing a day that is not safe", () => {
    const base = withOriginals(days);
    base.originalNames = new Set(["2026-03-01.jpg", "2026-03-03.jpg"]);

    expect(planDeletion(base, "2026-03-01", "2026-03-03").ok).toBe(false);
  });

  it("refuses a range that has no safe days", () => {
    expect(planDeletion(withOriginals(["2025-01-01"]), "2025-01-01", "2025-01-01").ok).toBe(false);
  });

  it("leaves out days already marked deleted", () => {
    const plan = planDeletion(withOriginals(days, { deletedDays: new Set(["2026-03-02"]) }), "2026-03-01", "2026-03-03");

    expect(plan).toEqual({ ok: true, entry: expect.objectContaining({ itemCount: 2, days: { "2026-03-01": 1, "2026-03-03": 1 } }) });
  });
});
