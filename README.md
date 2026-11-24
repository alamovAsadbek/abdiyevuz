# Abdiyev.uz — Django (fullstack) versiya

Bitta HTML faylda bo‘lgan sayt endi **to‘liq Django loyihasi**: har bir sahifa alohida shablon, hamma ma’lumot modellarda,
ruxsatlar backendda, JWT, WebSocket, himoyalangan fayl/video xizmati. **Dizayn (CSS) o‘zgarmagan** — `static/css/app.css` original CSS bilan bir xil.

## Ishga tushirish
```bash
python -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # SECRET_KEY va JWT_SECRET ni almashtiring
python manage.py migrate
python manage.py seed_demo                             # demo ma’lumotlar (keyin kerak bo‘lmasa yuklamang)
python -m daphne -p 8000 config.asgi:application       # yoki: python manage.py runserver (WebSocket bilan)
```
Video siqish uchun **ffmpeg** o‘rnatilgan bo‘lishi kerak (`sudo apt install ffmpeg`). Word → PDF uchun ixtiyoriy: LibreOffice.

Demo loginlar: `abdiyev / Admin#2026` (asosiy), `yordamchi / Yordam#2026` (yordamchi), `ali, nilufar, jasur, madina, sardor / Talaba#2026`.
Django admin: `/admin/` (asosiy o‘qituvchi bilan kiriladi). Haqiqiy ishga o‘tganda demo foydalanuvchilarni o‘chiring yoki `python manage.py createsuperuser` ishlating.

## Tuzilma
```
config/                  settings, urls, asgi (HTTP + WebSocket)
apps/
  core/                  JWT (jwt_auth), middleware, permissions (perms), himoyalangan fayl xizmati (protected),
                         scheduler (avto-status), websocket (ws), umumiy yordamchilar
  accounts/   UserModel, GroupModel, LoginHistoryModel, RefreshTokenModel  + login/register/users/groups/dashboard/stats
  courses/    CourseModel, ModuleModel, LessonModel, LessonMaterialModel, TaskModel, TaskFileModel, SubmissionModel,
              LessonProgressModel, CourseAccessModel, PurchaseRequestModel, GuideModel, GuideFileModel
  exams/      TestModel, QuestionModel, AttemptModel, RetakeGrantModel, TestAccessModel, ErrorReportModel
  notifications/  NotificationModel, MessageModel, MessageDeliveryModel
templates/
  base.html              umumiy navbar + sidebar + mobil menyu (hamma sahifa shundan meros oladi)
  partials/              qayta ishlatiladigan bo‘laklar (ro‘yxat, maydon, select, tab…)
  auth/  public/  errors/
  shared/                hamma rollar uchun sahifalar (kurslar, darslar, testlar, guruhlar, qo‘llanma, profil…)
  student/               talaba sahifalari (panel, vazifalarim, guruh)
  staff/                 asosiy va yordamchi o‘qituvchi sahifalari (users, courses, lessons, tasks, tests, messages, guides)
static/css/app.css       original dizayn      static/js/app.js  klient kodi      static/js/guide.js  Mendeleyev jadvali va h.k.
```
Barcha modellar `...Model` nomi bilan (UserModel, TestModel …), hammasi `/admin/` ga ulangan.

## Maqolalar va umumiy sozlamalar
- Sayt ochilganda (`/`) birinchi **maqolalar lentasi** chiqadi; undan keyin foydalanuvchi testlar, kurslar yoki kirish/ro‘yxatdan o‘tishga o‘tadi.
- Maqola qo‘shish/tahrirlash/aktiv-noaktiv/o‘chirish: asosiy o‘qituvchi yoki `articles` ruxsati bor yordamchi (matn tozalanadi, muqova qayta kodlanadi). Modellar: `ArticleModel`, `SiteSettingsModel`.
- **Sozlamalar → Umumiy sozlamalar** (faqat asosiy o‘qituvchi): «Maqolalarni login qilmasdan ko‘rish» va «Ro‘yxatdan o‘tish ochiq».
- Kurs yaratish endi ikki bosqichli: avval kurs (nom, turi), so‘ng kurs sahifasidan modul yoki video dars qo‘shiladi.
- Dars sahifasida video ostida dars ma’lumotlari (tavsif, ko‘rishlar, qo‘llanmalar, vazifalar, davomiylik) chiqadi.

## Rollar va ruxsatlar (faqat backendda)
`apps/core/perms.py`: `@login_required`, `@teacher_required`, `@main_required`, `@student_required`, `@perm_required("users")`.
Asosiy o‘qituvchi — hammasi. Yordamchi — faqat `UserModel.perms` dagi ruxsatlar (`users, gift, tests, courses, tasks, notify, activity, groups, guides, articles`)
va faqat **o‘z guruhlari talabalari** ustida. Ruxsatni asosiy o‘qituvchi foydalanuvchi sahifasi → «Ruxsatlar» tabida beradi (yoki yordamchini yaratayotganda belgilaydi).
Tugmalarni yashirish faqat qulaylik uchun — server har bir so‘rovni qayta tekshiradi.

