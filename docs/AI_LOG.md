# AI log: Mini Hiring Pipeline

Claude (claude.ai) wrote the first version from the assignment text in one session. I then had it trimmed, tested and prepared for deployment. I reviewed the code and ran the tests. The chat it refers to is [chat-export.md](chat-export.md), and message numbers below point to that file.

This file has four parts: where I disagreed with the AI, the mistakes it made, the design decisions and trade-offs I had to settle, and a testing summary.

## 1. Where I disagreed with the AI

Six times I pushed back:

1. **Commit messages (message 2).** Claude's first commit messages read like AI output. I asked for plain, human ones and it rewrote them as short titles with brief bodies.
2. **Scope (message 3).** The first version went beyond the brief: a hash chain with a verify endpoint, a rejection reason, dark mode, extra search phrasings, a PDF generator in the repo and long docs. I asked for only what is absolutely needed and it cut the rest.
3. **"Didn't get hired" (messages 4 and 5).** Claude read it as rejected only, so candidates still at Offer were left out. I argued for "not Hired", and Claude now returns both groups with the pending ones labelled.
4. **Parser or LLM (messages 6 and 7).** Claude wrote a deterministic parser. I asked whether an LLM could read free-form questions, and chose to keep the parser as the default with an optional LLM fallback.
5. **Hash chain (messages 8 and 9).** Claude dropped it in the cleanup because the triggers already block edits. I had it restored with the verify endpoint, since anyone with the database file can drop the triggers.
6. **Vercel storage (messages 11 and 12).** Claude shipped the demo on temporary storage and said so. I insisted on a hosted Postgres so history persists.

## 2. Mistakes the AI made

All three were found in the full test pass (message 10), then fixed and given regression tests.

- **History could be overwritten.** The audit-log triggers blocked UPDATE and DELETE but not `INSERT OR REPLACE`, which silently replaced an event. Found by probing the database directly.
- **Some names weren't searchable.** Search could not find accented or non-Latin names, and hyphenated names matched poorly. Found by testing.
- **No query length limit.** The cleanup pass dropped it, and a 50,000-character query took seconds.

## 3. Design decisions and trade-offs

These are the choices behind the disagreements above.

- **"Didn't get hired".** The search means "reached Offer and is not Hired". Candidates still at Offer are labelled pending, and the reasoning is in the README.
- **Deterministic parser by default.** Results are repeatable and need no API key or network call. The cost is that it only understands the phrasings it was built for, which is why the LLM fallback is optional and only runs when a key is set.
- **Hash chain kept.** The triggers stop the application from editing history, and the hash chain makes any edit to the database file visible through the verify endpoint.
- **Hosted Postgres.** History persists across restarts and deploys. The cost is a second database backend and a connection string to configure, with SQLite kept for local runs.

## 4. Testing

Message 10 covers running the tests in several timezones, probing the database directly, odd inputs (accents, Devanagari, an HTML-injection name, a 50,000-character query), parallel requests, and a restart on the same database. After the Postgres change, the tests ran against both backends. Not covered: a visual browser check.