# Backend: SMS Feedback + Coder (Claude)

- **Twilio SMS** → Claude gathers feedback until clear; when determined, **feedback is stored in the DB** (`user_feedback`).
- **No tweet tracking.** All project/plan data comes from the database.
- **Claude** is used for plans, issue enrichment, and code changes + PR (tool use: read_file, write_file, run_bash).

## Flow

1. User texts your Twilio number.
2. Twilio POSTs to `/sms/incoming`. The app replies with TwiML using Claude.
3. Conversation continues until Claude has clear feedback; then Claude ends with `FEEDBACK_SUMMARY: ...`.
4. The handler **saves one row to `user_feedback`** (phone_number, summary, optional raw_messages) and clears in-memory history for that phone.
5. Projects/plans/coder workflow use **DB only** (no tweet pipeline). Plan generation uses project title/description from the DB.

## Setup

- **Environment:** `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, optional `PORT`.
- **DB:** Run migration `supabase/migrations/00005_user_feedback.sql` for the feedback table.
- **Run:** `pip install -r requirements.txt` then `python app.py` or `flask run` (port 8000).
- **Twilio:** Set webhook to `https://YOUR_HOST/sms/incoming` (POST).

## Endpoints (summary)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/sms/incoming` | Twilio webhook (saves to DB when feedback determined) |
| GET | `/api/feedback` | List recent feedback |
| GET | `/api/feedback/by-phone/<phone>` | Feedback for one phone |
| GET | `/api/projects/<id>` | Project + plan + logs (no tweets) |
| POST | `/api/projects/<id>/approve` | Approve project, create issue, optional plan |
| POST | `/api/plans/<id>/approve` | Approve plan, trigger Claude coder (update code, create PR) |
| … | … | Other project/plan/repo/coder routes unchanged |

## Stack

- **Flask** – API
- **Supabase** – DB (projects, plans, **user_feedback**, repo_configs, etc.)
- **Twilio** – SMS in/out
- **Anthropic Claude** – feedback conversation, plan generation, issue enrichment, code edits + PR
