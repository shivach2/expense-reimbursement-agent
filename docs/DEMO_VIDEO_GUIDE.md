# Demo Video Guide (YouTube link required)

The rules require **a YouTube link to a demo video that showcases the key features and demonstrates the user experience**, and
"Demo Quality" is one of the six evaluation criteria (effectiveness and clarity). This guide gives you a shot list, a word-for-word script,
the preparation steps and the upload steps. Target length: **about 5 minutes (4:30 to 5:30)**. Judges watch many videos; clarity beats length.

## 1. What the video must prove (map to the evaluation criteria)
| Criterion | Show this on screen |
|---|---|
| Innovation and creativity | Policy is a *document*: edit "5,000" to "7,000" and the claim changes with no code change |
| Technical complexity | The architecture diagram: which steps are LLMs, which are deterministic, the grounding check |
| User experience | Drop bills, get a claim, answer only 5 questions, submit |
| Explainability | The "Why?" panel with the clause and the verbatim quote |
| Code quality / testing | A terminal showing `133 passed`, 100% coverage and `ruff` passing |
| Documentation | The README and the design document on GitHub (diagrams rendered) |

## 2. Preparation (30 minutes, do it once, off camera)
1. Start clean: `cd backend && CLAIM_TODAY=2026-10-12 uvicorn app.main:app --port 8000`, open http://localhost:8000 in a **fresh browser profile**
   (no bookmarks bar, no other tabs, notifications off). Browser zoom 110-125% so text is readable at 1080p.
2. **Dry-run the whole demo once** so everything is cached. The first time you edit the policy to 7,000 the AI re-reads the document (10-20 s);
   after one dry run it is instant on camera. The chat also needs your API key, so confirm the key is set in `.env` (never show `.env` on screen).
3. Reload the page for a fresh session before recording (each page load is a new session). Click **Reset to original** in the Policy tab.
4. Prepare a second window with a terminal in the project folder (large font) and the GitHub repository page open on `docs/TECHNICAL_DESIGN.md`.
5. Run these once so you know the output: `cd backend && python -m pytest -q --cov=app` and `cd .. && ruff check backend tools`.
6. Close Slack/Teams/email. Turn on Do Not Disturb. Check that no real names, keys or company data appear on screen (all demo data is synthetic).
7. Recording: OBS Studio (free, Windows/macOS/Linux) or QuickTime (macOS) or Xbox Game Bar (Windows). **1920x1080, 30 fps, a headset microphone**,
   quiet room. Record the screen plus audio only; a face camera is optional.

## 3. Shot list and script
Speak at a calm pace (about 140 words per minute). `[ACTION]` lines are what you do; the quoted text is what you say.

| Time | Screen | Script |
|---|---|---|
| 0:00 | Title slide or the README header | "Hi, this is the Expense and Reimbursement Agent, our entry for Track 1. Employees waste hours turning a pile of bills into a claim: typing details, picking categories, looking up limits, and finding out only after submission that something was over the limit. Our assistant does that work, and, importantly, it reads the company's policy documents the way a finance reviewer would." |
| 0:30 | `docs/TECHNICAL_DESIGN.md`, the architecture diagram | "Here is how it works. A vision model reads each bill. A second AI step reads the policy documents and turns them into structured rules, and every rule must carry a verbatim quote from the policy or it is rejected. A third step classifies each bill, with its reasoning. Then plain, deterministic code does all the money: caps, partial reimbursement, currency conversion, duplicates. AI interprets; code enforces. That is what keeps financial accuracy." |
| 1:00 | App, Claim tab. `[ACTION]` click **Try with the demo receipts** | "Let's try it. These are 24 synthetic bills: photos, PDFs, a blurry one, a crumpled one, dollar and Singapore-dollar bills, and three duplicates. In real use you drag your own files here." |
| 1:20 | Summary card and questions | "In seconds: forty thousand rupees on the bills, twenty-three thousand reimbursable under policy, and the system needs only five answers, not twenty-four forms. Three duplicates, an expired receipt and a personal expense were left out automatically." |
| 1:50 | `[ACTION]` expand **Why?** on the Lotus Grove Hotel bill | "Every decision is explained. This hotel bill is seven thousand one hundred and sixty-eight rupees. The AI explains why it is lodging, cites policy clause TEP 2.1 with the exact sentence, and shows the arithmetic: five thousand reimbursed, the excess is not reimbursable. It also cites the grade clause that lets a manager claim lodging at all." |
| 2:20 | `[ACTION]` click the chip **Why was my hotel reduced?** | "The assistant answers from the policy documents with the same clause reference, for both hotel bills." |
| 2:45 | Policy tab | "Now the key idea. Nothing about limits is coded. An LLM read these documents and extracted this table, nine limits, each tied to a clause, each backed by a quote that was verified." |
| 3:05 | `[ACTION]` change `INR 5,000 per night` to `INR 7,000 per night`, click **Save** | "Finance changes one sentence: five thousand becomes seven thousand. The AI re-reads the document, the table updates, and the claim is recalculated: twenty-three thousand becomes twenty-six and a half thousand. No code change, no release." |
| 3:35 | `[ACTION]` **Reset to original**; back on Claim, answer the five questions; click **Submit claim**; open **Finance system** | "I put the policy back and answer what the system could not know: a missing date, two approval notes, and one business purpose per trip. The claim is ready, I submit it, and it lands in the mock finance system with a reference number." |
| 4:10 | Terminal: `python -m pytest -q --cov=app` then `ruff check backend tools` | "Quality: one hundred and thirty-three automated tests, one hundred percent statement coverage, no LLM calls in tests because the models are faked, and lint passes. We also measured the AI on 24 bills with ground truth: every field extracted correctly, twenty-three of twenty-four categories, all duplicates found, five questions for twenty-four bills." |
| 4:40 | README on GitHub (scroll the doc list) | "Everything is documented: a technical design document with architecture and flow diagrams, setup and Docker deployment instructions, a test report, and a mapping to the evaluation criteria. All data is synthetic. Thank you." |

