"""Fon jarayoni: test va vazifa statuslarini backend o'zi o'zgartiradi.
 - test: kutilmoqda -> aktiv -> tugagan (vaqt kelganda)
 - vazifa: muddat tugasa yuklash avtomatik yopiladi (keyingi darslar ochiq qoladi)
Ko'p jarayonli productionda `python manage.py run_scheduler` ni alohida ishga tushiring (RUN_SCHEDULER=0)."""
import logging
import threading
import time

from django.conf import settings
from django.utils import timezone

from .realtime import push_all, push_users

log = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def start():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=loop, daemon=True, name="km-scheduler").start()
    log.info("Scheduler ishga tushdi")


def loop():
    time.sleep(3)
    n = 0
    while True:
        try:
            tick(n % 180 == 0)
        except Exception:
            log.exception("scheduler tick xatosi")
        n += 1
        time.sleep(settings.SCHEDULER_INTERVAL)


def _meetings(now):
    """Bo'sh qolgan jonli meetinglarni yakunlaydi; boshlanish vaqti yaqinlashganda eslatadi."""
    from datetime import timedelta
    from apps.meetings.models import MeetingMemberModel, MeetingModel
    from apps.meetings import services as MS
    from apps.notifications.services import notify
    lim = now - timedelta(minutes=settings.MEETING_EMPTY_END_MINUTES)
    for m in MeetingModel.objects.filter(status="live", empty_since__isnull=False, empty_since__lte=lim):
        MS.end_meeting(m, None, auto=True)
    from apps.accounts.models import UserModel
    from apps.meetings.models import MeetingRecordingModel
    hour = timedelta(minutes=settings.MEETING_LONG_MINUTES)
    for m in MeetingModel.objects.filter(status="live", started_at__isnull=False, started_at__lte=now - hour).select_related("host"):
        if m.long_notice_at and now - m.long_notice_at < hour:
            continue
        MeetingModel.objects.filter(pk=m.pk).update(long_notice_at=now)
        mins = int((now - m.started_at).total_seconds() // 60)
        ids = {m.host_id} | set(UserModel.objects.filter(role="main", is_active=True).values_list("pk", flat=True))
        notify(list(ids), f"Sizda davom etayotgan meeting bor: “{m.title}” ({mins // 60} soat {mins % 60} daqiqadan beri)", f"/meetings/{m.pk}/")
    for r in MeetingRecordingModel.objects.filter(active=True):   # yozuvchi uzilib qolgan bo'lsa yopamiz
        f = MS.rec_dir() / r.path
        if (not f.exists()) or now.timestamp() - f.stat().st_mtime > 120:
            MS.rec_finish(r, None)
    for m in MeetingModel.objects.filter(status="scheduled", reminded=False, start_at__isnull=False, start_at__lte=now + timedelta(minutes=10)):
        MeetingModel.objects.filter(pk=m.pk).update(reminded=True)
        ids = list(MeetingMemberModel.objects.filter(meeting=m, banned=False, invited=True).values_list("user_id", flat=True))
        if ids:
            notify(ids, f"“{m.title}” meeting tez orada boshlanadi", f"/meetings/{m.pk}/")
        push_all({"type": "meeting", "id": m.pk, "status": "soon"})


def tick(cleanup=False):
    from apps.courses.models import TaskModel
    from apps.courses.services import enrolled
    from apps.exams.models import TestModel
    from apps.notifications.services import notify
    now = timezone.now()
    for t in TestModel.objects.all():
        new = t.compute_status(now)
        if new != t.status:
            TestModel.objects.filter(pk=t.pk).update(status=new)
            push_all({"type": "test_status", "id": t.pk, "status": new, "title": t.title})
            if new == TestModel.ACTIVE:
                log.info("Test boshlandi: %s", t.title)
    for k in TaskModel.objects.filter(is_closed=False, deadline__isnull=False, deadline__lte=now).select_related("lesson__module__course"):
        TaskModel.objects.filter(pk=k.pk).update(is_closed=True)
        ids = [u.pk for u in enrolled(k.lesson, None) if not k.submissions.filter(student=u).exists()]
        if ids:
            notify(ids, f"“{k.title}” vazifasi muddati tugadi — yuklash yopildi", f"/lessons/{k.lesson_id}/?tab=task")
        push_all({"type": "task_closed", "id": k.pk, "lesson": k.lesson_id, "title": k.title})
    TaskModel.objects.filter(is_closed=True).exclude(deadline__lte=now).exclude(deadline__isnull=True).update(is_closed=False)
    TaskModel.objects.filter(is_closed=True, deadline__isnull=True).update(is_closed=False)
    _meetings(now)
    if cleanup:
        from apps.accounts.models import RefreshTokenModel
        RefreshTokenModel.objects.filter(expires_at__lt=now).delete()
