# Mini Hiring Pipeline

A board for one recruiter and one job. Candidates move Applied, Screening, Interview, Offer, Hired, and can be Rejected at any point before Hired. Every move is recorded permanently, and one search box answers questions like "who's been stuck in Screening for more than a week?"

FastAPI, SQLite and plain JavaScript. No build step.

## Run

Python 3.11 or newer.

```
pip install -r requirements.txt
python scripts/seed.py --reset    # optional demo data, backdated from now
python -m pipeline                # http://127.0.0.1:8000
pytest
```

## Deploy on Vercel

Push the repo to GitHub, import it at vercel.com/new and deploy with the default settings. Vercel finds FastAPI in `requirements.txt` and uses `app.py` as the entrypoint.

Vercel's filesystem is read-only apart from a temporary `/tmp`, so the deployed site is a demo: it starts from the seed data, shows a notice, and keeps changes only until Vercel replaces the instance. To keep history, run `python -m pipeline` on a host with a persistent disk (Render, Railway, Fly.io), or move the store to a hosted database.

## API

`GET` and `POST /api/candidates`, `GET /api/candidates/{id}`, `POST /api/candidates/{id}/moves`, `GET /api/search?q=...&tz=Asia/Kolkata`.

## Decisions and why

**Forward only, one step at a time.** The brief rules out skipping and reversing a final outcome, and says "move along", so there is no backward move. The cost is that a mis-click can't be undone, which is why every move asks for confirmation.

**The API names the target stage** (`{"to": "interview"}`) instead of "advance". A double click or a stale second tab gets "Already in Interview" instead of skipping a stage.

**The history can't be altered.** Both tables are insert-only: SQLite triggers abort every UPDATE, every DELETE and any INSERT that would replace a row, so this doesn't depend on the app having no edit button. A candidate's stage isn't stored. It is whatever their latest event says, so the stage and the history can't disagree. Writes take SQLite's write lock, so checking the stage and recording the move can't interleave.

**Time.** Time in stage comes from the server's clock. The browser sends its time zone, so "since Monday" means midnight at the start of the recruiter's Monday. "After Monday" starts Tuesday. "Last week" is the previous Monday to Sunday; "in the last week" is a rolling seven days.

**Search is a small hand-written grammar, not an LLM.** The same text always reads the same way, it works offline, and it's testable. The price is that it only understands what's written down, so it says when it didn't.
- It reads names (typo tolerant), `in Interview`, `interview or offer`, `reached Offer`, `moved to Interview since Monday`, `stuck for more than a week`, `not hired` and `except rejected`. Conditions combine, and all must hold.
- Best name match comes first: exact, starts-with, typo, contained. A swapped pair of letters costs less than a wrong one, so "sharam" puts Sharma above Sharan. Ties go to whoever has waited longest (for "in" and "stuck" questions) or moved most recently (for "moved" and "reached"). The results say which.
- It shows how it read the query. Words it doesn't know are dropped with a warning while the rest still runs. Impossible requests (`stuck in hired`, `since tomorrow`, `in screening in interview`) get an explanation instead of a search. A valid search with nothing in it names the condition that failed: "the longest anyone has been in their current stage is 9d 4h (Priya Sharma)".

**Two judgment calls.** "Didn't get hired" means not currently Hired, so people still at Offer are included (their stage is shown, and `rejected` narrows it). "Stuck" on its own means more than 7 days.

## With more time

- A correction event, to undo a mis-click without editing history.
- Login, and who did it on every event.
- A hash chain over the events, so edits made outside the app are detectable. Triggers can be dropped by anyone with the database file.
- Editing a candidate's details (as events). Today a typo in a name can't be fixed.
- Enforce the stage rules in the database too, so even a raw INSERT can't skip a stage.
- Search for names in non-Latin scripts (Devanagari, for example), which isn't supported yet.
- Search at scale: prefilter in SQL, FTS5 for names. Postgres and Docker if it grows past one recruiter.

## How I used AI

I built this in a chat with Claude. The write-up is in [docs/AI_LOG.md](docs/AI_LOG.md) and the full conversation is in [docs/chat-export.md](docs/chat-export.md).

### Where I disagreed with the AI

The first full build went well past the brief: a hash chain over the events with a verify endpoint, email and notes fields, extra search phrasings, a PDF generator inside the repo, browser tests, and long docs, about 4,300 lines in all. I asked Claude to keep only what is absolutely needed, and it cut the project to about 2,000 lines. The cost is that edits made outside the app are no longer detectable; the triggers still block edits and deletes, and the hash chain is on the "with more time" list.
