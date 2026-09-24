import os
import smtplib
from email.message import EmailMessage


def send_otp_email(recipient: str, code: str, purpose: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("SMTP_FROM")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    if password:
        password = password.replace(" ", "")
    use_ssl = os.getenv("SMTP_USE_SSL", str(port == 465)).lower() == "true"
    if not host or not sender:
        if os.getenv("DEV_RETURN_OTP", "false").lower() == "true":
            return
        raise RuntimeError("OTP email is not configured. Set SMTP_HOST and SMTP_FROM in backend/.env, then restart the backend.")
    message = EmailMessage()
    message["Subject"] = "Your PantryOS verification code"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(f"Your PantryOS {purpose} verification code is {code}. It expires in 10 minutes.")
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with smtp_class(host, port, timeout=15) as server:
            if not use_ssl:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as error:
        raise RuntimeError("Gmail rejected SMTP login. Enable 2-Step Verification and use a 16-character Google App Password in SMTP_PASSWORD.") from error
    except smtplib.SMTPException as error:
        raise RuntimeError(f"OTP email could not be sent through {host}:{port}. Check SMTP username, app password, and SSL settings.") from error
    except OSError as error:
        raise RuntimeError(f"OTP email server {host}:{port} is unreachable. Check SMTP host, port, and firewall settings.") from error