## JWT
- Login → `km_access` (15 daqiqa) + `km_refresh` (7 kun) **HttpOnly, SameSite=Lax, (productionda Secure)** cookie.
- Access tugasa refresh orqali avtomatik yangilanadi (rotatsiya, bazada saqlanadi, logout/parol almashtirishda bekor qilinadi).
- `Authorization: Bearer <token>` sarlavhasi ham qabul qilinadi. Bloklangan foydalanuvchi darhol chiqib ketadi.
- CSRF himoyasi, login brute-force cheklovi (6 urinish / 10 daqiqa), CSP (inline skript yo‘q), HSTS, X-Frame-Options: DENY.

## Talaba hech narsa yuklab ola olmaydi
- Yuklangan fayllar `MEDIA_URL`siz, `private/` papkada — hech qanday URL orqali to‘g‘ridan-to‘g‘ri berilmaydi.
- PDF/rasm talabaga **server tomonida sahifa-rasmga** aylantirilib, har bir sahifaga uning **ismi va ID si suv belgisi** qilib bosiladi (`/f/<tur>/<id>/<n>.png`). Asl fayl talabaga umuman jo‘natilmaydi.
  Yuklab olish (`/f/.../download/`) faqat o‘qituvchilarga.
- Video: yuklanganda **ffmpeg bilan siqiladi** (x264 CRF 27, ≤1080p — hajm odatda 2–8 baravar kamayadi, ko‘rinish sifati saqlanadi),
  **AES-128 shifrlangan HLS** bo‘laklariga ajratiladi, asl fayl o‘chiriladi. Kalit va bo‘laklar faqat kirish huquqi bor foydalanuvchiga beriladi.
  Sifat/hajm: `.env` → `VIDEO_CRF` (23 — sifatliroq, 30 — kichikroq).
- Brauzer tomonida: o‘ng tugma/saqlash/chop etish/PrintScreen va oyna fokusini yo‘qotganda xiralashtirish (talaba uchun).
> Aniq haqiqat: ekranni telefon kamerasi bilan suratga olishni hech qanday veb-sayt to‘xtata olmaydi — shuning uchun har bir sahifa/videoda foydalanuvchi ID si suv belgisi bor.

## Avtomatik statuslar (backend)
`apps/core/scheduler.py` har 20 soniyada: test **kutilmoqda → aktiv → tugagan** holatini o‘zgartiradi; vazifa muddati tugasa **yuklash avtomatik yopiladi**
(`is_closed`) va talabalarga xabar ketadi. Server har so‘rovda vaqtni o‘zi ham tekshiradi (`live_status`, `TaskModel.is_open`), shuning uchun scheduler kechiksa ham
yopiq vazifaga fayl yuklab bo‘lmaydi. **Muddati tugagan vazifa keyingi darslarni bloklamaydi** — talaba keyingi darslarni ko‘rishda davom etadi.
Talaba yuklagan faylini «Yuborgan faylim» tugmasi orqali ko‘ra oladi.
Bir nechta jarayon (gunicorn/uvicorn workers) ishlatsangiz: `RUN_SCHEDULER=0` qo‘ying va alohida `python manage.py run_scheduler` ishga tushiring.

## WebSocket
`/ws/live/` (JWT cookie bilan autentifikatsiya, Origin tekshiriladi): yangi bildirishnoma/xabarnoma (qo‘ng‘iroqcha va toast), test statusi o‘zgarishi,
vazifa yopilishi, onlayn holati. Productionda `REDIS_URL` + `channels-redis` o‘rnating (bir nechta jarayon uchun majburiy).

## «Kurs sovg‘a qilish» xatosi
Sabab: eski kod faqat narxi > 0 bo‘lgan modullarni ro‘yxatga chiqarardi — bepul modulli kurslarda ro‘yxat bo‘sh qolardi. Endi **kursning barcha modullari** narxi bilan chiqadi
(talabada borlari o‘chirilgan holda), «Barcha modullar» tanlovi ham bor. Ikkala yo‘l ishlaydi: foydalanuvchi sahifasi → «Kurs berish» va kurs sahifasi → «Talabalarga berish».

## Production
`DEBUG=0`, `SECRET_KEY`, `JWT_SECRET`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `COOKIE_SECURE=1`, `TRUST_PROXY=1` (nginx ortida), PostgreSQL (`POSTGRES_*`), Redis.
Nginx: `client_max_body_size 2g;`, `/ws/` uchun Upgrade sarlavhalari; `private/` papkani **hech qachon** nginx orqali ochmang. `python manage.py collectstatic`.

