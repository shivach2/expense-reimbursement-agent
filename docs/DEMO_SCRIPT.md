# Demo script

The full, current demo plan (shot list, word-for-word narration, preparation, recording and YouTube upload steps) is in
**[DEMO_VIDEO_GUIDE.md](DEMO_VIDEO_GUIDE.md)**. This page only lists the commands to start the app for a live demo.

```bash
cd backend
CLAIM_TODAY=2026-10-12 uvicorn app.main:app --port 8000        # Windows PowerShell: $env:CLAIM_TODAY="2026-10-12"; uvicorn app.main:app --port 8000
```
Open http://localhost:8000 and click **Try with the demo receipts**. The claim, "Why?" explanations and the policy viewer work from cached AI results
without a key; the chat and the policy-edit step need the API key in `.env`.

Five-minute outline: problem and track (0:00) - architecture diagram (0:30) - drop 24 bills (1:00) - explanations with clause quotes (1:50) -
policy edit 5,000 to 7,000 changes the claim (2:45) - answer questions and submit (3:35) - tests, coverage and accuracy (4:10) - documentation (4:40).
