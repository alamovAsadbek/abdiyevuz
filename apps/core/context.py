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
    R = reverse
    if not u.is_authenticated:
        return [("home", "file-text", "Maqolalar", "Maqola"), ("tests", "check-square", "Testlar", "Testlar"),
                ("courses", "play-circle", "Kurslar", "Kurslar"), ("login", "log-in", "Kirish", "Kirish")]
    g = ("guides", "book-open", "Qo‘llanma", "Qo‘llanma")
    if u.is_student:
        return [("dashboard", "grid", "Panel", "Panel"), ("home", "file-text", "Maqolalar", "Maqola"), ("courses", "play-circle", "Kurslar", "Kurslar"),
                ("tests", "check-square", "Testlar", "Testlar"), ("meetings", "video", "Uchrashuvlar", "Meeting"), ("groups", "layers", "Guruhlarim", "Guruhlar"),
                ("tasks", "clipboard", "Vazifalarim", "Vazifalar"), ("stats", "bar-chart-2", "Statistika", "Statistika"), g,
                ("settings", "settings", "Sozlamalar", "Sozlama"), ("profile", "user", "Profil", "Profil")]
    items = [("dashboard", "grid", "Panel", "Panel"), ("home", "file-text", "Maqolalar", "Maqola")]
    if u.can("tasks"): items.append(("tasks", "clipboard", "Vazifalar", "Vazifalar"))
    if u.can("users"): items.append(("users", "users", "Foydalanuvchilar", "Userlar"))
    items += [("groups", "layers", "Guruhlar", "Guruhlar"), ("tests", "check-square", "Testlar", "Testlar")]
    if u.can("tests"): items.append(("reports", "flag", "Xato xabarlari", "Xabarlar"))
    if u.can("notify"): items.append(("messages", "send", "Xabarnomalar", "Xabarnoma"))
    items.append(("meetings", "video", "Uchrashuvlar", "Meeting"))
    items += [("courses", "play-circle", "Kurslar", "Kurslar"), g, ("stats", "bar-chart-2", "Statistika", "Statistika"),
              ("settings", "settings", "Sozlamalar", "Sozlama"), ("profile", "user", "Profil", "Profil")]
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
