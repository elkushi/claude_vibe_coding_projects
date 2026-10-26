"""Create a Gmail draft (default) or send a rendered issue.

Usage:
    python tools/gmail_send.py .tmp/<slug> [--to a@x.com,b@y.com] [--send]

Two ways to authenticate (the first one found is used):
  1. App password (simplest): GMAIL_ADDRESS + GMAIL_APP_PASSWORD in .env.
     Drafts go in over IMAP, sending goes out over SMTP. Needs 2-Step Verification
     on the account; create the password at https://myaccount.google.com/apppasswords
  2. OAuth: credentials.json ("Desktop app" client) in the project root. The first
     run opens a browser consent screen and saves token.json.
A plain Google API key (AIza...) can't be used: Gmail needs user consent.
Images from images.json are embedded as inline CID attachments so they
render in Gmail without any hosting. On success, appends to issues_log.json.
"""
import argparse
import base64
import imaplib
import json
import os
import re
import smtplib
import time
from datetime import date
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]  # drafts + send, no inbox read access


def gmail_service():
    token, creds_file = ROOT / "token.json", ROOT / "credentials.json"
    creds = Credentials.from_authorized_user_file(token, SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not creds_file.exists():
            raise SystemExit("No Gmail login found. Add GMAIL_ADDRESS + GMAIL_APP_PASSWORD to .env "
                             "(or credentials.json for OAuth). See 'One-time setup' in workflows/newsletter.md")
        creds = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES).run_local_server(port=0)
    token.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def app_password_login():
    load_dotenv(ROOT / ".env")
    addr, pw = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
    return (addr, pw.replace(" ", "")) if addr and pw else None


def imap_draft(addr, pw, msg):
    """Save to the Drafts folder, found by its \\Drafts flag so non-English Gmail labels work too."""
    with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
        imap.login(addr, pw)
        _, folders = imap.list()
        drafts = next((re.search(rb'"([^"]+)"$', f).group(1).decode() for f in folders if rb"\\Drafts" in f),
                      "[Gmail]/Drafts")
        typ, resp = imap.append(f'"{drafts}"', r"\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK":
            raise SystemExit(f"IMAP append failed: {resp}")


def smtp_send(addr, pw, msg, to):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(addr, pw)
        smtp.send_message(msg, from_addr=addr, to_addrs=to)


def build_message(issue_dir, brand, to, sender="me"):
    content = json.loads((issue_dir / "content.json").read_text())
    images = json.loads((issue_dir / "images.json").read_text())

    msg = MIMEMultipart("related")
    msg["Subject"] = content["subject"]
    msg["From"] = formataddr((brand["from_name"], sender))
    if to:
        msg["To"] = ", ".join(to)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText((issue_dir / "email.txt").read_text(), "plain", "utf-8"))
    alt.attach(MIMEText((issue_dir / "email.html").read_text(), "html", "utf-8"))
    msg.attach(alt)

    for cid, path in images.items():
        img = MIMEImage(Path(path).read_bytes())
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=Path(path).name)
        msg.attach(img)
    return msg, content


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("issue_dir")
    ap.add_argument("--to", help="comma-separated recipients (default: brand.json default_to)")
    ap.add_argument("--send", action="store_true", help="send immediately instead of creating a draft")
    args = ap.parse_args()

    issue_dir = Path(args.issue_dir)
    brand = json.loads((ROOT / "config" / "brand.json").read_text())
    to = [a.strip() for a in (args.to or brand.get("default_to", "")).split(",") if a.strip()]
    if args.send and not to:
        raise SystemExit("--send needs a recipient: pass --to or set default_to in config/brand.json")

    login = app_password_login()
    if login:
        msg, content = build_message(issue_dir, brand, to, sender=login[0])
        if args.send:
            smtp_send(*login, msg, to)
            print(f"sent to {', '.join(to)} via SMTP")
        else:
            imap_draft(*login, msg)
            print("draft saved via IMAP - open Gmail > Drafts to review")
    else:
        msg, content = build_message(issue_dir, brand, to)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        svc = gmail_service()
        if args.send:
            res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            print(f"sent to {', '.join(to)} (message id {res['id']})")
        else:
            res = svc.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            print(f"draft created (id {res['id']}) - open Gmail > Drafts to review")

    log_path = ROOT / "issues_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    log.append({"date": date.today().isoformat(), "slug": issue_dir.name, "topic": content.get("topic"),
                "subject": content["subject"], "action": "sent" if args.send else "draft", "to": to})
    log_path.write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
