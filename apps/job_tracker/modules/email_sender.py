import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import os
from database import get_db, get_setting

TRK_PREFIX = "TRK"


def _build_tracking_tag(app_uuid):
    return f"[{TRK_PREFIX}-{app_uuid}]"


def _inject_uuid_in_body(body_html, body_plain, app_uuid):
    tag = _build_tracking_tag(app_uuid)
    hidden_tag = f'<div style="display:none;color:transparent;font-size:0">{tag}</div>'
    if body_html:
        body_html = body_html + hidden_tag
    if body_plain:
        body_plain = body_plain + f"\n\n{tag}"
    return body_html, body_plain


def send_tracked_email(application_id, subject, body_plain, body_html=None, attachments=None):
    smtp_host  = get_setting('smtp_host', '')
    smtp_port  = int(get_setting('smtp_port', 587))
    smtp_user  = get_setting('smtp_user', '')
    smtp_pass  = get_setting('smtp_pass', '')
    from_name  = get_setting('from_name', '')
    use_tls    = get_setting('smtp_tls', 'true').lower() == 'true'

    if not smtp_host or not smtp_user or not smtp_pass:
        raise ValueError("SMTP settings are not configured. Go to Settings.")

    conn = get_db()
    app = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    if not app:
        conn.close()
        raise ValueError(f"Application {application_id} not found")

    app_uuid = app['uuid']
    to_email = app['contact_email']
    if not to_email:
        conn.close()
        raise ValueError("Application has no contact email")

    # inject tracking tag
    tag = _build_tracking_tag(app_uuid)
    tracked_subject = f"{subject} {tag}"
    body_html_tracked, body_plain_tracked = _inject_uuid_in_body(body_html, body_plain, app_uuid)

    # build MIME message
    msg = MIMEMultipart('alternative' if body_html else 'mixed')
    msg['Subject'] = tracked_subject
    msg['From'] = f"{from_name} <{smtp_user}>" if from_name else smtp_user
    msg['To'] = to_email

    msg.attach(MIMEText(body_plain_tracked, 'plain'))
    if body_html_tracked:
        msg.attach(MIMEText(body_html_tracked, 'html'))

    for path in (attachments or []):
        if os.path.exists(path):
            with open(path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(path)}"')
            msg.attach(part)

    context = ssl.create_default_context()
    if use_tls:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
    else:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())

    now = datetime.utcnow().isoformat()
    conn.execute('''
        UPDATE applications
        SET status = 'sent', sent_at = ?, email_subject = ?, email_body = ?
        WHERE id = ?
    ''', (now, subject, body_plain, application_id))
    conn.commit()
    conn.close()

    return {"success": True, "tracked_subject": tracked_subject, "uuid": app_uuid}
