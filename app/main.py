"""
SMS feedback API: Twilio + OpenAI.
Receives SMS via Twilio webhook, uses ChatGPT to converse until feedback is clear, replies via Twilio.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI

# In-memory conversation store: phone_number -> list of {"role": "user"|"assistant", "content": "..."}
conversations: dict[str, list[dict]] = {}

FEEDBACK_SYSTEM_PROMPT = """You are a friendly feedback assistant over SMS. Your only job is to gather clear, actionable feedback from the user.

- Keep replies SHORT (SMS-friendly: 1-3 sentences, under 320 chars when possible).
- Be conversational and warm. Ask one question at a time.
- If the user's message is vague, brief, or unclear, ask a single short follow-up to clarify (e.g., "What worked best?" "Anything we could improve?").
- Once you have clear, specific feedback (what they liked, what could improve, or a clear "no feedback"), acknowledge it and thank them. You can say something like "Thanks, we've got your feedback!" and then stop asking.
- Do not lecture, repeat long summaries, or send paragraphs. Emojis are OK sparingly.
- If the user says they're done or have nothing to add, accept that and thank them."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Optional: clear or persist conversations on shutdown
    # conversations.clear()


app = FastAPI(title="SMS Feedback API", lifespan=lifespan)
client_openai: OpenAI | None = None


def get_openai():
    global client_openai
    if client_openai is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        client_openai = OpenAI(api_key=api_key)
    return client_openai


def get_or_create_history(phone: str) -> list[dict]:
    if phone not in conversations:
        conversations[phone] = [
            {"role": "system", "content": FEEDBACK_SYSTEM_PROMPT},
        ]
    return conversations[phone]


def get_chat_reply(phone: str, user_message: str) -> str:
    history = get_or_create_history(phone)
    history.append({"role": "user", "content": user_message})

    client = get_openai()
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=history,
        max_tokens=300,
        temperature=0.7,
    )
    reply = (resp.choices[0].message.content or "").strip()
    history.append({"role": "assistant", "content": reply})
    return reply


@app.get("/")
async def root():
    return {"service": "SMS Feedback API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sms/incoming")
async def twilio_webhook(
    Body: str = Form(""),
    From: str = Form(""),
    To: str = Form(""),
):
    """
    Twilio sends incoming SMS here. We reply with TwiML so Twilio sends our message back.
    Configure your Twilio number's webhook URL to: https://your-domain/sms/incoming
    """
    body = (Body or "").strip()
    phone = (From or "").strip() or "unknown"
    if not body:
        resp = MessagingResponse()
        resp.message("Send any message to share your feedback—we'll ask until we have it clear. Thanks!")
        return Response(content=str(resp), media_type="application/xml")

    try:
        reply_text = get_chat_reply(phone, body)
    except Exception as e:
        reply_text = "Something went wrong on our end. Please try again in a moment."
        # Log e in production

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(content=str(twiml), media_type="application/xml")
