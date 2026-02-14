-- User feedback: stored when Twilio/Claude has determined clear feedback from each user (SMS).
CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    phone_number TEXT NOT NULL,
    summary TEXT NOT NULL,
    raw_messages TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_phone ON user_feedback(phone_number);
CREATE INDEX IF NOT EXISTS idx_user_feedback_created_at ON user_feedback(created_at DESC);

COMMENT ON TABLE user_feedback IS 'Feedback from users via Twilio SMS once Claude has determined it is clear';
