import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None):
    return os.environ.get(key, default)


# .env fayl bo'lsa o'qiladi (oddiy parser)
_envf = BASE_DIR / ".env"
if _envf.exists():
    for line in _envf.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DEBUG = env("DEBUG", "1") == "1"
SECRET_KEY = env("SECRET_KEY", "dev-only-insecure-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Productionda SECRET_KEY majburiy")
JWT_SECRET = env("JWT_SECRET", SECRET_KEY)
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [h.strip() for h in env("CSRF_TRUSTED_ORIGINS", "").split(",") if h.strip()]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.courses.apps.CoursesConfig",
    "apps.exams.apps.ExamsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.meetings.apps.MeetingsConfig",
]

AUTH_USER_MODEL = "accounts.UserModel"
LOGIN_URL = "/login/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.JWTAuthMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "apps.core.context.shell",
    ]},
}]

if env("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER", ""), "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"), "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3",
                             "OPTIONS": {"timeout": 20}}}

if env("REDIS_URL"):
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
                                  "CONFIG": {"hosts": [env("REDIS_URL")]}}}
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher",
                    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher"]

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = DEBUG
# MUHIM: MEDIA_URL yo'q — yuklangan fayllar hech qachon to'g'ridan-to'g'ri berilmaydi.
PRIVATE_ROOT = Path(env("PRIVATE_ROOT", str(BASE_DIR / "private")))
PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)

# ---- JWT ----
JWT_ACCESS_MINUTES = int(env("JWT_ACCESS_MINUTES", "15"))
JWT_REFRESH_DAYS = int(env("JWT_REFRESH_DAYS", "7"))
COOKIE_SECURE = env("COOKIE_SECURE", "0" if DEBUG else "1") == "1"
TRUST_PROXY = env("TRUST_PROXY", "0") == "1"

# ---- Xavfsizlik ----
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = env("SSL_REDIRECT", "0") == "1"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_PROXY else None
LOGIN_MAX_FAILS = int(env("LOGIN_MAX_FAILS", "6"))
LOGIN_LOCK_MINUTES = int(env("LOGIN_LOCK_MINUTES", "10"))

# ---- Yuklashlar ----
MAX_UPLOAD_MB = int(env("MAX_UPLOAD_MB", "25"))
MAX_VIDEO_MB = int(env("MAX_VIDEO_MB", "2048"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

# ---- Video ----
VIDEO_CRF = int(env("VIDEO_CRF", "27"))          # 23 — sifat yuqori, 30 — hajm kichik
VIDEO_MAX_HEIGHT = int(env("VIDEO_MAX_HEIGHT", "1080"))
VIDEO_WORKERS = int(env("VIDEO_WORKERS", "1"))
FFMPEG = env("FFMPEG", "ffmpeg")
FFPROBE = env("FFPROBE", "ffprobe")

# ---- Fon vazifalari ----
RUN_SCHEDULER = env("RUN_SCHEDULER", "1") == "1"
SCHEDULER_INTERVAL = int(env("SCHEDULER_INTERVAL", "20"))
SMS_BACKEND = env("SMS_BACKEND", "console")

# ---- Meeting (WebRTC) ----
import json as _json
MEETING_ICE_SERVERS = _json.loads(env("MEETING_ICE_SERVERS", '[{"urls": ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]}]'))
MEETING_REC_MAX_MB = int(env("MEETING_REC_MAX_MB", "2048"))
MEETING_LONG_MINUTES = int(env("MEETING_LONG_MINUTES", "60"))
MEETING_MAX_PARTICIPANTS = int(env("MEETING_MAX_PARTICIPANTS", "8"))   # mesh: 8 tagacha tavsiya etiladi
MEETING_EMPTY_END_MINUTES = int(env("MEETING_EMPTY_END_MINUTES", "10"))

LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"c": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["c"], "level": "INFO"}}
