"""Meeting ruxsatlari — faqat backendda hal qilinadi (view ham, WebSocket ham shu funksiyalarni ishlatadi)."""
from django.db.models import Q

from .models import MPERM_CODES, MeetingMemberModel, MeetingModel


def member_of(meeting, user):
    if not user.is_authenticated:
        return None
    return MeetingMemberModel.objects.filter(meeting=meeting, user=user).first()


def is_owner(meeting, user):
    """Egasi yoki asosiy o'qituvchi — to'liq huquq."""
    return user.is_authenticated and (user.pk == meeting.host_id or user.is_main)


def can_perm(meeting, user, code, member=None):
    if is_owner(meeting, user):
        return True
    m = member or member_of(meeting, user)
    return bool(m and m.role == "cohost" and not m.banned and code in (m.mperms or []))


def is_moderator(meeting, user, member=None):
    if is_owner(meeting, user):
        return True
    m = member or member_of(meeting, user)
    return bool(m and m.role == "cohost" and not m.banned)


def can_view(meeting, user):
    """Detail sahifasini ko'rish. Ochiq — login qilgan hamma; yopiq — faqat taklif qilinganlar/boshqaruvchilar."""
    if not user.is_authenticated:
        return False
    if is_owner(meeting, user):
        return True
    m = member_of(meeting, user)
    if meeting.is_public:
        return not (m and m.banned)
    return bool(m and (m.invited or m.role == "cohost") and not m.banned)


def can_join(meeting, user):
    """-> (ok, sabab)"""
    if not user.is_authenticated:
        return False, "Tizimga kiring"
    if meeting.is_ended:
        return False, "Meeting yakunlangan"
    if not can_view(meeting, user):
        m = member_of(meeting, user)
        return False, "Siz bu meetingdan chiqarilgansiz" if m and m.banned else "Bu yopiq meeting — sizga taklif yuborilmagan"
    if not meeting.is_live and not is_moderator(meeting, user):
        return False, "Meeting hali boshlanmagan"
    return True, ""


def effective(meeting, user, member=None):
    """Qatnashchining joriy imkoniyatlari: mic/cam/chat/screen."""
    if is_moderator(meeting, user):
        return {"mic": True, "cam": True, "chat": True, "screen": True}
    m = member or member_of(meeting, user)

    def pick(own, default):
        return default if own is None else own
    return {
        "mic": pick(m.can_mic if m else None, meeting.mic_default),
        "cam": pick(m.can_cam if m else None, meeting.cam_default),
        "chat": meeting.chat_on and pick(m.can_chat if m else None, True),
        "screen": pick(m.can_screen if m else None, meeting.screen_default),
    }


def visible_meetings(user, ended=False):
    """Foydalanuvchi ko'ra oladigan meetinglar. ended=True — yakunlanganlar ham (ro'yxat jadvali uchun)."""
    qs = MeetingModel.objects.all() if ended else MeetingModel.objects.exclude(status="ended")
    if user.is_main:
        return qs
    mine = Q(host=user) | Q(members__user=user, members__banned=False, members__invited=True) | Q(members__user=user, members__role="cohost", members__banned=False)
    if ended:   # yakunlangan meetingni faqat qatnashgan yoki taklif qilinganlar ko'radi
        part = Q(sessions__user=user)
        return qs.filter(Q(status__in=["scheduled", "live"], kind="public") & ~Q(members__user=user, members__banned=True) | mine | part).distinct()
    return qs.filter(Q(kind="public") & ~Q(members__user=user, members__banned=True) | mine).distinct()


def clean_perms(codes):
    return sorted(c for c in (codes or []) if c in MPERM_CODES)
