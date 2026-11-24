import re
import secrets

from .models import UserModel

CYR = dict(zip("абвгдежзийклмнопрстуфхцчшщъыьэюяўқғҳ", ["a","b","v","g","d","e","j","z","i","y","k","l","m","n","o","p","r","s","t","u","f","x","ts","ch","sh","sh","","i","","e","yu","ya","o","q","g","h"]))
UN_RE = re.compile(r"^[a-z0-9_.]{3,30}$")


def slugify_name(s):
    s = s.lower()
    s = "".join(CYR.get(c, c) for c in s)
    s = re.sub(r"[‘’ʻ'`]", "", s)
    return re.sub(r"[^a-z0-9]+", ".", s).strip(".") or "talaba"


def unique_username(base):
    un, n = base, 1
    while UserModel.objects.filter(username=un).exists():
        n += 1
        un = f"{base}{n}"
    return un


def gen_password(n=12):
    U, W, N, Y = "ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnpqrstuvwxyz", "23456789", "!@#$%&*?"
    a = [secrets.choice(U), secrets.choice(W), secrets.choice(N), secrets.choice(Y)]
    a += [secrets.choice(U + W + N + Y) for _ in range(n - 4)]
    secrets.SystemRandom().shuffle(a)
    return "".join(a)


def norm_phone(v):
    d = re.sub(r"\D", "", v or "")
    if d.startswith("998"):
        d = d[3:]
    return "+998 %s %s %s %s" % (d[:2], d[2:5], d[5:7], d[7:9]) if len(d) == 9 else ""


def phone_ok(v):
    return not v or bool(norm_phone(v))


def device_of(ua):
    b = "Edge" if "Edg" in ua else "Firefox" if "Firefox" in ua else "Chrome" if "Chrome" in ua else "Safari" if "Safari" in ua else "Brauzer"
    o = next((n for k, n in (("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iOS"), ("Windows", "Windows"), ("Mac", "macOS"), ("Linux", "Linux")) if k in ua), "")
    return b + (" · " + o if o else "")
