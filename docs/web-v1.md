# Web v1: local practice interface

`web/` implements a React/TypeScript/Vite client for the existing API. It is a
local-development slice, not a public account system or deployment. The visual
direction is flat monochrome with a powdery pink accent. Light, black-background
dark, and system themes are stored locally. Layouts adapt to desktop and mobile; motion respects reduced-motion
preferences. Native dialogs provide focus containment and Escape dismissal.

## Implemented

- A next-review card ordered by earliest due time, up to three alternative reviews,
  a difficulty filter, a full due queue, library, collection navigation, and search.
  Title links open problems in a separate tab. Topic tags remain hidden to avoid
  giving away the approach (they are still searchable).
- Prominent last-attempt duration/outcome/date and optional time goal; full timing
  history preserves measured and corrected duration separately. Time does not
  affect the scheduling policy or change an independent outcome into a failure.
- A current-year activity calendar based on actual Epoch attempts, including first
  attempts and repetitions. Adding a link does not count as practice. Click a day
  to see its attempts; day boundaries use the browser timezone, displayed below
  the calendar. Imported LeetCode activity, streaks, and profile stats are not included.
- Collection creation and linked coding-problem creation with difficulty, tags,
  and optional personal time goal. The form is URL-first with editable title
  suggestions from LeetCode slugs and local canonical-link duplicate detection.
  It does not fetch metadata or infer problem numbers/difficulty. Include a problem
  number in the title when desired; there is no validated metadata catalog yet.
- Study dialog with a problem link, optional timer, explicit outcome, optional
  confidence and manual/corrected duration, and historical attempts.
- Current schedule refresh after submitting. Maintenance items stay in the library
  and return to the queue when due. Activity is computed from stored records;
  there are no fabricated streaks, retention scores, or ML predictions.
- Error/loading/empty states, local token connection and disconnection, and an
  opt-in synthetic demo connection.

Flashcards/exercises already stored through the API can be reviewed, but creation
in the UI currently focuses on linked problems. Archive, snooze, edit, and deletion
controls await corresponding API endpoints.

The current API has item-scoped history rather than an activity-summary endpoint.
The client fetches paginated histories with at most four concurrent requests,
showing loading/unavailable states instead of a misleading partial calendar. This
is suitable for the local slice; large libraries will need server-side activity
aggregation and latest-attempt summaries before a production rollout.

## Run locally

Install Node **24.22.2** (also pinned in `web/.node-version`). Start PostgreSQL,
apply migrations, and start the API using [the API setup](api-v1.md). Then:

```sh
cd web
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`, expand **Connect to your local API**, and paste a token
from `api.dev_token`. The token lives in this tab's `sessionStorage` so refreshes
work; disconnect removes it. Browser session recovery may restore session storage,
so disconnect explicitly on shared computers. This is temporary development auth,
not production login. The server still derives all ownership from verified claims.

Vite proxies `/api/*` to `http://127.0.0.1:8000` (override with `EPOCH_API_TARGET`).
No permissive CORS policy is needed. Both development servers bind to loopback.
`npm run build` type-checks and emits `web/dist/`. `npm run preview` previews static
assets only; the development API proxy and demo endpoint are not production hosting.
A deployed site will need same-origin API routing and real authentication.

For an explicitly local, synthetic demo, start Vite with `EPOCH_DEMO_TOKEN` set to
a locally issued token for a synthetic demo user. **Explore local demo** uses that
token. Without this environment variable, the demo endpoint returns 404. The
middleware exists only in Vite development, returns `Cache-Control: no-store`, and
does not embed credentials in built assets. Never use it with a real account or
expose the development server publicly.

## Timer and submission behavior

Timers use elapsed timestamps, not interval ticks. Pause excludes idle time.
Closing the study dialog pauses the timer; refreshing preserves its running
timestamp. Browser tab suspension is counted as elapsed time while running.
Backward clocks or uninterrupted spans over 12 hours pause timing and ask the user
to verify/correct it. Wall-clock forward changes under that threshold cannot be
distinguished from ordinary elapsed time; manual correction is available.

The home card's Start review opens the study dialog with the timer action focused;
the explicit Start & open button starts timing and opens the problem. Record
attempt opens the same dialog without starting a timer. Clicking a title opens
the problem directly and does not start timing or change its schedule.
Start & open opens an HTTPS problem in a new tab and removes its opener before navigating.
If blocked, the timer still starts with a visible message and manual link. Resume
does not open another tab. Reset requires confirmation and clears timer/correction
values. Measured and corrected seconds are sent independently; untimed attempts
omit both, and a manually entered zero stays zero.

A versioned draft is stored in `localStorage`, keyed by owner and item. An exclusive
Web Lock prevents two tabs from editing the same attempt. A conflicting tab must
close and reopen the dialog after the first releases it. Modern browsers on
localhost/HTTPS are required. Storage failure disables progress rather than
silently losing retry identity. Drafts contain outcomes/timing, not tokens or
learning content; they persist until successful submission or site-data removal.
This is single-browser draft recovery, not offline synchronization.

Before posting, the client freezes and stores the attempt UUID and exact payload.
An ambiguous failure retains both through refreshes. Retry sends the same event;
the API returns its original receipt without replacing newer scheduling state.
A definitive 422 rejection unlocks editing. A 409 is left visible with the frozen
submission for investigation. Collection/item creation is not idempotent: after a
network failure, check the library before creating it again.

## Checks

```sh
cd web
npm ci
npx playwright install chromium
npm run format:check
npm run build
npm test
```

Playwright tests cover keyboard interaction, mobile overflow, dialog focus return,
popup behavior, timer pause/reset/recovery, cross-tab exclusion, absent/corrected
timing, errors, and stable retry identity. Automated axe checks cover the workspace
and study dialog; these complement, rather than replace, keyboard/manual review.
These tests use synthetic HTTP fixtures.

The separate live browser test creates a collection/problem and submits an attempt
against a real running API/PostgreSQL instance. Run it with `EPOCH_E2E_TOKEN` for a
**disposable synthetic user**; it creates records and does not delete them. Without
that variable it explicitly skips. CI provisions PostgreSQL and supplies the token,
so it runs the real browser-to-database flow as well as fixture tests.

See GitHub Actions for the web job's results. Fonts currently use Google Fonts
with system fallbacks; self-hosting assets can be
part of deployment packaging. Public deployment, account lifecycle, and operational
controls remain separate work.
