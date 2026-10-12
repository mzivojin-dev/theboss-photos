/**
 * Selects (never deletes) the photos of the given days on photos.google.com.
 *
 * Flow: the cleanup page copies `clipboardPayload(days)` and opens Google Photos; the user clicks the
 * bookmarklet there, which reads the clipboard, ticks every photo of those days while scrolling, and reports
 * how many it selected against how many were indexed. The user then presses Delete themselves.
 */

const CLIPBOARD_PREFIX = "theboss-cleanup:";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2020-12-24" -> "Dec 24, 2020", the date format in Google Photos' photo labels. */
export function photoLabelDate(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return `${MONTHS[month - 1]} ${date}, ${year}`;
}

export function clipboardPayload(days: string[], expectedItems: number): string {
  return `${CLIPBOARD_PREFIX}${expectedItems}:${days.join(",")}`;
}

export const PHOTOS_URL = "https://photos.google.com/";

// Runs in photos.google.com, so it is plain JS with no imports. Pasted as a bookmarklet it must be one line.
const SCRIPT = `
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let text = '';
  try { text = await navigator.clipboard.readText(); } catch (e) {}
  const m = text.match(/^${CLIPBOARD_PREFIX}(\\d+):(.+)$/);
  if (!m) { alert('Nothing to select. On the cleanup page press "Open in Google Photos" first, then click this bookmark.'); return; }
  const expected = Number(m[1]);
  const months = ${JSON.stringify(MONTHS)};
  const labels = new Set(m[2].split(',').map((d) => { const [y, mo, da] = d.split('-').map(Number); return months[mo - 1] + ' ' + da + ', ' + y; }));
  const scroller = [...document.querySelectorAll('*')]
    .filter((e) => e.scrollHeight > e.clientHeight + 200 && /(auto|scroll)/.test(getComputedStyle(e).overflowY))
    .sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
  if (!scroller) { alert('Could not find the photo list on this page.'); return; }
  const dateOf = (l) => (l.match(/([A-Z][a-z]{2} \\d{1,2}, \\d{4}),/) || [])[1];
  const inRange = () => [...document.querySelectorAll('[role="checkbox"][aria-label]')]
    .filter((e) => !e.getAttribute('aria-label').startsWith('Select all') && labels.has(dateOf(e.getAttribute('aria-label'))));
  const showMore = () => [...document.querySelectorAll('*')].filter((e) => e.children.length === 0 && e.textContent.trim() === 'Show more' && e.offsetParent !== null);
  scroller.scrollTop = 0;
  await sleep(600);
  for (let i = 0; i < 400; i++) {
    for (const b of showMore()) { b.click(); await sleep(300); }
    for (const box of inRange().filter((b) => b.getAttribute('aria-checked') === 'false')) { box.click(); await sleep(40); }
    const before = scroller.scrollTop;
    scroller.scrollTop += Math.round(window.innerHeight * 0.6);
    await sleep(450);
    if (scroller.scrollTop === before) break;
  }
  await sleep(1500);
  const unticked = inRange().filter((b) => b.getAttribute('aria-checked') !== 'true').length;
  const sel = [...document.querySelectorAll('*')].filter((e) => e.children.length === 0).map((e) => e.textContent.trim()).find((t) => /^\\d+\\s+selected$/i.test(t));
  const n = sel ? Number(sel.split(/\\s/)[0]) : 0;
  const verdict = n > expected ? 'MORE selected than indexed. Do NOT delete; deselect and check the dates.'
    : (n < expected || unticked > 0) ? 'Fewer selected than indexed. Some photos may be missing from the selection.'
    : 'Matches the indexed count.';
  alert('Selected ' + n + ' of ' + expected + ' indexed (' + unticked + ' left unticked).\\n' + verdict + '\\nNothing was deleted. Review the selection, then delete it yourself.');
})();
`;

/** The one-line `javascript:` URL to save as a bookmark. */
export function bookmarkletUrl(): string {
  return "javascript:" + encodeURIComponent(SCRIPT.replace(/\n\s*/g, " ").trim());
}
