# Submission Checklist

Rules recap: submit by **12 Oct 2026**; the code goes to a **personal GitHub** repository and you share the link **with all the documents** and the
**YouTube demo link**; do not ask for access permissions to any platform; if hosted, share the link too.

## 1. What must be in the GitHub repository
| Required item | Where it is |
|---|---|
| Project overview + track selected | `README.md` (top), `docs/TECHNICAL_DESIGN.md` section 1 |
| System architecture and flow diagrams | `docs/TECHNICAL_DESIGN.md` sections 3 to 6 (Mermaid; GitHub renders them) |
| Setup and deployment instructions | `docs/SETUP_AND_DEPLOYMENT.md`, `README.md` quick start, `Dockerfile`, `docker-compose.yml` |
| Code explanations and assumptions | `docs/TECHNICAL_DESIGN.md` sections 8 and 9 |
| Unit tests | `backend/tests/` (133 tests), results in `docs/TEST_REPORT.md`, CI in `.github/workflows/ci.yml` |
| Evaluation-criteria mapping | `docs/EVALUATION_MAPPING.md` |
| Demo video link | `README.md` section "Demo video" (you add the YouTube URL) |
| Hosted link (optional) | `README.md` section "Hosted demo" (only if you host) |

## 2. Before you push (10 minutes)
```bash
cd backend && python -m pytest -q --cov=app                  # expect: 133 passed, 100% coverage
cd .. && ruff check backend tools && ruff format --check backend tools   # expect: All checks passed
```
Fill the placeholders (search for `YOUR_` and `<YOUR`):
- [ ] `README.md`: GitHub URL, YouTube URL, hosted URL (or delete that line)
- [ ] `docs/DEMO_VIDEO_GUIDE.md` description template: GitHub URL
- [ ] Optionally put your name and team in the README "Team" line

Screenshots (the README embeds five images; without them GitHub shows broken images):
- [ ] `docs/screenshots/` contains `01_claim_and_chat.jpg`, `02_explainable_decision.jpg`, `03_policy_ai_interpreted.jpg`, `04_policy_changed_no_code.jpg`, `05_submitted.jpg`.
  Capture them from the running app: 01 = claim page after "Try with the demo receipts" with a chat answer; 02 = the expanded **Why?** panel of the hotel bill;
  03 = Policy tab before editing; 04 = Policy tab after changing 5,000 to 7,000 (status line shows the new total); 05 = claim page after submit (reference shown).
  Use 1280-1400 px wide browser windows; JPEG or PNG renamed to the same file names.

Confidentiality checks (the rules forbid company data, PII and secrets in the repository):
```bash
git grep -nE "sk-ant|AIza[0-9A-Za-z_-]{20,}|(API_KEY|SECRET|TOKEN)=[A-Za-z0-9_-]{16,}"   # expect: no output
git ls-files | grep -E "(^|/)\.env$"                                                      # expect: no output
git grep -niE "<your employer's name>|<internal system names>|<your company email domain>"   # expect: no output (fill in your own terms)
```
- [ ] The repository contains **only synthetic data** (fictional "Acme Corp" policies, employee, receipts). No real receipts, no real policies.
- [ ] `.env` is not tracked (`.gitignore` covers it). Only `.env.example` is committed.
- [ ] **Commit `data/synthetic/` and `data/cache/`** (both are synthetic). They make the demo work offline and let CI/tests pass without any key.

## 3. Create the repository and push
1. On github.com (personal account): **New repository**, name e.g. `expense-reimbursement-agent`, **Public** (so reviewers need no permission), no README/licence/gitignore (you already have them).
2. In the project folder:
```bash
git init                                  # skip if already a repository
git add -A
git status                                # review: no .env, no .venv, no backend/runtime
git commit -m "Expense & Reimbursement Agent: AI-native reimbursement assistant (Track 1)"
git branch -M main
git remote add origin https://github.com/<your-username>/expense-reimbursement-agent.git
git push -u origin main
```
3. If prompted for a password use a **personal access token** (GitHub does not accept account passwords for pushes), or sign in with GitHub CLI (`gh auth login`).
4. If you cannot push from your office PC, push from the machine you rebuilt the project on (the `rebuild_prompt/` pack exists for that). Do not move company
   data or credentials between machines; the project contains none.

## 4. Verify what reviewers will see (5 minutes)
- [ ] Open the repository URL in a **private/incognito window** (not logged in): README renders, no access prompt.
- [ ] `docs/TECHNICAL_DESIGN.md` on GitHub shows the diagrams (Mermaid renders natively). If a diagram shows as code, check the fence is exactly three backticks plus `mermaid`.
- [ ] **Actions** tab: the `tests` workflow is green (needs the committed `data/cache/` and `data/synthetic/`). Optionally add the badge to the README:
  `![tests](https://github.com/<you>/<repo>/actions/workflows/ci.yml/badge.svg)`
- [ ] Fresh-clone proof:
```bash
git clone https://github.com/<you>/expense-reimbursement-agent.git /tmp/verify && cd /tmp/verify
python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements-dev.txt
cd backend && python -m pytest -q          # expect: 133 passed
```

## 5. The YouTube video
Follow `docs/DEMO_VIDEO_GUIDE.md`. Visibility must be **Unlisted or Public** (never Private). Test the link in an incognito window. Paste it into the README
("Demo video"), commit and push again.

## 6. Hosted link (optional)
Only if you host (see `docs/SETUP_AND_DEPLOYMENT.md` section 6). For a public link prefer **safe demo mode (no API key)**; the app has no authentication.

## 7. The message to send
```
Subject: Track 1 submission - Expense & Reimbursement Agent

GitHub repository (code + all documents): https://github.com/<you>/expense-reimbursement-agent
Technical design document: https://github.com/<you>/expense-reimbursement-agent/blob/main/docs/TECHNICAL_DESIGN.md
Demo video (YouTube): <YOUTUBE URL>
Hosted demo (optional): <URL or "not hosted">

Track: 1 - Expense & Reimbursement Agent.
All data is synthetic; no company or personal data is used. 133 automated tests, 100% statement coverage of the application package.
```

## 8. Final gate
- [ ] Repository public, README renders, diagrams render, CI green
- [ ] Documents present: design (overview + track, diagrams, setup/deployment, code explanations and assumptions)
- [ ] Demo video link works logged out; link is in the README and the message
- [ ] No secrets, no company data; only synthetic data
- [ ] Submitted before **12 Oct 2026** (do it early; do not wait for the last hour)
