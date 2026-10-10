import { buildCleanupReport, CleanupInput, daysInRange } from "@/lib/safe-days";

const photo = (day: string, path = `${day}.jpg`) => ({ takenAt: new Date(`${day}T12:00:00Z`), originalGcsPath: path });

const input = (overrides: Partial<CleanupInput> = {}): CleanupInput => ({
  photos: [],
  exports: [{ exportedAt: new Date("2026-10-05T23:27:35Z"), years: [2026] }],
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
          { exportedAt: new Date("2026-10-05T00:00:00Z"), years: [2026] },
          { exportedAt: new Date("2026-10-20T00:00:00Z"), years: [2026] },
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
      input({ photos: [{ takenAt: new Date("2026-03-02T00:00:00Z"), youtubeVideoId: "abc" }] })
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
