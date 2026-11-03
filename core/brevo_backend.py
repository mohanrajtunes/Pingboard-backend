import requests
from email.utils import parseaddr
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailBackend(BaseEmailBackend):
    """Sends mail over HTTPS (port 443) because Render's free plan blocks SMTP ports."""

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            name, address = parseaddr(message.from_email)
            sender = {"email": address}
            if name:
                sender["name"] = name
            payload = {
                "sender": sender,
                "to": [{"email": to} for to in message.to],
                "subject": message.subject,
                "textContent": message.body,
            }
            response = requests.post(
                BREVO_URL,
                json=payload,
                headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                timeout=15,
            )
            if response.status_code >= 400:
                if self.fail_silently:
                    continue
                raise RuntimeError(f"Brevo API {response.status_code}: {response.text[:300]}")
            sent += 1
        return sent
