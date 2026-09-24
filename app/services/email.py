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

    elif backend == "smtp":
        host = current_app.config.get("SMTP_HOST")
        port = int(current_app.config.get("SMTP_PORT", 587))
        user = current_app.config.get("SMTP_USER")
        password = current_app.config.get("SMTP_PASSWORD", "")
        use_tls = current_app.config.get("SMTP_USE_TLS", True)
        use_ssl = current_app.config.get("SMTP_USE_SSL", False)

        if not host:
            logger.error("SMTP_HOST is not configured.")
            return False

        clean_password = password.strip().replace(" ", "") if password else ""

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to_email

            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                if use_tls:
                    server.starttls()

            if user and clean_password:
                server.login(user, clean_password)

            server.send_message(msg)
            server.quit()
            logger.info(f"Successfully sent email via SMTP to {to_email}")
            return True
        except Exception as e:
            logger.error(f"SMTP email dispatch error to {to_email}: {e}")
            return False

    logger.warning(f"Unknown email backend '{backend}', skipping send.")
    return False
