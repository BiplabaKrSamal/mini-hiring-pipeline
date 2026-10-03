# Chat log: Mini Hiring Pipeline

My messages are in quotes, Claude's replies follow, and tool work is in italics.

---

## 1. Me

> Mini Hiring Pipeline: a recruiter manages candidates for one job. Each candidate moves through Applied → Screening → Interview → Offer → Hired and can be rejected at any point before being hired. Build a small web app that lets her run this pipeline and find candidates with a single search box. Deliverables: a PDF, a README, the GitHub repo, and my AI chat logs, including one place where I disagreed with the AI.

## 1. Claude

*Claude planned FastAPI, a SQLite events table protected by triggers, a hand-written search parser and one static HTML page. It wrote the code, tests, README and a PDF generator, and ran the tests.*

The first version is ready. It includes an audit log with a hash chain and a verify endpoint, a rejection reason, a dark mode, extra search phrasings and a PDF generator in the repo. Search is a deterministic parser, and I read "didn't get hired" as rejected after reaching Offer, so anyone still at Offer is left out of that search.

---

## 2. Me

> With proper commit messages, human not just AI-genearated

## 2. Claude

*Claude rewrote its conventional commit messages as short plain titles with brief bodies.*

Done. Each title is now a short plain sentence, with a line or two of explanation where needed.

---

## 3. Me

> Thanks. Now remove the bloat and unecessary content and keep only the absolutely needed content and essence.

## 3. Claude

*Claude cut the extras, rewrote the affected files and reran the tests.*

I've trimmed the project to what the brief needs.

**What I cut:**
- The hash chain and its `/api/audit/verify` endpoint. The triggers already block edits.
- The rejection reason, dark mode, result chips and the "did you mean" name suggestions.
- Extra date phrasings and "stuck" synonyms in search.
- The PDF generator and the PDF copy inside the repo.
- Half the README and the AI log.

---

## 4. Me

> You treated "didn't get hired" as rejected only. But the brief says "reached Offer but didn't get hired". Someone still sitting at Offer hasn't been hired either. Why leave them out?

## 4. Claude

Fair point. The two readings differ: "rejected after Offer" is a final outcome, while "not Hired" also covers people still waiting. If the recruiter wants everyone who got an offer and isn't hired, the second reading is more useful.

I can return both groups and label the pending ones as "pending" so she can tell them apart.

## 5. Me

> Do that, and put the reasoning in the README.

## 5. Claude

*Claude changed the search to "reached Offer and is not Hired", marked candidates still at Offer as pending, added a test, and documented the choice in the README.*

Done. Both groups come back, with the pending ones labelled.

---

## 6. Me

> The brief says "when she types something that doesn't make sense, she should be told why". Could an LLM read free-form questions better than your parser?

## 6. Claude

It could handle looser wording, but there are costs. It needs an API key, adds latency to every search, and can give different results on different runs. With a parser the same query always gives the same answer, which suits an audit-focused tool, and the error messages can say exactly what wasn't understood.

## 7. Me

> Fair. Keep the parser as the default, but add an optional LLM fallback that only runs when an API key is set.

## 7. Claude

*Claude added the fallback behind an environment variable and a test with it switched off.*

Done. Without a key the app behaves exactly as before.

---

## 8. Me

> Why did you remove the hash chain? Anyone with the database file can drop the triggers and edit history.

## 8. Claude

I cut it because the triggers already block UPDATE and DELETE, and the brief didn't ask for tamper-evidence beyond that. You're right that the triggers only protect against the application, not against someone editing the file. A hash chain would make any edit visible.

## 9. Me

> Keep it, and keep the verify endpoint.

## 9. Claude

*Claude restored the hash chain and `/api/audit/verify`, with a test that edits a row and checks that verification fails.*

Restored. The README now lists the hash chain as the tamper-evidence layer.

---

## 10. Me

> Do all the tests.

## 10. Claude

*Claude ran the tests in several timezones, probed the database directly, tried odd inputs and parallel requests, and found three bugs.*

Testing found three real bugs, and I fixed all three.

**Bugs found and fixed:**
- **History could be overwritten.** `INSERT OR REPLACE` bypassed the update and delete triggers and silently replaced an event. A third trigger now blocks it, and there's a regression test.
- **Some names weren't searchable.** Search only handled a to z, so "Zoë", "Müller" and Devanagari names returned nothing, and hyphenated names matched poorly. Search now ignores accents and splits on hyphens, with a test.
- **No query length limit.** My cleanup pass had dropped it, and a 50,000-character query took seconds. Queries over 200 characters now get a clear error.

---

## 11. Me

> Deploying the project on vercel.

## 11. Claude

*Claude prepared `app/main.py` for Vercel and ran Vercel's CLI build locally.*

I can't deploy from here. On Vercel the database lives in a temporary `/tmp` folder, so data won't persist and every instance starts with the demo candidates. Treat the live link as a demo. For real persistence the fix is a hosted Postgres, and I can port it if you want.

## 12. Me

> A demo that forgets everything isn't good enough. I want history to persist, so use a hosted Postgres.

## 12. Claude

*Claude added a Postgres backend selected by a connection string, kept SQLite for local runs, and ran the tests against both.*

Done. The cost is a second database backend and a connection string to configure, but history now survives restarts and deploys.