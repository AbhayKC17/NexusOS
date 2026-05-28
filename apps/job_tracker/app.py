import os
import uuid
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify
)
from werkzeug.utils import secure_filename

from database import init_db, get_db, get_setting, set_setting
from modules.excel_processor import process_excel
from modules.email_sender import send_tracked_email
from modules.email_monitor import sync_replies
from modules.llm_summarizer import reload_llm
from modules.scheduler import init_scheduler, schedule_one_off_email
from modules.apple_mail_sender import (
    run_bulk_campaign, send_via_apple_mail,
    generate_personalized_intro, build_email_body, transform_to_careers,
)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

ALLOWED_EXT = {'.xlsx', '.xls', '.csv'}

init_db()
scheduler = init_scheduler(app)


# ─── helpers ──────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXT


def page_range(total, per_page, current):
    pages = (total + per_page - 1) // per_page
    return range(1, pages + 1), pages


# ─── dashboard ────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    conn = get_db()
    stats = {
        'total':     conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
        'pending':   conn.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0],
        'sent':      conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('sent','replied')").fetchone()[0],
        'replied':   conn.execute("SELECT COUNT(*) FROM applications WHERE status='replied'").fetchone()[0],
        'scheduled': conn.execute("SELECT COUNT(*) FROM scheduled_emails WHERE status='pending'").fetchone()[0],
    }
    stats['reply_rate'] = round(stats['replied'] / stats['sent'] * 100, 1) if stats['sent'] else 0

    recent = conn.execute('''
        SELECT a.id, a.company, a.position, a.contact_email, a.status,
               a.sent_at, a.created_at,
               r.summary, r.received_at AS reply_date
        FROM applications a
        LEFT JOIN replies r ON a.id = r.application_id
        ORDER BY a.created_at DESC LIMIT 12
    ''').fetchall()

    recent_replies = conn.execute('''
        SELECT r.summary, r.received_at, r.from_email,
               a.company, a.position
        FROM replies r
        JOIN applications a ON r.application_id = a.id
        ORDER BY r.received_at DESC LIMIT 5
    ''').fetchall()

    conn.close()
    return render_template('dashboard.html', stats=stats, recent=recent, recent_replies=recent_replies)


# ─── applications ─────────────────────────────────────────────────────────────

@app.route('/applications')
def applications():
    search  = request.args.get('q', '')
    status  = request.args.get('status', '')
    page    = max(1, int(request.args.get('page', 1)))
    per_page = 20

    conn = get_db()
    base_where = "WHERE 1=1"
    params = []
    if search:
        base_where += " AND (company LIKE ? OR position LIKE ? OR contact_email LIKE ?)"
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if status:
        base_where += " AND status = ?"
        params.append(status)

    total = conn.execute(f"SELECT COUNT(*) FROM applications {base_where}", params).fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(f'''
        SELECT a.*, r.received_at AS reply_date, r.summary
        FROM applications a
        LEFT JOIN replies r ON a.id = r.application_id
        {base_where}
        ORDER BY a.created_at DESC
        LIMIT {per_page} OFFSET {offset}
    ''', params).fetchall()
    conn.close()

    pages, total_pages = page_range(total, per_page, page)
    return render_template('applications.html',
        apps=rows, total=total, page=page, pages=pages,
        total_pages=total_pages, search=search, status_filter=status,
        per_page=per_page)


@app.route('/application/<int:app_id>')
def application_detail(app_id):
    conn = get_db()
    appl = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not appl:
        flash('Application not found', 'danger')
        return redirect(url_for('applications'))
    replies_list = conn.execute(
        "SELECT * FROM replies WHERE application_id = ? ORDER BY received_at DESC", (app_id,)
    ).fetchall()
    scheduled = conn.execute(
        "SELECT * FROM scheduled_emails WHERE application_id = ? ORDER BY scheduled_at", (app_id,)
    ).fetchall()
    conn.close()
    return render_template('application_detail.html', app=appl, replies=replies_list, scheduled=scheduled)


