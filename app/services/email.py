import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    Dispatches transactional emails via configured backend:
    'mock', 'resend', or 'sendgrid'.
    """
    backend = current_app.config.get("EMAIL_BACKEND", "mock").lower()
    from_email = current_app.config.get("EMAIL_FROM", "GCIR Civic Alerts <alerts@gcir.local>")

    if backend == "mock":
        logger.info(f"--- [MOCK EMAIL DISPATCH] ---")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body snippet: {text_body[:150] if text_body else html_body[:150]}...")
        logger.info(f"-----------------------------")
        return True

    elif backend == "resend":
        api_key = current_app.config.get("RESEND_API_KEY")
        if not api_key:
            logger.error("Resend API key missing.")
            return False
        try:
            res = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "from": from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                    "text": text_body or html_body
                },
                timeout=10
            )
            return res.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Resend email dispatch error: {e}")
            return False

    elif backend == "sendgrid":
        api_key = current_app.config.get("SENDGRID_API_KEY")
        if not api_key:
            logger.error("SendGrid API key missing.")
            return False
        try:
            res = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": from_email.split("<")[-1].replace(">", "").strip() if "<" in from_email else from_email},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html_body}]
                },
                timeout=10
            )
            return res.status_code in (200, 202)
        except Exception as e:
            logger.error(f"SendGrid email dispatch error: {e}")
            return False

    logger.warning(f"Unknown email backend '{backend}', skipping send.")
    return False
