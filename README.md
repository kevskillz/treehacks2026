# SMS Feedback API

API-only service: **Twilio** for SMS in/out and **OpenAI (ChatGPT)** to handle every message and reply, gathering user feedback and continuing the conversation until the feedback is clear.

## Flow

1. User texts your Twilio number.
2. Twilio `POST`s to your `/sms/incoming` webhook with `Body`, `From`, `To`.
3. The API appends the message to that user’s conversation, calls the ChatGPT API with full history and a feedback-focused system prompt.
4. The model replies (short, SMS-friendly); the API returns **TwiML** so Twilio sends that reply back to the user.
5. Conversation continues until the model decides feedback is clear, then it thanks the user and stops asking.

## Setup

### 1. Environment variables

Create a `.env` (or set in your host):

- `OPENAI_API_KEY` – required; your OpenAI API key.
- `OPENAI_MODEL` – optional; default `gpt-4o-mini`. Use `gpt-4o` for stronger reasoning.
- Twilio credentials are **not** needed in the app for the webhook flow (Twilio sends HTTP to you; you respond with TwiML). Only needed if you add outbound SMS or other Twilio APIs.

### 2. Install and run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Twilio webhook

- In [Twilio Console](https://console.twilio.com/) → Phone Numbers → your number → Messaging.
- Set **“A MESSAGE COMES IN”** to **Webhook**, URL:  
  `https://YOUR_PUBLIC_URL/sms/incoming`  
  Method: **POST**.

Use a tunnel (e.g. ngrok) for local testing:

```bash
ngrok http 8000
# set Twilio webhook to https://YOUR_NGROK_URL/sms/incoming
```

## Endpoints

| Method | Path            | Description                          |
|--------|-----------------|--------------------------------------|
| GET    | `/`             | Service info and link to docs        |
| GET    | `/health`       | Health check                         |
| POST   | `/sms/incoming` | Twilio webhook for incoming SMS      |

All logic is in the API; no frontend. The assistant “speaks” by replying to each SMS until feedback is clear.
