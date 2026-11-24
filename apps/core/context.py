from django.urls import reverse

NAV_ACTIVE = {
    "home": "home", "dashboard": "dashboard", "tests": "tests", "courses": "courses", "login": "login",
    "users": "users", "groups": "groups", "tasks": "tasks", "stats": "stats", "guides": "guides",
    "settings": "settings", "profile": "profile", "reports": "reports", "messages": "messages",
    "security": "security", "logs": "logs", "meetings": "meetings",
}
PREFIX = (("user", "users"), ("test", "tests"), ("attempt", "tests"), ("course", "courses"), ("module", "courses"),
          ("lesson", "courses"), ("material", "courses"), ("group", "groups"), ("task", "tasks"), ("submission", "tasks"),
          ("guide", "guides"), ("message", "messages"), ("report", "reports"), ("notification", "dashboard"),
          ("run", "tests"), ("gift", "courses"), ("article", "home"), ("site", "settings"), ("meeting", "meetings"),
          ("security", "security"), ("log", "logs"), ("role", "settings"), ("protect", "settings"))


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
                ("stats", ("stats", "bar-chart-2", "Statistika", "Statistika")), ("security", ("security", "shield", "Xavfsizlik", "Xavfsizlik")),
                ("logs", ("logs", "terminal", "Tizim jurnali", "Jurnal"))]
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
    site = SiteSettingsModel.get()
    prot = False
    sec_open = 0
    if u.is_authenticated:
        prot = (not u.is_main) and bool(site.protect_students if u.is_student else site.protect_assistants)
        if u.can_view("security") and not u.is_student:
            from apps.security.models import SecurityIncidentModel
            q = SecurityIncidentModel.objects.filter(reviewed=False, severity="high")
            if u.is_assistant:
                from apps.courses.services import scoped_students
                q = q.filter(user__in=scoped_students(u))
            sec_open = q.count()
    for n in nav:
        n["badge"] = sec_open if n["key"] == "security" else 0
    return {"site": site, "flash": flash, "nav": nav, "nav_main": nav[:4], "unread": unread, "url_name": name,
            "protect": prot, "sec_open": sec_open}
