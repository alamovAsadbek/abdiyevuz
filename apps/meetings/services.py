import base64
import hashlib
import hmac
import re
import time

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.realtime import _send, push_all, push_user
from apps.notifications.services import notify
from . import access
from .models import MeetingCommentModel, MeetingEventModel, MeetingMemberModel, MeetingModel, MeetingRecordingModel, MeetingSessionModel

MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_.]{3,30})")
DEFAULT_STATE = {"mic": False, "cam": False, "screen": False, "hand": False}


def grp(pk):
    return f"mt{pk}"


def ugrp(pk, uid):
    return f"mt{pk}u{uid}"


def broadcast(meeting_id, payload, skip_uid=None):
    _send(grp(meeting_id), payload)


def to_user(meeting_id, uid, payload):
    _send(ugrp(meeting_id, uid), payload)


def log(meeting, actor, action, target=None, note=""):
    return MeetingEventModel.objects.create(meeting=meeting, actor=actor, target=target, action=action, note=note[:200])


def role_of(meeting, user, member=None):
    if user.pk == meeting.host_id:
        return "host"
    if user.is_main:
        return "cohost"
    m = member or access.member_of(meeting, user)
    return "cohost" if m and m.role == "cohost" else "member"


def ser_user(meeting, m):
    u = m.user
    return {"uid": u.pk, "name": u.full_name or u.username, "username": u.username, "ini": u.initials, "role": role_of(meeting, u, m),
            "online": m.online, "state": {**DEFAULT_STATE, **(m.state or {})}, "caps": access.effective(meeting, u, m),
            "mperms": m.mperms or [], "banned": m.banned}


STALE_SECONDS = 150


def drop_stale(meeting_id):
    """Ping yubormay qo'ygan (server qayta ishga tushgan, brauzer yopilgan) «onlayn» qatnashchilarni chiqaradi."""
    from datetime import timedelta
    from django.db.models import Q
    now = timezone.now()
    qs = MeetingMemberModel.objects.filter(meeting_id=meeting_id, online=True).filter(Q(seen_at__isnull=True) | Q(seen_at__lt=now - timedelta(seconds=STALE_SECONDS)))
    uids = list(qs.values_list("user_id", flat=True))
    if uids:
        qs.update(online=False, left_at=now)
        MeetingSessionModel.objects.filter(meeting_id=meeting_id, user_id__in=uids, left_at__isnull=True).update(left_at=now)
        if not MeetingMemberModel.objects.filter(meeting_id=meeting_id, online=True).exists():
            MeetingModel.objects.filter(pk=meeting_id, status="live", empty_since__isnull=True).update(empty_since=now)
    return uids


def roster(meeting, only_online=False):
    qs = MeetingMemberModel.objects.filter(meeting=meeting, banned=False).select_related("user")
    if only_online:
        qs = qs.filter(online=True)
    return [ser_user(meeting, m) for m in qs]


def mentionables(meeting):
    """@ belgisi bilan belgilash mumkin bo'lganlar: egasi + barcha a'zolar (banlanmagan)."""
    out = {meeting.host.username: meeting.host.full_name or meeting.host.username}
    for m in MeetingMemberModel.objects.filter(meeting=meeting, banned=False).select_related("user"):
        out[m.user.username] = m.user.full_name or m.user.username
    return [{"username": k, "name": v} for k, v in out.items()]


def ser_comment(c):
    return {"id": c.pk, "uid": c.user_id, "name": c.user.full_name or c.user.username, "ini": c.user.initials, "username": c.user.username,
            "text": "" if c.is_deleted else c.text, "deleted": c.is_deleted, "at": timezone.localtime(c.created).strftime("%H:%M"),
            "mentions": [] if c.is_deleted else list(c.mentions.values_list("username", flat=True))}


def recent_comments(meeting, n=100):
    qs = list(MeetingCommentModel.objects.filter(meeting=meeting).select_related("user").prefetch_related("mentions").order_by("-id")[:n])
    return [ser_comment(c) for c in reversed(qs)]


def add_comment(meeting, user, text):
    text = (text or "").strip()[:1000]
    if not text:
        return None
    c = MeetingCommentModel.objects.create(meeting=meeting, user=user, text=text)
    names = {x.lower() for x in MENTION_RE.findall(text)}
    if names:
        U = get_user_model()
        ids = set(MeetingMemberModel.objects.filter(meeting=meeting, banned=False).values_list("user_id", flat=True)) | {meeting.host_id}
        found = list(U.objects.filter(pk__in=ids, is_active=True).exclude(pk=user.pk))
        found = [u for u in found if u.username.lower() in names]
        if found:
            c.mentions.set(found)
            notify(found, f"{user.full_name} sizni “{meeting.title}” meetingida belgiladi: {text[:80]}", f"/meetings/{meeting.pk}/room/")
    return c


