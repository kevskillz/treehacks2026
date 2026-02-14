from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/sms", methods=["POST"])
def sms_reply():
    incoming_msg = request.form.get("Body")
    resp = MessagingResponse()
    resp.message(f"You said: {incoming_msg}")
    return str(resp)

@app.route("/status", methods=["POST"])
def status_callback():
    message_sid = request.form.get("MessageSid")
    status = request.form.get("MessageStatus")
    print(f"{message_sid} is {status}")
    return "OK", 200

if __name__ == "__main__":
    app.run(port=5000)