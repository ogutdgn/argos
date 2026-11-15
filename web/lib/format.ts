// "15 November 2026": the one date format of the app and its emails
// (decided 2026-11-15). Takes a date ("2026-11-15") or a timestamp.
// Read in UTC, so the server and the browser show the same day. Times of
// day: components/local-time.tsx.
export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