def delete_comment(meeting, actor, cid):
    c = MeetingCommentModel.objects.filter(pk=cid, meeting=meeting, is_deleted=False).select_related("user").first()
    if not c:
        return None
    if c.user_id != actor.pk and not access.can_perm(meeting, actor, "comments"):
        return None
    if c.user_id != actor.pk and c.user.pk == meeting.host_id and actor.pk != meeting.host_id and not actor.is_main:
        return None  # egasining izohini yordamchi o'chira olmaydi
    c.is_deleted, c.deleted_by = True, actor
    c.save(update_fields=["is_deleted", "deleted_by"])
    if c.user_id != actor.pk:
        log(meeting, actor, "comment_delete", c.user, c.text[:80])
    return c


def start_meeting(meeting, actor=None):
    if meeting.status == MeetingModel.SCHEDULED:
        MeetingModel.objects.filter(pk=meeting.pk).update(status="live", started_at=timezone.now(), empty_since=timezone.now())
        meeting.status = "live"
        ids = list(MeetingMemberModel.objects.filter(meeting=meeting, banned=False, invited=True).exclude(user_id=meeting.host_id).values_list("user_id", flat=True))
        if ids:
            notify(ids, f"“{meeting.title}” meeting boshlandi — qo‘shiling", f"/meetings/{meeting.pk}/room/")
        push_all({"type": "meeting", "id": meeting.pk, "status": "live"})
        log(meeting, actor, "start")
        return True
    return False


def end_meeting(meeting, actor=None, auto=False):
    if meeting.status == MeetingModel.ENDED:
        return False
    MeetingModel.objects.filter(pk=meeting.pk).update(status="ended", ended_at=timezone.now())
    now = timezone.now()
    MeetingMemberModel.objects.filter(meeting=meeting).update(online=False, left_at=now)
    MeetingSessionModel.objects.filter(meeting=meeting, left_at__isnull=True).update(left_at=now)
    for r in MeetingRecordingModel.objects.filter(meeting=meeting, active=True):
        rec_finish(r, actor)
    meeting.status = "ended"
    log(meeting, actor, "auto_end" if auto else "end")
    broadcast(meeting.pk, {"type": "ended", "auto": auto})
    push_all({"type": "meeting", "id": meeting.pk, "status": "ended"})
    return True


def invite(meeting, actor, users):
    n = 0
    for u in users:
        m, created = MeetingMemberModel.objects.get_or_create(meeting=meeting, user=u, defaults={"invited": True})
        if m.banned:
            continue
        if created or not m.invited:
            m.invited = True
            m.save(update_fields=["invited"])
            n += 1
            when = f" ({timezone.localtime(meeting.start_at):%d.%m.%Y %H:%M})" if meeting.start_at else ""
            notify([u], f"Sizni “{meeting.title}” meetingiga taklif qilishdi{when}", f"/meetings/{meeting.pk}/")
    if n:
        log(meeting, actor, "invite", note=f"{n} ta")
    return n


def ice_servers(user):
    """Brauzerga beriladigan STUN/TURN serverlar. TURN uchun coturn REST (vaqtinchalik parol) yoki doimiy login."""
    from django.conf import settings
    out = list(settings.MEETING_ICE_SERVERS)
    urls = settings.MEETING_TURN_URLS
    if urls and settings.MEETING_TURN_SECRET:
        name = f"{int(time.time()) + 12 * 3600}:{user.pk}"
        pwd = base64.b64encode(hmac.new(settings.MEETING_TURN_SECRET.encode(), name.encode(), hashlib.sha1).digest()).decode()
        out.append({"urls": urls, "username": name, "credential": pwd})
    elif urls and settings.MEETING_TURN_USER:
        out.append({"urls": urls, "username": settings.MEETING_TURN_USER, "credential": settings.MEETING_TURN_PASSWORD})
    return out


def has_turn():
    from django.conf import settings
    return bool(settings.MEETING_TURN_URLS and (settings.MEETING_TURN_SECRET or settings.MEETING_TURN_USER))


# ---------------------------------------------------------------- yozib olish
def rec_dir():
    from django.conf import settings
    d = settings.PRIVATE_ROOT / "meeting_rec"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rec_start(meeting, user):
    if MeetingRecordingModel.objects.filter(meeting=meeting, active=True).exists():
        return None
    r = MeetingRecordingModel.objects.create(meeting=meeting, started_by=user)
    r.path = f"m{meeting.pk}_{r.pk}.webm"
    r.save(update_fields=["path"])
    (rec_dir() / r.path).touch()
    log(meeting, user, "rec_start")
    broadcast(meeting.pk, {"type": "recording", "on": True, "by": user.pk})
    return r


def rec_finish(r, actor=None):
    if not r.active:
        return
    r.active, r.ended_at = False, timezone.now()
    f = rec_dir() / r.path
    r.size = f.stat().st_size if f.exists() else 0
    r.save(update_fields=["active", "ended_at", "size"])
    log(r.meeting, actor, "rec_stop", note=f"{r.size // 1024} KB")
    broadcast(r.meeting_id, {"type": "recording", "on": False})
