"""One place that sends e-mail (SMTP). Without SMTP_HOST it only logs (development)."""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def send_mail(to, subject, body):
    """Returns True when the message was handed to the SMTP server, False when SMTP is not configured."""
    host = current_app.config.get("SMTP_HOST")
    if not host:
        if current_app.debug or current_app.testing:          # the text may hold a code or a link: never log it in production
            log.warning("SMTP sozlanmagan. %s ga xat (%s):\n%s", to, subject, body)
        else:
            log.error("SMTP sozlanmagan: xat yuborilmadi (%s).", to)
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, current_app.config["SMTP_FROM"], to
    msg.set_content(body)
    port = current_app.config["SMTP_PORT"]
    smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP       # 465 = SSL from the start, 587 = STARTTLS
    with smtp_class(host, port, timeout=15) as smtp:
        if port != 465:
            smtp.starttls()
        if current_app.config.get("SMTP_USER"):
            smtp.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
        smtp.send_message(msg)
    return True
