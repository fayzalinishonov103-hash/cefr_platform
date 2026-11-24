"""Send one test e-mail with the SMTP settings from .env, so you know password-reset e-mails will really arrive.

Usage:   python tools/check_smtp.py you@example.com
"""
import os
import smtplib
import sys
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def main():
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("Ishlatish: python tools/check_smtp.py sizning@emailingiz.uz")
    host, port = os.environ.get("SMTP_HOST", ""), int(os.environ.get("SMTP_PORT", "587"))
    user, password = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", "Levi <no-reply@example.com>")
    if not host:
        sys.exit(".env da SMTP_HOST boʻsh. Email provayderingiz maʼlumotlarini kiriting (README: Server).")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Levi: SMTP sinov xati", sender, sys.argv[1]
    msg.set_content("Agar bu xatni oʻqiyotgan boʻlsangiz, Levi saytining email sozlamalari toʻgʻri ishlayapti.")
    try:
        cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP          # same rule as the app: 465 = SSL, otherwise STARTTLS
        with cls(host, port, timeout=20) as smtp:
            if port != 465:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        sys.exit("Kirish rad etildi: SMTP_USER / SMTP_PASSWORD notoʻgʻri (Gmail va boshqalarda 'ilova paroli' kerak boʻlishi mumkin).")
    except Exception as exc:
        sys.exit(f"Xat yuborilmadi: {exc!r}\nSMTP_HOST ({host}), SMTP_PORT ({port}) va tarmoq (firewall) ni tekshiring. 587 = STARTTLS, 465 = SSL.")
    print(f"Yuborildi: {sys.argv[1]}. Pochtani (va spam papkasini) tekshiring.")


if __name__ == "__main__":
    main()
