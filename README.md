# Tempo

A small team time tracker built for the Falcon Jobster programmer assignment.
Employees track tasks in a dedicated personal view; the team dashboard shows
running timers, task history and period totals from the same database.

**Python 3.11+ · SQLite 3.35+ · Vanilla JavaScript · No third-party dependencies**

## Run in one command

```bash
python3 app.py
```

Open **http://127.0.0.1:8000**. No install, account, API key or build step is
required. The SQLite database is created automatically beside `app.py`.

For a populated demo with fictional employees and tasks:

```bash
python3 seed_demo.py
python3 app.py --db demo.sqlite3
```

The seed command uses a separate database and refuses to overwrite existing
employees. Reuse the same database path after restarting the server. Choose
another port with `--port 8080`; stop the server with Ctrl+C.

## Walkthrough

1. Add an employee on the dashboard, or start with the demo data.
2. Click **Открыть трекер** on an employee's card. The personal page has a task
   description, start/stop control, elapsed time and personal history.
3. Start a task, then open the team overview in another tab. Return to that tab
   or click Refresh to see the shared running timer.
4. Stop the task from either screen. Its completed entry appears in the reports.
5. Choose Today / Week / Month or custom dates, and optionally filter by employee.
6. Restart the server with the same database: employees, entries and running
   timers remain available.

UI language is Russian. Dates, timestamps and period boundaries are explicitly
labelled **UTC**. The dashboard's period total follows the employee filter;
team size and active-timer counts always describe the whole team. Reports are
snapshots; elapsed timers tick every second.

## Assignment coverage

| Requirement | Implementation |
| --- | --- |
| Add employees | Dashboard form with validation and duplicate-name feedback. |
| Start/stop a timer with a task description | Available in team cards and the personal tracker. |
| View records and total time per employee for a period | Date filters, employee totals and task history; active tasks included. |
| Preserve data after restart | SQLite stores absolute start/end timestamps; active tasks recover on restart. |
| Simple interface, no authentication or complex roles | Two linked views and a demo employee selector. |
| Fictional data only | Optional seed script and isolated test fixtures. |
| Explain AI tools, prompts and fixes | [AI_USAGE.md](AI_USAGE.md). |
| Check duplicate starts and empty reports | Automated tests, including six concurrent start requests. |

## Verification

```bash
python3 -m unittest -v
node --check static/app.js
node --check static/employee.js
```

Node is optional and used only for the JavaScript syntax checks.

**16 domain/HTTP tests pass locally on Python 3.12.14.** They cover the HTTP flow,
shared personal/team state, concurrent starts, repeated stops, independent
employee timers, restart persistence, empty reports, invalid requests, active
and completed cross-midnight tasks, and exact report boundaries. Tests create
and clean up their own temporary databases.

GitHub Actions is configured to run the suite on Python 3.11, 3.12 and 3.13 plus
both JavaScript syntax checks. No CI result is claimed before the first push.
The original UI was manually tried by the applicant; browser verification of
the redesigned dashboard and personal screen remains outstanding.

## Architecture

| File | Responsibility |
| --- | --- |
| `app.py` | `Tracker` domain operations, SQLite schema and HTTP adapter. |
| `static/index.html`, `static/app.js` | Team overview and reports. |
| `static/employee.html`, `static/employee.js` | Dedicated employee tracker. |
| `static/style.css` | Shared responsive workspace styling. |
| `seed_demo.py` | Optional fictional demo dataset. |
| `test_app.py` | Domain and real HTTP tests using the standard library. |

Both screens use the same API and SQLite records. There is no separate
browser-local timer store. The personal page is a convenient view, not an
access-control boundary: any employee can be selected, as authentication is
outside the assignment scope. Other tabs refresh on focus or manually; this
version does not use live push updates.

### One active timer per employee

```sql
CREATE UNIQUE INDEX one_running_timer
ON entries(employee_id) WHERE ended_at IS NULL;
```

This partial unique index enforces the invariant in the database, including
concurrent requests. A duplicate start returns HTTP 409. Stopping uses one
conditional SQL update; repeating it cannot change the original end timestamp.
This is database uniqueness, not an idempotency-key implementation.

### Accurate period totals

```python
start = max(task_start, period_start)
end = min(task_end_or_now, period_end)
seconds = max(0, end - start)
```

The final date is inclusive in the UI and becomes midnight of the next day as
an exclusive upper boundary. A 23:30–00:30 task contributes 30 minutes to each
UTC day. Active tasks share a single captured `now` per report. The employee
and entry queries run in one read transaction for a consistent SQLite snapshot.

The live display uses server time plus `performance.now()` to avoid depending
on the browser's wall clock. Stored timestamps and reports use server time.

## Deliberate limits

The built-in HTTP server and SQLite keep the assignment easy to run. The server
binds to localhost and is intended for a local demonstration. Hosting would
require a production server, authentication and deployment configuration.

SQL binds parameters; UI rendering uses DOM nodes and `textContent`. Writes
require JSON, have a request-size limit and reject foreign origins.
Active tasks accrue wall-clock time while the app is closed; server clock
changes can still affect timing. SQLite's built-in `NOCASE` checks ASCII case,
not full Unicode name equivalence. Billing, payroll and task editing are out
of scope.

## AI-assisted development

Built with ChatGPT Work using GPT-6.1 for implementation, tests and code review.
Actual input excerpts, identified issues, corrections and verification limits
are documented in [AI_USAGE.md](AI_USAGE.md).

## Publish the repository

With Git, GitHub CLI (`gh`) and an authenticated account:

```bash
bash publish.sh
```

The script runs the tests, creates the initial Git commit and publishes a new
**public** repository named `tempo-time-tracker` in the signed-in account. A
different name can be passed as an argument. It refuses to run if an `origin`
remote already exists. If Git needs an author identity, configure your own
`user.name` and `user.email` and rerun the script. Database and environment files
are ignored and are not included in the initial commit.
