"""
Email service for password reset. Uses real SMTP (smtplib, stdlib — no
extra dependency) when SMTP_HOST/SMTP_USER/SMTP_PASSWORD are configured.

If email is not configured, send_reset_email() returns False and the caller
(app.py) falls back to the previous dev-mode behavior of returning the reset
token directly in the API response — so nothing that worked before breaks
when SMTP isn't set up.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import config

logger = logging.getLogger("scholarai.email")


def send_reset_email(to_email, full_name, reset_token):
    """
    Attempts to send a real password-reset email.
    Returns True on success, False if email isn't configured or sending failed
    (the caller should fall back to dev-mode token display in the latter case,
    but only when not configured — a configured-but-failing send is logged and
    surfaced, not silently swallowed).
    """
    if not config.EMAIL_CONFIGURED:
        logger.info("SMTP not configured — skipping real email send, using dev-mode token fallback.")
        return False, "not_configured"

    reset_link = f"{config.APP_BASE_URL}/#/reset-password?token={reset_token}"
    subject = "Reset your ScholarAI password"
    body_text = (
        f"Hi {full_name},\n\n"
        f"We received a request to reset your ScholarAI password.\n"
        f"Reset link (valid for 1 hour): {reset_link}\n\n"
        f"Or enter this token manually on the reset page: {reset_token}\n\n"
        f"If you did not request this, you can safely ignore this email.\n"
    )
    body_html = f"""
    <p>Hi {full_name},</p>
    <p>We received a request to reset your ScholarAI password.</p>
    <p><a href="{reset_link}">Click here to reset your password</a> (valid for 1 hour).</p>
    <p>Or enter this token manually on the reset page: <code>{reset_token}</code></p>
    <p>If you did not request this, you can safely ignore this email.</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if config.SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_FROM, [to_email], msg.as_string())
        logger.info(f"Password reset email sent to {to_email}")
        return True, None
    except Exception as e:
        logger.error(f"Failed to send reset email to {to_email}: {e}")
        return False, str(e)
