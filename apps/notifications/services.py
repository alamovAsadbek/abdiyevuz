import logging

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import UserModel
from apps.core.realtime import push_user
from .models import MessageDeliveryModel, MessageModel, NotificationModel

log = logging.getLogger(__name__)


def unread_count(user):
    return (NotificationModel.objects.filter(user=user, is_read=False).count()
            + MessageDeliveryModel.objects.filter(user=user, channel="app", ok=True, is_read=False).count())


def notify(users, text, link=""):
    ids = [u.pk if hasattr(u, "pk") else u for u in users]
    NotificationModel.objects.bulk_create([NotificationModel(user_id=i, text=text[:300], link=link) for i in ids])
    for i in set(ids):
        push_user(i, {"type": "notify", "text": text, "link": link, "unread": unread_count_id(i)})


def unread_count_id(uid):
    return (NotificationModel.objects.filter(user_id=uid, is_read=False).count()
            + MessageDeliveryModel.objects.filter(user_id=uid, channel="app", ok=True, is_read=False).count())


def notify_staff(perm, text, link=""):
    ids = [u.pk for u in UserModel.objects.filter(role__in=["main", "assistant"], is_active=True) if u.can_view(perm)]
    if ids:
        notify(ids, text, link)


def send_sms(phone, text):
    """SMS provayder ulanmaguncha 'console' rejim. O'zingizning provayderingizni shu yerga ulang."""
    if settings.SMS_BACKEND == "console":
        log.info("SMS -> %s: %s", phone, text[:60])
        return True
    raise NotImplementedError("SMS provayderini apps/notifications/services.py::send_sms da ulang")


def recipients(audience, author, groups=(), users=()):
    from apps.courses.services import my_groups
    from apps.accounts.models import GroupModel
    base = UserModel.objects.exclude(pk=author.pk).filter(is_active=True)
    st = base.filter(role="student")
    if audience == "all": return base
    if audience == "students": return st
    if audience == "staff": return base.exclude(role="student")
    if audience == "nobuy": return st.filter(accesses__isnull=True)
    if audience == "buyers": return st.filter(accesses__isnull=False).distinct()
    if audience == "inactive":
        from datetime import timedelta
        lim = timezone.now() - timedelta(days=7)
        return st.filter(last_seen__lt=lim) | st.filter(last_seen__isnull=True)
    if audience == "online":
        from datetime import timedelta
        return base.filter(last_seen__gte=timezone.now() - timedelta(minutes=5))
    if audience == "group":
        allowed = my_groups(author).filter(pk__in=[g.pk for g in groups])
        return st.filter(member_groups__in=allowed).distinct()
    if audience == "users":
        ids = [u.pk for u in users]
        qs = base.filter(pk__in=ids)
        if author.is_assistant:
            qs = qs.filter(role="student", member_groups__assistants=author).distinct()
        return qs
    return st.filter(member_groups__in=my_groups(author)).distinct()  # mygroups


def deliver(msg, users):
    rows = []
    for u in users:
        for ch in msg.channels:
            if u.is_blocked:
                rows.append(MessageDeliveryModel(message=msg, user=u, channel=ch, ok=False, reason="Hisob bloklangan"))
            elif ch == "sms" and not u.phone:
                rows.append(MessageDeliveryModel(message=msg, user=u, channel=ch, ok=False, reason="Telefon raqami kiritilmagan"))
            else:
                ok, why = True, ""
                if ch == "sms":
                    try:
                        send_sms(u.phone, msg.title + ": " + msg.short)
                    except Exception as e:  # noqa
                        ok, why = False, str(e)[:100]
                rows.append(MessageDeliveryModel(message=msg, user=u, channel=ch, ok=ok, reason=why))
    MessageDeliveryModel.objects.bulk_create(rows)
    for u in {r.user_id for r in rows if r.channel == "app" and r.ok}:
        push_user(u, {"type": "message", "text": msg.title, "link": "/notifications/", "unread": unread_count_id(u),
                      "important": msg.important})


def retry_failed(msg):
    fixed = 0
    for d in msg.deliveries.filter(ok=False).select_related("user"):
        if d.user.is_blocked or (d.channel == "sms" and not d.user.phone):
            continue
        d.ok, d.reason = True, ""
        d.save(update_fields=["ok", "reason"])
        fixed += 1
    return fixed
