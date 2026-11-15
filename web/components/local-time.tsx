"use client";

import { useSyncExternalStore } from "react";

// A date and time in the viewer's own time zone. The server only knows UTC,
// so the text is written only in the browser: the server renders an empty
// <time>, and the browser fills it in right after loading.

const noSubscription = () => () => {};

export function LocalTime({ iso }: { iso: string }) {
  const inBrowser = useSyncExternalStore(
    noSubscription,
    () => true, // browser
    () => false, // server and the first (hydration) render
  );
  return (
    <time dateTime={iso}>
      {inBrowser
        ? new Date(iso).toLocaleString("en-GB", {
            weekday: "long",
            day: "numeric",
            month: "long",
            hour: "2-digit",
            minute: "2-digit",
          })
        : null}
    </time>
  );
}