@app.route('/application/new', methods=['GET', 'POST'])
def new_application():
    if request.method == 'POST':
        conn = get_db()
        new_uuid = str(uuid.uuid4())
        conn.execute('''
            INSERT INTO applications
                (uuid, company, position, contact_email, contact_name, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            new_uuid,
            request.form.get('company'),
            request.form.get('position'),
            request.form.get('contact_email'),
            request.form.get('contact_name'),
            request.form.get('notes'),
        ))
        conn.commit()
        app_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        flash('Application created successfully', 'success')
        return redirect(url_for('application_detail', app_id=app_id))
    return render_template('new_application.html')


@app.route('/application/<int:app_id>/edit', methods=['GET', 'POST'])
def edit_application(app_id):
    conn = get_db()
    appl = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not appl:
        conn.close()
        flash('Application not found', 'danger')
        return redirect(url_for('applications'))

    if request.method == 'POST':
        conn.execute('''
            UPDATE applications
            SET company=?, position=?, contact_email=?, contact_name=?, notes=?, status=?
            WHERE id=?
        ''', (
            request.form.get('company'),
            request.form.get('position'),
            request.form.get('contact_email'),
            request.form.get('contact_name'),
            request.form.get('notes'),
            request.form.get('status'),
            app_id,
        ))
        conn.commit()
        conn.close()
        flash('Application updated', 'success')
        return redirect(url_for('application_detail', app_id=app_id))

    conn.close()
    return render_template('edit_application.html', app=appl)


@app.route('/application/<int:app_id>/delete', methods=['POST'])
def delete_application(app_id):
    conn = get_db()
    conn.execute("DELETE FROM replies WHERE application_id = ?", (app_id,))
    conn.execute("DELETE FROM scheduled_emails WHERE application_id = ?", (app_id,))
    conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    flash('Application deleted', 'warning')
    return redirect(url_for('applications'))


# ─── compose & send ───────────────────────────────────────────────────────────

@app.route('/application/<int:app_id>/compose', methods=['GET', 'POST'])
def compose(app_id):
    conn = get_db()
    appl = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    templates = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
    conn.close()

    if not appl:
        flash('Application not found', 'danger')
        return redirect(url_for('applications'))

    if request.method == 'POST':
        action  = request.form.get('action', 'send')
        subject = request.form.get('subject', '')
        body    = request.form.get('body', '')

        if action == 'schedule':
            scheduled_at = request.form.get('scheduled_at', '')
            if not scheduled_at:
                flash('Please pick a date/time for scheduling', 'danger')
                return render_template('compose.html', app=appl, templates=templates)
            conn = get_db()
            conn.execute('''
                INSERT INTO scheduled_emails (application_id, scheduled_at, email_subject, email_body)
                VALUES (?, ?, ?, ?)
            ''', (app_id, scheduled_at, subject, body))
            conn.commit()
            sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            schedule_one_off_email(sid, scheduled_at)
            flash(f'Email scheduled for {scheduled_at} UTC', 'success')
            return redirect(url_for('application_detail', app_id=app_id))

        # send now
        try:
            result = send_tracked_email(app_id, subject, body)
            flash(f'Email sent! Tracking ID: {result["uuid"]}', 'success')
            return redirect(url_for('application_detail', app_id=app_id))
        except Exception as e:
            flash(f'Send failed: {e}', 'danger')

    return render_template('compose.html', app=appl, templates=templates)


# ─── upload ───────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            flash('Please upload an .xlsx, .xls or .csv file', 'danger')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            results = process_excel(filepath, filename)
            flash(
                f"Imported {results['imported']} rows | "
                f"Skipped {results['duplicates_skipped']} duplicates | "
                f"Auto-generated {results['new_uuid_generated']} UUIDs",
                'success'
            )
            if results['errors']:
                flash(f"Warnings: {'; '.join(results['errors'][:5])}", 'warning')
        except Exception as e:
            flash(f'Import failed: {e}', 'danger')

        return redirect(url_for('applications'))

    return render_template('upload.html')


# ─── replies ──────────────────────────────────────────────────────────────────

@app.route('/replies')
def replies():
    conn = get_db()
    rows = conn.execute('''
        SELECT r.*, a.company, a.position, a.contact_email
        FROM replies r
        JOIN applications a ON r.application_id = a.id
        ORDER BY r.received_at DESC
    ''').fetchall()
    conn.close()
    return render_template('replies.html', replies=rows)


# ─── settings ─────────────────────────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        keys = [
            'smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'smtp_tls',
            'from_name',
            'imap_host', 'imap_port', 'imap_user', 'imap_pass',
            'llm_model_path', 'llm_context', 'llm_gpu_layers',
            'sender_name', 'sender_role', 'sender_pitch', 'sender_linkedin', 'resume_path',
        ]
        for key in keys:
            val = request.form.get(key, '').strip()
            if val:
                set_setting(key, val)
        reload_llm()
        flash('Settings saved', 'success')
        return redirect(url_for('settings'))

    current = {}
    setting_keys = [
        'smtp_host', 'smtp_port', 'smtp_user', 'smtp_tls',
        'from_name',
        'imap_host', 'imap_port', 'imap_user',
        'llm_model_path', 'llm_context', 'llm_gpu_layers',
        'sender_name', 'sender_role', 'sender_pitch', 'sender_linkedin', 'resume_path',
    ]
    for k in setting_keys:
        current[k] = get_setting(k, '')

    return render_template('settings.html', settings=current)


# ─── templates ────────────────────────────────────────────────────────────────

@app.route('/templates')
def email_templates():
    conn = get_db()
    tmpl_list = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
    conn.close()
    return render_template('templates.html', templates=tmpl_list)


@app.route('/templates/new', methods=['POST'])
def new_template():
    conn = get_db()
    conn.execute("INSERT INTO templates (name, subject, body) VALUES (?, ?, ?)", (
        request.form.get('name'),
        request.form.get('subject'),
        request.form.get('body'),
    ))
    conn.commit()
    conn.close()
    flash('Template saved', 'success')
    return redirect(url_for('email_templates'))


@app.route('/templates/<int:tmpl_id>/delete', methods=['POST'])
def delete_template(tmpl_id):
    conn = get_db()
    conn.execute("DELETE FROM templates WHERE id = ?", (tmpl_id,))
    conn.commit()
    conn.close()
    flash('Template deleted', 'warning')
    return redirect(url_for('email_templates'))


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/sync-replies', methods=['POST'])
def api_sync_replies():
    result = sync_replies()
    return jsonify(result)


@app.route('/api/stats')
def api_stats():
    conn = get_db()
    data = {
        'total':   conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
        'pending': conn.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0],
        'sent':    conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('sent','replied')").fetchone()[0],
        'replied': conn.execute("SELECT COUNT(*) FROM applications WHERE status='replied'").fetchone()[0],
    }
    conn.close()
    return jsonify(data)


@app.route('/api/template/<int:tmpl_id>')
def api_template(tmpl_id):
    conn = get_db()
    tmpl = conn.execute("SELECT * FROM templates WHERE id = ?", (tmpl_id,)).fetchone()
    conn.close()
    if not tmpl:
        return jsonify({}), 404
    return jsonify(dict(tmpl))


# ─── Campaign (Apple Mail bulk sender) ────────────────────────────────────────

@app.route('/campaign', methods=['GET', 'POST'])
def campaign():
    conn = get_db()

    if request.method == 'POST':
        action = request.form.get('action', '')

        # ── Preview intro for a single app ────────────────────────────────────
        if action == 'preview':
            app_id = int(request.form.get('app_id', 0))
            appl = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
            conn.close()
            if not appl:
                return jsonify({'error': 'Not found'}), 404
            intro = generate_personalized_intro(
                company_name=appl['company'] or '',
                short_desc=appl['notes'] or '',
            )
            body = build_email_body(appl['company'] or '', intro)
            careers = transform_to_careers(appl['contact_email'] or '')
            return jsonify({'intro': intro, 'body': body, 'careers_email': careers})

        # ── Run bulk send ─────────────────────────────────────────────────────
        if action == 'send':
            ids_raw = request.form.getlist('app_ids')
            app_ids = [int(i) for i in ids_raw if i.isdigit()]
            dry_run = request.form.get('dry_run') == '1'
            sleep_sec = int(request.form.get('sleep_seconds', 10))
            send_careers = request.form.get('send_to_careers', '1') == '1'
            conn.close()

            if not app_ids:
                flash('No applications selected.', 'warning')
                return redirect(url_for('campaign'))

            results = run_bulk_campaign(
                application_ids=app_ids,
                sleep_seconds=sleep_sec,
                dry_run=dry_run,
                send_to_careers=send_careers,
            )

            msg = (f"{'[DRY RUN] ' if dry_run else ''}Sent: {results['sent']} | "
                   f"Failed: {results['failed']} | Skipped: {results['skipped']}")
            flash(msg, 'success' if results['failed'] == 0 else 'warning')
            for err in results['errors'][:5]:
                flash(err, 'danger')
            return redirect(url_for('campaign'))

        conn.close()
        return redirect(url_for('campaign'))

    # GET — list pending/unsent applications
    apps = conn.execute('''
        SELECT id, company, position, contact_email, status, notes
        FROM applications
        WHERE status IN ('pending', 'sent')
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()

    resume_path = get_setting('resume_path', '')
    sender_name = get_setting('sender_name', '')
    llm_ready = bool(get_setting('llm_model_path', ''))

    return render_template('campaign.html',
        apps=apps,
        resume_path=resume_path,
        sender_name=sender_name,
        llm_ready=llm_ready,
    )


@app.route('/application/<int:app_id>/send-apple-mail', methods=['POST'])
def send_apple_mail_single(app_id):
    conn = get_db()
    appl = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    if not appl:
        flash('Application not found', 'danger')
        return redirect(url_for('applications'))

    results = run_bulk_campaign(
        application_ids=[app_id],
        sleep_seconds=0,
        dry_run=False,
        send_to_careers=request.form.get('send_to_careers', '1') == '1',
    )
    if results['sent']:
        flash(f'Sent via Apple Mail to {appl["contact_email"]}', 'success')
    else:
        err = results['errors'][0] if results['errors'] else 'Unknown error'
        flash(f'Apple Mail send failed: {err}', 'danger')
    return redirect(url_for('application_detail', app_id=app_id))


# ─── Settings (extended with sender profile) ──────────────────────────────────

@app.route('/settings/profile', methods=['POST'])
def save_profile():
    for key in ['sender_name', 'sender_role', 'sender_pitch', 'sender_linkedin', 'resume_path']:
        val = request.form.get(key, '').strip()
        if val:
            set_setting(key, val)
    flash('Sender profile saved', 'success')
    return redirect(url_for('settings'))


if __name__ == '__main__':
    app.run(debug=True, port=5050, use_reloader=False)
