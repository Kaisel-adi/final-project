"""
Email Dispatcher & SMTP Test Utility for GCIR.
Allows testing email dispatch and verifying SMTP configuration from the CLI.

Usage:
    python scripts/test_email.py
    python scripts/test_email.py --to your-email@domain.com
"""

import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app
from app.services.email import send_email


def main():
    parser = argparse.ArgumentParser(description="Test GCIR email dispatch and SMTP settings.")
    parser.add_argument("--to", help="Recipient email address (defaults to configured SMTP_USER or EMAIL_FROM)")
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        backend = app.config.get("EMAIL_BACKEND", "mock")
        recipient = args.to or app.config.get("SMTP_USER") or "test@example.com"

        print("=" * 60)
        print("GCIR Email Dispatch Diagnostic")
        print("=" * 60)
        print(f"Configured Backend: {backend}")
        print(f"From Address:       {app.config.get('EMAIL_FROM')}")
        print(f"Recipient:          {recipient}")

        if backend == "smtp":
            print(f"SMTP Host:          {app.config.get('SMTP_HOST')}")
            print(f"SMTP Port:          {app.config.get('SMTP_PORT')}")
            print(f"SMTP User:          {app.config.get('SMTP_USER')}")
            print(f"SMTP Use TLS:       {app.config.get('SMTP_USE_TLS')}")
            print(f"SMTP Use SSL:       {app.config.get('SMTP_USE_SSL')}")

        subject = "GCIR Civic Verification Digest - Test Email"
        html_body = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #1a73e8; margin-top: 0;">GCIR Email Setup Verified!</h2>
            <p>Hello,</p>
            <p>This is a test notification confirming that your <strong>GCIR Civic Issue Reporter</strong> email dispatch system and SMTP credentials are correctly configured and operational.</p>
            <div style="background: #f8f9fa; border-left: 4px solid #1a73e8; padding: 12px; margin: 16px 0; border-radius: 4px;">
                <strong>System Information:</strong><br/>
                <span>Email Backend: <code>SMTP</code></span><br/>
                <span>Delivery: <code>Operational</code></span>
            </div>
            <p style="font-size: 0.85em; color: #777;">
                Sent automatically by the GCIR Test Utility.
            </p>
        </div>
        """
        text_body = "GCIR Email Setup Verified!\n\nThis is a test notification confirming your email dispatch system is operational."

        print("-" * 60)
        print("Attempting to dispatch test email...")
        success = send_email(to_email=recipient, subject=subject, html_body=html_body, text_body=text_body)

        if success:
            print("[OK] Test email dispatched successfully!")
            print(f"Check the inbox for '{recipient}'.")
        else:
            print("[ERROR] Email dispatch failed. Please check your credentials or logs above.")
            sys.exit(1)

        print("=" * 60)


if __name__ == "__main__":
    main()
