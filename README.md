# Levi (CEFR tayyorlov platformasi)

Milliy CEFR imtihoniga tayyorlanish platformasi: Reading, Listening, Writing, Speaking.

## Ishga tushirish (lokal)
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # OPENAI_API_KEY, SECRET_KEY ni toʻldiring (lokal ishlashda APP_ENV qatorini oʻchiring)
python seed.py              # demo testlar va topshiriqlar
python app.py               # http://127.0.0.1:5000
flask --app app make-admin EMAIL   # roʻyxatdan oʻtgach, oʻzingizni admin qiling
```
Speaking uchun mikrofon faqat `https://` yoki `localhost` da ishlaydi.

## Server (deploy)
**Toʻliq bosqichma-bosqich ko'rsatma, nginx/systemd fayllari va zaxira skripti: `deploy/DEPLOY.md`.** Quyida qisqacha:
- `gunicorn wsgi:app --workers 2 --timeout 300` (Procfile tayyor). `--timeout` AI baholash va AI bilan Listening yaratish (savollar + audio) uchun kamida 300 s boʻlsin.
- `DATABASE_URL=postgresql://...` bersangiz PostgreSQL ishlatiladi (aks holda SQLite fayl).
- `SECRET_KEY` (kamida 32 belgi) boʻlmasa, production rejimida ilova ishga tushmaydi.
- `APP_ENV=production` va `PROXY_HOPS` (proksilar soni, odatda 1) ni bering. Aks holda tezlik chegaralari haqiqiy IP ni koʻrmaydi. Sayt faqat HTTPS orqali ochilsin.
- `static/audio/` (Listening audiolari) va `static/maps/` (xarita/rasmlar) doimiy saqlanadigan diskda boʻlsin.
- Nginx orqasida boʻlsangiz `client_max_body_size 30m;` qoʻying (audio yuklash uchun).

## Ommaga ochishdan oldingi vositalar
- **Tezlik:** `python tools/build_css.py` (Tailwind ni CDN dan oʻzimizga koʻchiradi) va `python tools/fetch_fonts.py` (shriftlar). Fayllar paydo boʻlgach, `base.html` CDN lardan voz kechadi; oʻchirsangiz, CDN ga qaytadi.
- **Email:** `python tools/check_smtp.py sizning@emailingiz.uz`: parolni tiklash xatlari yetib borishini tekshiradi (587 = STARTTLS, 465 = SSL).
- **AI sifati:** `python tools/eval_writing.py insholar.csv --repeat 2`: AI baholarini oʻqituvchi baholari bilan solishtiradi (shablon: `tools/eval_writing_template.csv`).
- **AI xarajati:** `AI_GLOBAL_DAILY_CAP` barcha foydalanuvchilar uchun umumiy kunlik chegara (0 = oʻchiq). Admin → Statistika da joriy sarfni koʻrasiz.
- **Statistika:** Admin → ONBOARDING sahifasida voronka (roʻyxatdan oʻtgan → onboarding → daraja testi → test → Writing/Speaking).
- **Hujjatlar:** `/maxfiylik`, `/shartlar` (qoralama, yurist koʻrigidan oʻtkazing).

