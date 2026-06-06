"""Email delivery for password recovery.

Supports two providers, both using only the standard library (no extra deps):
  - Resend HTTP API   (set RESEND_API_KEY + EMAIL_FROM)
  - SMTP              (set SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / EMAIL_FROM)

If neither is configured, ``send_reset_email`` returns False and the caller
falls back to returning the token directly (demo mode).
"""
from __future__ import annotations

import json
import smtplib
import urllib.request
from email.mime.text import MIMEText

from .config import settings


def _html(reset_link: str, token: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0a0a12;color:#f5f5f7;padding:32px;border-radius:16px;max-width:480px;margin:auto">
  <h2 style="margin:0 0 8px">🎰 MelateAI Pro</h2>
  <p style="color:#b9b9c6">Recibimos una solicitud para restablecer tu contraseña.</p>
  <p style="margin:24px 0">
    <a href="{reset_link}" style="background:linear-gradient(90deg,#7C3AED,#06B6D4);color:#fff;text-decoration:none;padding:12px 22px;border-radius:12px;font-weight:600">Restablecer contraseña</a>
  </p>
  <p style="color:#8a8a98;font-size:13px">O usa este token: <code style="color:#a5b4fc">{token}</code></p>
  <p style="color:#6a6a78;font-size:12px">El enlace expira en 30 minutos. Si no fuiste tú, ignora este correo.</p>
</div>"""


def _send_resend(to_email: str, subject: str, html: str) -> bool:
    payload = json.dumps({
        "from": settings.email_from,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
            # Cloudflare (in front of Resend) blocks the default urllib UA
            # ("Python-urllib") with error 1010 — use an explicit User-Agent.
            "User-Agent": "MelateAI-Pro/1.0 (+https://melate-ia.vercel.app)",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return 200 <= resp.status < 300


def _send_smtp(to_email: str, subject: str, html: str) -> bool:
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.email_from, [to_email], msg.as_string())
    return True


def send_reset_email(to_email: str, token: str) -> bool:
    """Send a password-reset email. Returns True if delivered."""
    reset_link = f"{settings.app_url.rstrip('/')}/reset?token={token}"
    subject = "Restablece tu contraseña · MelateAI Pro"
    html = _html(reset_link, token)
    try:
        if settings.resend_api_key:
            return _send_resend(to_email, subject, html)
        if settings.smtp_host:
            return _send_smtp(to_email, subject, html)
    except Exception:
        return False
    return False


def email_configured() -> bool:
    return bool(settings.resend_api_key or settings.smtp_host)
