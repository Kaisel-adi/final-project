import logging
from typing import Any
import requests
import socket
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _clean_str(val: Any) -> str:
    """Safely strips leading/trailing whitespace and surrounding quotation marks."""
    if val is None:
        return ""
    s = str(val).strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def _get_email_config(key: str, default=None):
    from flask import current_app, has_app_context
    if has_app_context():
        return current_app.config.get(key, default)
    from app.config import Config
    return getattr(Config, key, default)


def get_effective_email_backend() -> str:
    """
    Determines active email backend.
    If EMAIL_BACKEND is set to 'mock' (or unset), but SMTP credentials
    (SMTP_HOST and SMTP_USER) are present in config/env and not in test mode,
    automatically upgrades backend to 'smtp'.
    """
    is_testing = bool(_get_email_config("TESTING", False))
    raw_backend = _clean_str(_get_email_config("EMAIL_BACKEND", "mock")).lower()

    if is_testing:
        return raw_backend or "mock"

    if raw_backend in ("smtp", "resend", "sendgrid", "brevo"):
        return raw_backend

    # Auto-detection when backend is mock/unset:
    if _clean_str(_get_email_config("BREVO_API_KEY", "")):
        logger.info("Auto-detected BREVO_API_KEY; upgrading email backend to 'brevo'.")
        return "brevo"

    if _clean_str(_get_email_config("RESEND_API_KEY", "")):
        logger.info("Auto-detected RESEND_API_KEY; upgrading email backend to 'resend'.")
        return "resend"

    if _clean_str(_get_email_config("SENDGRID_API_KEY", "")):
        logger.info("Auto-detected SENDGRID_API_KEY; upgrading email backend to 'sendgrid'.")
        return "sendgrid"

    smtp_host = _clean_str(_get_email_config("SMTP_HOST", ""))
    smtp_user = _clean_str(_get_email_config("SMTP_USER", ""))
    if smtp_host and smtp_user:
        logger.info("Auto-detected SMTP credentials; upgrading email backend to 'smtp'.")
        return "smtp"

    return "mock"


def _sanitize_from_email(from_email: str, backend: str, smtp_user: str) -> str:
    """
    Ensures the sender address is valid and accepted by mail servers.
    Gmail and major SMTP relays reject or discard emails from '@gcir.local'
    or emails where the sender differs from the authenticated SMTP username.
    """
    clean_from = _clean_str(from_email)
    clean_user = _clean_str(smtp_user)

    if backend == "smtp" and clean_user:
        if not clean_from or "@gcir.local" in clean_from or "@" not in clean_from:
            return f"GCIR Civic Alerts <{clean_user}>"
        if "<" in clean_from and ">" in clean_from:
            display_name = clean_from.split("<")[0].strip()
            return f"{display_name} <{clean_user}>" if display_name else f"GCIR Civic Alerts <{clean_user}>"
        if clean_from.lower() != clean_user.lower():
            return f"GCIR Civic Alerts <{clean_user}>"

    return clean_from or "GCIR Civic Alerts <gcir.alerts@gmail.com>"


def _dispatch_via_smtp(
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool,
    use_ssl: bool,
    from_email: str,
    to_email: str,
    msg: MIMEMultipart
) -> tuple[bool, str]:
    """
    Dispatches email via SMTP with automatic dual-port fallback
    (tries configured port first, falls back to Port 465 SSL or 587 STARTTLS).
    """
    clean_password = _clean_str(password).replace(" ", "")

    # Primary attempt
    primary_is_ssl = use_ssl or (port == 465)
    primary_is_tls = use_tls if not primary_is_ssl else False

    attempts = [
        {
            "port": port,
            "ssl": primary_is_ssl,
            "tls": primary_is_tls,
            "label": f"Port {port} ({'SSL' if primary_is_ssl else 'STARTTLS'})"
        }
    ]

    # Alternate fallback attempt
    alt_port = 465 if port != 465 else 587
    alt_is_ssl = (alt_port == 465)
    alt_is_tls = (alt_port == 587)
    attempts.append({
        "port": alt_port,
        "ssl": alt_is_ssl,
        "tls": alt_is_tls,
        "label": f"Fallback Port {alt_port} ({'SSL' if alt_is_ssl else 'STARTTLS'})"
    })

    last_error = ""

    for attempt in attempts:
        p = attempt["port"]
        ssl_mode = attempt["ssl"]
        tls_mode = attempt["tls"]
        label = attempt["label"]

        try:
            logger.info(f"Connecting to SMTP server {host}:{p} via {label} (timeout=12s)...")
            if ssl_mode:
                server = smtplib.SMTP_SSL(host, p, timeout=12)
            else:
                server = smtplib.SMTP(host, p, timeout=12)
                if tls_mode:
                    server.starttls()

            if user and clean_password:
                server.login(user, clean_password)

            server.send_message(msg)
            server.quit()
            logger.info(f"Successfully sent email to {to_email} via {host}:{p} ({label})")
            return True, f"Delivered via {label}"

        except smtplib.SMTPAuthenticationError as auth_err:
            last_error = f"SMTP Authentication failed on {label}: {auth_err}. Check your username and 16-character App Password."
            logger.error(last_error)
            # Credential issues will not succeed on another port
            return False, last_error

        except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError) as conn_err:
            last_error = f"{label} connection error: {conn_err}"
            logger.warning(f"{last_error}. Proceeding to next port if available...")

        except Exception as err:
            last_error = f"{label} dispatch error: {err}"
            logger.warning(f"{last_error}. Proceeding to next port if available...")

    if "101" in last_error or "unreachable" in last_error.lower():
        last_error += " [Render Free Tier blocks raw SMTP ports 25, 465, and 587. To send emails on Render, use an HTTPS API like Brevo (BREVO_API_KEY) or Resend (RESEND_API_KEY), or upgrade to a paid Render plan.]"

    logger.error(f"All SMTP attempts failed to {to_email}. Last error: {last_error}")
    return False, last_error


