from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
import logging

logging.getLogger('apscheduler').setLevel(logging.WARNING)

_scheduler = None


def _sync_replies_job():
    from modules.email_monitor import sync_replies
    try:
        result = sync_replies()
        if result.get('new_replies', 0) > 0:
            print(f"[Scheduler] Synced {result['new_replies']} new replies")
    except Exception as e:
        print(f"[Scheduler] Reply sync error: {e}")


def _send_scheduled_emails_job():
    from database import get_db
    from modules.email_sender import send_scheduled_email
    from datetime import datetime

    now = datetime.utcnow().isoformat()
    conn = get_db()
    pending = conn.execute('''
        SELECT id FROM scheduled_emails
        WHERE status = 'pending' AND scheduled_at <= ?
    ''', (now,)).fetchall()
    conn.close()

    for row in pending:
        try:
            send_scheduled_email(row['id'])
        except Exception as e:
            print(f"[Scheduler] Failed to send scheduled email {row['id']}: {e}")


def init_scheduler(app):
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)

    # sync replies every 15 minutes
    _scheduler.add_job(
        _sync_replies_job,
        IntervalTrigger(minutes=15),
        id='sync_replies',
        replace_existing=True,
    )

    # check scheduled emails every 5 minutes
    _scheduler.add_job(
        _send_scheduled_emails_job,
        IntervalTrigger(minutes=5),
        id='send_scheduled',
        replace_existing=True,
    )

    _scheduler.start()
    return _scheduler


def schedule_one_off_email(scheduled_id, run_at_iso):
    if _scheduler is None:
        return
    from modules.email_sender import send_scheduled_email
    _scheduler.add_job(
        send_scheduled_email,
        DateTrigger(run_date=datetime.fromisoformat(run_at_iso)),
        args=[scheduled_id],
        id=f'scheduled_email_{scheduled_id}',
        replace_existing=True,
    )


def get_scheduler():
    return _scheduler
