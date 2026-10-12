import { bookmarkletUrl, clipboardPayload, photoLabelDate } from "@/lib/photos-selector";

describe("photos-selector", () => {
  it("formats a day like Google Photos labels it", () => {
    expect(photoLabelDate("2020-12-24")).toBe("Dec 24, 2020");
    expect(photoLabelDate("2021-01-05")).toBe("Jan 5, 2021");
  });

  it("puts the expected count and days in the clipboard payload", () => {
    expect(clipboardPayload(["2020-12-24", "2020-12-25"], 80)).toBe("theboss-cleanup:80:2020-12-24,2020-12-25");
  });

  it("builds a one-line javascript: bookmarklet that parses as a function body", () => {
    const url = bookmarkletUrl();
    expect(url.startsWith("javascript:")).toBe(true);
    const source = decodeURIComponent(url.slice("javascript:".length));
    expect(source).not.toContain("\n");
    expect(() => new Function(source)).not.toThrow();
  });
});
