from django.urls import reverse

NAV_ACTIVE = {
    "home": "home", "dashboard": "dashboard", "tests": "tests", "courses": "courses", "login": "login",
    "users": "users", "groups": "groups", "tasks": "tasks", "stats": "stats", "guides": "guides",
    "settings": "settings", "profile": "profile", "reports": "reports", "messages": "messages",
}
PREFIX = (("user", "users"), ("test", "tests"), ("attempt", "tests"), ("course", "courses"), ("module", "courses"),
          ("lesson", "courses"), ("material", "courses"), ("group", "groups"), ("task", "tasks"), ("submission", "tasks"),
          ("guide", "guides"), ("message", "messages"), ("report", "reports"), ("notification", "dashboard"),
          ("run", "tests"), ("gift", "courses"), ("article", "home"), ("site", "settings"), ("meeting", "meetings"))


def active_key(name):
    if name in NAV_ACTIVE:
        return NAV_ACTIVE[name]
    for p, k in PREFIX:
        if name.startswith(p):
            return k
    return ""


def build_nav(u):
    if not u.is_authenticated:
        return [("home", "file-text", "Maqolalar", "Maqola"), ("tests", "check-square", "Testlar", "Testlar"),
                ("courses", "play-circle", "Kurslar", "Kurslar"), ("login", "log-in", "Kirish", "Kirish")]
    V = u.can_view
    items = [("dashboard", "grid", "Panel", "Panel")]
    if u.is_student:
        cand = [("articles", ("home", "file-text", "Maqolalar", "Maqola")), ("courses", ("courses", "play-circle", "Kurslar", "Kurslar")),
                ("tests", ("tests", "check-square", "Testlar", "Testlar")), ("meetings", ("meetings", "video", "Uchrashuvlar", "Meeting")),
                ("groups", ("groups", "layers", "Guruhlarim", "Guruhlar")), ("tasks", ("tasks", "clipboard", "Vazifalarim", "Vazifalar")),
                ("stats", ("stats", "bar-chart-2", "Statistikam", "Statistika")), ("guides", ("guides", "book-open", "Qo‘llanma", "Qo‘llanma"))]
    else:
        cand = [("articles", ("home", "file-text", "Maqolalar", "Maqola")), ("tasks", ("tasks", "clipboard", "Vazifalar", "Vazifalar")),
                ("users", ("users", "users", "Foydalanuvchilar", "Userlar")), ("groups", ("groups", "layers", "Guruhlar", "Guruhlar")),
                ("tests", ("tests", "check-square", "Testlar", "Testlar")), ("reports", ("reports", "flag", "Xato xabarlari", "Xabarlar")),
                ("notify", ("messages", "send", "Xabarnomalar", "Xabarnoma")), ("meetings", ("meetings", "video", "Uchrashuvlar", "Meeting")),
                ("courses", ("courses", "play-circle", "Kurslar", "Kurslar")), ("guides", ("guides", "book-open", "Qo‘llanma", "Qo‘llanma")),
                ("stats", ("stats", "bar-chart-2", "Statistika", "Statistika"))]
    items += [it for code, it in cand if V(code)]
    items += [("settings", "settings", "Sozlamalar", "Sozlama"), ("profile", "user", "Profil", "Profil")]
    return items


def shell(request):
    u = request.user
    name = getattr(request.resolver_match, "url_name", "") or ""
    key = active_key(name)
    nav = [{"key": k, "icon": i, "label": l, "short": s, "url": reverse(k), "on": k == key} for k, i, l, s in build_nav(u)]
    unread = 0
    if u.is_authenticated:
        from apps.notifications.services import unread_count
        unread = unread_count(u)
    from django.contrib.messages import get_messages
    flash = [{"t": str(m.message), "l": m.level_tag} for m in get_messages(request)] if hasattr(request, "_messages") else []
    from .models import SiteSettingsModel
    return {"site": SiteSettingsModel.get(), "flash": flash, "nav": nav, "nav_main": nav[:4], "unread": unread, "url_name": name}
