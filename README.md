# Treehacks 2026

SMS feedback API + Claude coder (Twilio, Supabase, Anthropic). **The running app is in `backend/`.**

## Quick start

From repo root:

```bash
pip install -r backend/requirements.txt
python run.py
```

Or from the backend folder:

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Set in `.env` (in `backend/` or repo root):

- `ANTHROPIC_API_KEY` (required)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (for DB and feedback storage)
- `PORT` (optional, default 8000)

Twilio webhook: **POST** `https://YOUR_HOST/sms/incoming`

## What’s what

| Path | Purpose |
|------|--------|
| **`backend/`** | Main API (Flask): Twilio SMS → Claude, feedback saved to DB; projects, plans, coder (Claude updates code, creates PR). Use this. |
| **`app/`** | Old standalone FastAPI SMS API (OpenAI, no DB). Deprecated; use `backend/` instead. |
| **`run.py`** | Starts the backend from repo root so you can run `python run.py`. |

See **`backend/README.md`** for full API and setup (migrations, env, endpoints).