Total about 5:00. If you run long, drop the chat chip (2:20) first.

## 4. Do and don't
* **Do** keep the cursor still while speaking, and zoom/highlight the numbers you mention. **Do** show the clause quote on screen for at least 3 seconds.
* **Do** mention the track by name in the first 30 seconds. **Do** state honestly that the data is synthetic and the finance system is a mock.
* **Don't** show `.env`, API keys, the browser's saved passwords or your company's name or systems.
* **Don't** rely on live LLM latency for the first-time policy edit: use the dry-run trick above.
* If something fails mid-take, stop, fix, and re-record that section; you can trim and join clips in any editor (Clipchamp, iMovie, DaVinci Resolve).

## 5. Editing (optional, 15 minutes)
Trim silences, add a title card (the project name and "Track 1"), and on-screen captions for key numbers (INR 23,053, 5 questions, 133 tests). Export **MP4, H.264, 1080p**.

## 6. Upload to YouTube
1. Open https://studio.youtube.com, click **Create > Upload videos**, choose the MP4.
2. **Title:** `Expense & Reimbursement Agent: AI that reads the bills and the policy (Track 1 demo)`
3. **Description:** use the template below. Timestamps starting at `0:00` become chapters automatically.
4. **Audience:** "No, it's not made for kids". Thumbnail optional (a screenshot of the claim page works).
5. **Visibility: choose "Unlisted" or "Public".** Both can be opened by anyone with the link and **without any permission request**, which the rules require.
   **Do not choose Private.**
6. Save, copy the link, and **open it in a private/incognito window to confirm it plays without logging in**.
7. Paste the link in `README.md` (section "Demo video"), commit and push, and include it in your submission message.
8. Upload early: YouTube needs a few minutes to process HD after upload.

Description template
```
Expense & Reimbursement Agent - Track 1 submission.
An AI assistant that turns a pile of receipts into a policy-checked, explained, submission-ready claim. It reads the policy documents with an LLM,
verifies every extracted rule against a verbatim quote, and enforces them with deterministic code, so a policy change needs no code change.

Code and documentation: <YOUR GITHUB REPO URL>
All data in this demo is synthetic (fictional company, policies, employee and receipts).

Chapters
0:00 Problem and idea
0:30 Architecture: AI interprets, code enforces
1:00 Drop in 24 bills
1:50 Explainable decisions with policy clauses
2:45 Policy as a document: change a limit, no code change
3:35 Answer questions and submit
4:10 Tests, coverage and measured accuracy
4:40 Documentation

Stack: Python, FastAPI, Pydantic AI, Claude (any provider via one setting), SQLite, 133 automated tests.
```

## 7. Final checklist
- [ ] Track named in the first 30 seconds; architecture diagram shown; AI-versus-deterministic split explained
- [ ] Demo shows upload, claim, questions, explanation with clause quote, policy edit, submit, finance tab
- [ ] Terminal shows tests, coverage and lint passing
- [ ] No keys, no company data, no real names on screen; synthetic-data statement made
- [ ] Visibility is Unlisted or Public and the link works in an incognito window
- [ ] Link is in the README and in the submission message
