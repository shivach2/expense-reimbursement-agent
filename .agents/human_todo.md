# Human Manual To-Do List

All automated stages (8, 9, 10) are complete. The following require a human.

## 1. Capture 5 screenshots
Start the server: from `backend/` with venv activated, run:
`$env:CLAIM_TODAY="2026-10-12"; python -m uvicorn app.main:app --port 8000 --reload`
Then open http://localhost:8000 in Chrome and capture:

| # | Filename | What to show |
|---|---|---|
| 1 | `docs/screenshots/01_upload.jpg` | Upload panel with 3–5 receipt images dragged in, before sending |
| 2 | `docs/screenshots/02_extraction.jpg` | Chat showing extracted receipts table or extraction summary |
| 3 | `docs/screenshots/03_questions.jpg` | The 5 clarifying questions the agent asked |
| 4 | `docs/screenshots/04_claim_summary.jpg` | Final claim summary (eligible INR 23,053) with breakdown |
| 5 | `docs/screenshots/05_policy_chat.jpg` | Chat window showing a policy question answered with clause reference |

Save as JPG, ~1280×800px.

## 2. Fill in README.md placeholders
Open `README.md` and replace:
- `YOUR_YOUTUBE_URL` → your YouTube video URL
- `YOUR_HOSTED_URL` → your hosted demo URL (if any; otherwise remove that line)
- `YOUR_NAME` → your name

## 3. Record and upload demo video
See `docs/DEMO_VIDEO_GUIDE.md` for the script and upload instructions.
Target: 3–5 minute walkthrough showing upload → extraction → questions → claim.
Upload to YouTube (unlisted or public) and copy the URL into README.md.

## 4. Create public GitHub repository and push
See `docs/SUBMISSION_CHECKLIST.md` for the push checklist.
Ensure `.env` is NOT pushed (it is gitignored).
Command sequence:
```bash
git add -A
git commit -m "Final submission: stages 0-10 complete"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

## 5. Fill in GitHub repo URL
Open `docs/DEMO_VIDEO_GUIDE.md` and replace `<YOUR GITHUB REPO URL>` with your actual GitHub URL.

## 6. Verify GitHub renders README correctly
Open your GitHub repo in an incognito window.
Verify:
- Mermaid diagrams render (GitHub renders mermaid in README.md natively)
- Screenshots appear (they will be blank until step 1 is done)
- All section links in the table of contents work

## 7. Send submission message
See the submission template in `docs/SUBMISSION_CHECKLIST.md` for the exact message to send.
Make sure you include: GitHub URL, YouTube URL, and your name.