## Cheklovlar (ochiq aytaman)
- To‘lov tizimi ulanmagan: «Sotib olish» tugmasi o‘qituvchiga so‘rov yuboradi, o‘qituvchi kursni ochib beradi (asl nusxadagi eslatma bilan bir xil).
- SMS provayderi ulanmagan (`SMS_BACKEND=console`): `apps/notifications/services.py::send_sms` ga o‘z provayderingizni ulang.
- Video siqish fon oqimida (thread) ishlaydi; juda ko‘p video uchun Celery tavsiya etiladi.
- Ro‘yxatlar Python tomonida filtrlanadi/sahifalanadi — bir necha ming yozuvgacha qulay.
- Sinov skriptlari: `python manage.py shell < scripts/smoke_pages.py` (barcha sahifalar, barcha rollar) va `scripts/smoke_flows.py` (asosiy jarayonlar), `scripts/smoke_articles.py` (maqola, sozlamalar, kurs yaratish) — `seed_demo` dan keyin.

## Uchrashuvlar (Meeting) — video suhbat

- **Yaratish:** o‘qituvchi (`Ruxsatlar` → «Uchrashuv tashkil qilish») `/meetings/new/` da meeting yaratadi: **ochiq** (tizimga kirgan hamma qo‘shila oladi) yoki **yopiq** (faqat taklif qilinganlar).
- **Dashboard:** foydalanuvchiga ko‘rinadigan jonli va rejalashtirilgan meetinglar panelda chiqib turadi (jonli yangilanadi).
- **Yordamchi (co-host):** egasi yordamchi o‘qituvchini biriktiradi va unga alohida huquq beradi: chiqarish, mikrofon/kamerani o‘chirish, izohni o‘chirish, taklif qilish, ruxsat berish, yakunlash.
- **Xonada:** kamera, mikrofon, ekran ulashish, qo‘l ko‘tarish, chat, `@username` bilan belgilash (belgilangan odamga bildirishnoma boradi), izohni o‘chirish, qatnashchini chiqarib yuborish (qayta kirolmaydi, egasi qaytara oladi), hammaning mikrofonini o‘chirish, har bir qatnashchiga mikrofon/kamera/chat/ekran ruxsati, chatni yoqish/o‘chirish, meetingni yakunlash.
- **Ruxsatlar faqat serverda** tekshiriladi (`apps/meetings/access.py`, `consumers.py`). Moderatsiya tarixi admin panelda.
- Bo‘sh qolgan meeting `MEETING_EMPTY_END_MINUTES` daqiqadan so‘ng o‘zi yakunlanadi; boshlanishidan 10 daqiqa oldin eslatma yuboriladi.

**Muhim cheklovlar**
- Brauzer kamera/mikrofonni faqat **HTTPS** (yoki localhost) da beradi — productionda sertifikat shart.
- Video P2P (mesh) usulida: qulay chegara ~`MEETING_MAX_PARTICIPANTS` (8) kishi. Kattaroq sinflar uchun SFU (LiveKit/mediasoup) kerak.
- Qattiq NAT/korporativ tarmoqlar uchun TURN server kerak: `MEETING_ICE_SERVERS` ga qo‘shing (JSON).
- Production uchun `REDIS_URL` (channels_redis) o‘rnating.

### Yangilanish: jadval, tarix, yozib olish
- `/meetings/` — **bitta jadval**: jonli, rejalashtirilgan va yakunlangan meetinglar; Holat / Turi / Boshlovchi bo‘yicha filtr va qidiruv.
- Detail sahifa bo‘limlari: Umumiy (boshlangan/tugagan/davomiyligi), Qatnashchilar (boshqaruv + statistika), Kirish-chiqish (kim soat nechida kirib chiqqani, roli), Izohlar (kim, roli, vaqti, o‘chirilganlari), Yozuvlar, Tarix (moderatsiya).
- Xona Zoom kabi: gapirayotgan odam katta oynada (ovoz balandligi bo‘yicha), qolganlar yonda; tilga bosib «qadash» mumkin; ⊞ tugmasi — hammasi teng ko‘rinish.
- Gapirishga ruxsat: umumiy qoida («Hammaga ruxsat» tugmasi), har bir odamga alohida, yoki qo‘l ko‘targanga bir bosishda.
- Yozib olish: faqat meeting egasi / asosiy o‘qituvchi. Yozuvchining brauzeri sahnani va hamma ovozini yig‘ib serverga yuboradi (`private/meeting_rec/`, webm). Hamma qatnashchiga «Yozilmoqda» belgisi ko‘rinadi. Yozuvni faqat egasi/asosiy o‘qituvchi ko‘radi va yuklab oladi. Yozuvchi sahifani yopsa, yozuv avtomatik yopiladi.
- Meeting `MEETING_LONG_MINUTES` (60) daqiqadan oshsa, egasi va asosiy o‘qituvchiga «Sizda davom etayotgan meeting bor» xabarnomasi boradi (har soatda qaytariladi).
