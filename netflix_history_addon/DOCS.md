# Netflix Viewing History

1. Start the add-on and open **Netflix History** in the sidebar.
2. Press **Sign in to Netflix**, log in inside the embedded browser (MFA and captchas work), then press **Done**.
3. The add-on scrapes every profile on a schedule (`scrape_interval_hours`, default 24) and on **Refresh now**.
4. Copy the host and token shown in the panel into the *Netflix Viewing History* integration.

Only the Netflix session cookies are stored (in the add-on's private `/data`). `date_format` is a
`strptime` pattern (e.g. `%y-%m-%d` for dates like `26-8-25`) matching your Netflix locale; set it to get dated sensors.

`engine`: `chromium` (default) or `obscura` (lighter; experimental, see the repo README). Sign-in always uses Chromium.

`debug_probe` (default off): enables a read-only page inspector at `POST /api/debug/probe` on the token-protected API (port 8100), for diagnosing changes to Netflix's pages. It can navigate Netflix paths and read sanitised page structure; it cannot click, type or run scripts.