def send_email_with_status(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> tuple[bool, str]:
    """
    Dispatches email and returns a tuple: (success: bool, status_message: str).
    """
    backend = get_effective_email_backend()
    from_raw = _clean_str(_get_email_config("EMAIL_FROM", "GCIR Civic Alerts <gcir.alerts@gmail.com>"))
    smtp_user = _clean_str(_get_email_config("SMTP_USER", ""))
    from_email = _sanitize_from_email(from_raw, backend, smtp_user)

    if backend == "mock":
        logger.info("--- [MOCK EMAIL DISPATCH] ---")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body snippet: {text_body[:150] if text_body else html_body[:150]}...")
        logger.info("-----------------------------")
        return True, "mock"

    elif backend == "resend":
        api_key = _clean_str(_get_email_config("RESEND_API_KEY", ""))
        if not api_key:
            err = "Resend API key missing in environment."
            logger.error(err)
            return False, err
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
            if res.status_code in (200, 201):
                return True, "Delivered via Resend"
            err = f"Resend API error HTTP {res.status_code}: {res.text}"
            logger.error(err)
            return False, err
        except Exception as e:
            err = f"Resend dispatch error: {e}"
            logger.error(err)
            return False, err

    elif backend == "sendgrid":
        api_key = _clean_str(_get_email_config("SENDGRID_API_KEY", ""))
        if not api_key:
            err = "SendGrid API key missing in environment."
            logger.error(err)
            return False, err
        try:
            sender = from_email.split("<")[-1].replace(">", "").strip() if "<" in from_email else from_email
            res = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": sender},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html_body}]
                },
                timeout=10
            )
            if res.status_code in (200, 202):
                return True, "Delivered via SendGrid"
            err = f"SendGrid API error HTTP {res.status_code}: {res.text}"
            logger.error(err)
            return False, err
        except Exception as e:
            err = f"SendGrid dispatch error: {e}"
            logger.error(err)
            return False, err

    elif backend == "brevo":
        api_key = _clean_str(_get_email_config("BREVO_API_KEY", ""))
        if not api_key:
            err = "Brevo API key missing in environment (BREVO_API_KEY)."
            logger.error(err)
            return False, err
        try:
            sender_name = "GCIR Civic Alerts"
            sender_email = from_email
            if "<" in from_email and ">" in from_email:
                sender_name = from_email.split("<")[0].strip() or "GCIR Civic Alerts"
                sender_email = from_email.split("<")[-1].replace(">", "").strip()

            payload = {
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_body,
            }
            if text_body:
                payload["textContent"] = text_body

            res = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "api-key": api_key
                },
                json=payload,
                timeout=12
            )
            if res.status_code in (200, 201, 202):
                return True, "Delivered via Brevo (HTTPS REST API)"
            err = f"Brevo API error HTTP {res.status_code}: {res.text}"
            logger.error(err)
            return False, err
        except Exception as e:
            err = f"Brevo dispatch error: {e}"
            logger.error(err)
            return False, err

    elif backend == "smtp":
        host = _clean_str(_get_email_config("SMTP_HOST", ""))
        port_raw = _get_email_config("SMTP_PORT", 587)
        try:
            port = int(_clean_str(port_raw))
        except (ValueError, TypeError):
            port = 587

        user = _clean_str(_get_email_config("SMTP_USER", ""))
        password = _clean_str(_get_email_config("SMTP_PASSWORD", ""))
        use_tls = bool(_get_email_config("SMTP_USE_TLS", True))
        use_ssl = bool(_get_email_config("SMTP_USE_SSL", False))

        if not host:
            err = "SMTP_HOST is not configured in environment variables."
            logger.error(err)
            return False, err

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        return _dispatch_via_smtp(
            host=host,
            port=port,
            user=user,
            password=password,
            use_tls=use_tls,
            use_ssl=use_ssl,
            from_email=from_email,
            to_email=to_email,
            msg=msg
        )

    err = f"Unknown or unconfigured email backend '{backend}'."
    logger.warning(err)
    return False, err


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    Dispatches transactional email. Returns True if succeeded, False otherwise.
    Maintains complete backward compatibility for callers.
    """
    success, _ = send_email_with_status(to_email=to_email, subject=subject, html_body=html_body, text_body=text_body)
    return success