## Daraja aniqlash va mobil
- `/placement`: 25 ta savol (A1–C1), natija taxminiy daraja va mos mashqlar. Yangi foydalanuvchi ro'yxatdan o'tgach shu yerga tushadi. Savollar `placement_data.py` da.
- `/practice`: barcha mashqlar bir sahifada. Telefonda pastki menyu (Bosh, Mashq, Daraja, Lug'at, Profil) chiqadi; test topshirish paytida u yashiriladi.

## Roʻyxatdan oʻtish va onboarding
- `/register`: ism, email, parol (yoki Telegram) + ixtiyoriy savollar: **qiziqishlar** (6 tagacha), **yosh oraligʻi**, **viloyat**. Yosh va viloyat faqat rozilik belgisi bilan saqlanadi (`UserProfile.consent_at`). Aniq tugʻilgan sana, telefon va manzil soʻralmaydi.
- Roʻyxatdan oʻtgach `/onboarding?r=1`: qisqa, 3 ta savol (maqsad, daraja va imtihon sanasi, kunlik vaqt). Rozilik berilgan boʻlsa, 4-savol: bizni qayerdan eshitgan. Oʻtkazib yuborish mumkin. Ketma-ketlik: roʻyxatdan oʻtish → onboarding → daraja aniqlash.
- Telegram orqali birinchi kirganda toʻliq onboarding (6 savol) chiqadi. Sozlamalardan `/onboarding` ni istalgan vaqt qayta ochish mumkin.
- `/maxfiylik`: maxfiylik siyosati (qoralama). **Eʼlon qilishdan oldin yurist koʻrib chiqsin.** `PRIVACY_CONTACT` muhit oʻzgaruvchisiga aloqa email/Telegram yozing.
- `Admin → ONBOARDING`: viloyat, manba, yosh, qiziqish boʻyicha yigʻma statistika.
- Hisob oʻchirilganda bu javoblar ham oʻchadi.

## Hisobni tasdiqlash (soxta hisoblarga qarshi)
- **Roʻyxatdan oʻtish:** faqat ism, email, parol (yoki Telegram bitta tugma). Qiziqish, yosh, viloyat soʻralmaydi.
- **Telegram** asosiy yoʻl: parolsiz, bitta bosish, Telegram hisobi haqiqiy telefon raqamiga bogʻlangan, shuning uchun darrov «tasdiqlangan» hisoblanadi. (Telegram tugmasi faqat haqiqiy domen va `TELEGRAM_BOT_USERNAME` bilan ishlaydi, `localhost` da ishlamaydi.)
- **Email bilan:** hisob darrov ochiladi, Reading, Listening, daraja testi va lugʻatdan foydalanish mumkin. Emailga 6 xonali kod va bir bosishlik havola yuboriladi. **Writing, Speaking va AI maslahat** (pulli AI) tasdiqlangandan keyin ochiladi, shuning uchun sohta/bot hisoblar AI xarajatini yeb qoʻya olmaydi.
- Kod 10–20 daqiqa amal qiladi, xato urinishlar chegaralangan (15 daqiqada 5 ta), qayta yuborish soatiga 3 ta.
- **Bitta email = bitta hisob:** `a.b+x@gmail.com` va `ab@gmail.com` bir xil pochta hisoblanadi.
- Tasdiqlash yoqilishi: `SMTP_HOST` berilsa avtomatik yoqiladi; `VERIFY_EMAIL=1` / `0` bilan majburan yoqish/oʻchirish. SMTP yoʻq boʻlsa, tasdiqlash oʻchiq (production loglarida ogohlantirish chiqadi).
- Mavjud hisoblar bir marta «tasdiqlangan» deb belgilanadi (yangi ustunlar qoʻshilganda).

## Kirish / roʻyxatdan oʻtish himoyasi
- Roʻyxatdan oʻtishda: yashirin tuzoq maydoni (honeypot), formani 3 soniyadan tez yuborishni rad etish (testda oʻchiq), vaqtinchalik email domenlarini rad etish (`security.DISPOSABLE_DOMAINS`), IP boʻyicha limit (oldindan bor).
- Kirishda: «Bu qurilmada eslab qolish» belgisi (belgilanmasa, brauzer yopilganda chiqadi), parolni koʻrsatish/yashirish tugmasi.
- Parol uzunligi maslahati va Telegram tugmasi (bot sozlangan boʻlsa).
- Sozlamalarda «Boshqa qurilmalardan chiqish» (`session_token` aylantiriladi).
- Hali yoʻq (keyingi qadam): adminlar uchun 2 bosqichli kirish (TOTP).

## Shadowing: tez qoʻshish
`/shadowing` sahifasida adminlarga «+ SHADOWINGGA QOʻSHISH» tugmasi koʻrinadi: YouTube havolasi, turi va daraja kiritiladi, sarlavha avtomatik olinadi. Qoʻshilgach foydalanuvchi shu sahifaga qaytadi. Soʻzlar `Admin → Shadowing` da qoʻshiladi.

## Brend
Ranglar logodan olingan (sovuq palitra), hammasi `templates/base.html` boshidagi CSS oʻzgaruvchilarida: `--bg` fon, `--lime` asosiy urgʻu (muzdek koʻk `#7fc8ff`, nomi eski shablonlar uchun saqlangan), `--pur`/`--purt` koʻk, `--win` karta, `--sh` qattiq soya. Qorongʻi rejim uchun ikkinchi toʻplam bor. Rang almashtirish uchun faqat shu oʻzgaruvchilarni tahrirlang.
Kirish animatsiyasi (intro): `templates/base.html` ichida, brauzer sessiyasida bir marta (~5 s), bosib oʻtkazib yuboriladi, `prefers-reduced-motion` da va test topshirish sahifasida chiqmaydi. Vaqtlar CSS (`iEyes`, `iWord`, `iOut`) da. Qayta koʻrish/sinash: `/?intro=1` (sessiya va `prefers-reduced-motion` ni hisobga olmaydi).
Logo va favicon: `static/brand/` (SVG, qora/oq fon variantlari).

## Qoʻshimcha
- `/health` : monitoring uchun (ilova va baza ishlasa 200).
- `/settings` : foydalanuvchi ismini, parolini oʻzgartiradi yoki hisobini oʻchiradi.
- Admin: `Admin → FOYDALANUVCHILAR`, har testda `STATISTIKA` (qaysi savol juda qiyin yoki oson).
- Kunlik streak Oʻzbekiston vaqti (UTC+5) boʻyicha hisoblanadi.

## Toʻliq imtihon va AI bilan kontent
- `/exam`: 4 skill ketma-ket, oxirida umumiy daraja (toʻrt skillning oʻrtachasi). Imtihon boshlangach, har skilldan bittadan test/topshiriq bajariladi, oxirgi natija hisobga olinadi. Tugagach natija saqlanadi.
- `Admin → AI BILAN LISTENING`: transkript yoziladi, AI savollar tuzadi (mcq, gap-fill, True/False/Not Given), ixtiyoriy ravishda matndan audio yaratiladi (`OPENAI_TTS_MODEL`, standart `tts-1`). `Man:` / `Woman:` deb yozilgan suhbatda har kimga alohida ovoz beriladi. Javobi transkriptda topilmagan gap-fill savollar avtomatik olib tashlanadi. Natija muharrirda **saqlanmagan qoralama** sifatida ochiladi: toʻgʻri javoblarni tekshirib saqlang.
- `Admin → SPEAKING`: mavzu yozib "AI topshiriq tuzsin" bosilsa, forma toʻldiriladi. Siz tahrirlab qoʻshasiz.

## Xatolar daftari
- `/mistakes`: Reading va Listening'da noto'g'ri yoki javobsiz qoldirilgan savollar (oxirgi 30 ta tugatilgan urinishdan). Har savolda **eng yangi** urinish hal qiladi.
- `Mashq qilish`: 10 tagacha tasodifiy xato qayta beriladi (Reading'da matn, Listening'da audio bilan). To'g'ri javob berilgan savol daftardan o'chadi (`MistakeFixed`), keyingi haqiqiy testda yana xato qilinsa, qaytadan paydo bo'ladi.
- Ro'yxat har safar hozirgi javob kalitidan qayta hisoblanadi. Admin testni tahrirlab savollarni almashtirsa, "tuzatilgan" belgilar yo'qoladi (bu xavfsiz, xolos qaytadan mashq qilinadi).

## Listeningga xarita (map) qoʻshish
1. Xarita rasmini tayyorlang (PNG, JPG yoki WebP, 5 MB gacha). Joylarga **A, B, C...** harflarini rasmning oʻziga yozib qoʻying.
2. `Admin → Listening testi → TAHRIRLASH`. Xarita boʻlgan Part ichida **"Rasm yoki xarita"** blokidan rasmni yuklang.
3. Shu Part ichida **"+ Savollar guruhi"** → savol turi **"Map labelling"**. Harflar maydoniga `A-H` yozing.
4. **"+ Savol"**: "Qaysi joy?" maydoniga joy nomi (masalan `the library`), javobga toʻgʻri harf (masalan `C`).
5. **SAQLASH**. Talaba rasmni Part ichida koʻradi va har savolga A–H ruyxatidan tanlaydi. Rasm natija sahifasida va xatolar daftarida ham chiqadi.
Rasm Reading partlariga ham qoʻshiladi (diagramma uchun).

## Aqlli mashq, kunlik challenge, XP va reyting
- `/smart`: tizim talabaning barcha javoblaridan (testlar + oldingi mashqlar) savol turi va daraja boʻyicha oʻzlashtirishni hisoblaydi (yangi javoblar muhimroq), zaif joylarga mos 8 ta savol tanlaydi, yaqinda toʻgʻri javob berilgan savolni qaytarmaydi, xato qilinganini vaqti kelganda qaytaradi. Savollar bitta matn/audio/xarita atrofida jamlanadi. AI chaqiruvi yoʻq, xarajat nol.
- Kunlik challenge: kuniga bitta (Oʻzbekiston vaqti), 5 ta savol, kun davomida bir xil. Toʻgʻri javoblar uchun XP + seriya bonusi.
- XP faqat bir marta beriladi (`user + sabab + ref` bazada unikal). Testlar, Writing va Speaking ham XP beradi; bu ulanishlar (`gamify.after_*`) hech qachon asosiy oqimni buzmaydi.
- Reyting **ixtiyoriy** va faqat taxallus koʻrsatiladi (ism/email hech qachon). Hisob oʻchirilganda barcha yangi maʼlumot ham oʻchadi.
- Eslatma: reytingda taxalluslarni admin hozircha moderatsiya qilmaydi (faqat lotin harf/raqam, 3–20 belgi).

## Testlar
`python -m pytest -q`  (ffmpeg oʻrnatilgan boʻlishi kerak: Listening testi sinov audiosi yaratadi).
`test_access.py` ilovaning BARCHA yoʻllarini avtomatik aylanib chiqadi: kirmagan foydalanuvchi, oddiy talaba va boshqa talabaning maʼlumotlariga kira olmasligini tekshiradi. Yangi yoʻl himoyasiz qoʻshilsa, shu test yiqiladi.

## Xavfsizlik
- Parol: 10–128 belgi, oddiy/ommabop parollar va email/ismga oʻxshash parollar rad etiladi. Hash: scrypt.
- Kirishga urinishlar bazada hisoblanadi (barcha worker'lar uchun umumiy): 15 daqiqada 5 ta xato (IP+email), 20 ta (IP), 20 ta (email).
- Parolni tiklash: soatiga IP uchun 5 ta, email uchun 3 ta soʻrov. Havola bir martalik va 1 soat amal qiladi.
- Parol almashtirilsa yoki tiklansa, boshqa barcha qurilmalardagi sessiyalar tugaydi.
- Admin huquqi emailga qarab avtomatik berilmaydi: `flask --app app make-admin EMAIL` / `revoke-admin EMAIL`.
- AI chaqiruvlari uchun qattiq xarajat chegarasi (muvaffaqiyatsiz chaqiruvlar ham sanaladi).
- Sarlavhalar: CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy. Sahifa buzilsa `CSP_MODE=report-only`.
- Audio yuklashda fayl imzosi tekshiriladi. Kuchli xavfsizlik uchun keyingi qadam: adminlar uchun 2FA (TOTP) va email tasdiqlash.
