import requests
import os
from typing import Dict, Optional
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from root .env file
root_dir = Path(__file__).resolve().parent.parent.parent
env_path = root_dir / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)


class PokeNotifier:
    """
    Service for sending notifications to developers via Poke SMS
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("POKE_API_KEY")
        self.webhook_url = "https://poke.com/api/v1/inbound-sms/webhook"
        self.rate_limit = 1  # requests per second (from docs)

        if not self.api_key:
            raise ValueError("POKE_API_KEY not set")

    def notify_poke_assistant(self, message: str) -> Dict:
        """
        Notify the Poke Assistant with a message by using a webhook

        Args:
            message: The SMS content to send to Poke Assistant

        Returns:
            Response from Poke API
        """
        try:
            response = requests.post(
                self.webhook_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={"message": message},
                timeout=10
            )

            response.raise_for_status()

            logger.info(f"Poke notification sent: {message[:50]}...")
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Poke notification: {e}")
            raise
