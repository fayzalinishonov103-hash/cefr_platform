# Levi (CEFR Platformasi) — Render.com ga joylash qoʻllanmasi

Ushbu qoʻllanma orqali loyihani [Render.com](https://render.com) bulutli platformasiga bepul (Free Tier) joylashingiz mumkin.

---

## 1-usul: Blueprint orqali avtomatik oʻrnatish (Tavsiya etiladi ⚡)

Loyiha ildizida `render.yaml` fayli tayyorlangan. U avtomatik ravishda:
- Python veb-servisini (Gunicorn + Flask) yaratadi;
- Bepul PostgreSQL maʼlumotlar bazasini ulaydi;
- Xavfsiz `SECRET_KEY` generatsiya qiladi;
- Demo testlarni (`python seed.py`) avtomatik yuklaydi.

### Bosqichlar:
1. **GitHub repozitoriy yarating va kodni yuklang:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit for Render"
   git branch -M main
   git remote add origin https://github.com/SIZNING_PROFILINGIZ/cefr_platform.git
   git push -u origin main
   ```
2. **Render.com ga kiring:**
   - [dashboard.render.com](https://dashboard.render.com) ga kiring (GitHub orqali kirish qulay).
3. **Blueprints boʻlimiga oʻting:**
   - **"New +"** tugmasini bosing va **"Blueprint"** ni tanlang.
   - GitHub repozitoriyangizni (`cefr_platform`) tanlang.
4. **Environment Variables (Oʻzgaruvchilar):**
   - Render `render.yaml` faylini oʻqib, PostgreSQL va xizmatni sozlaydi.
   - Sizdan faqat bitta narsani soʻraydi:
     - `OPENAI_API_KEY`: OpenAI API kalitingizni kiriting (`sk-proj-...`).
5. **"Apply" tugmasini bosing.**
   - Bir necha daqiqada loyihangiz ishga tushadi va sizga `https://cefr-platform-xxxx.onrender.com` kabi bepul HTTPS havola beriladi!

---

## 2-usul: Render Dashboard orqali qoʻlda oʻrnatish (Manual)

Agar Blueprint ishlatmasdan har birini oʻzingiz sozlamoqchi boʻlsangiz:

### A. PostgreSQL bazasini yaratish:
1. Render Dashboard ➔ **"New +"** ➔ **"PostgreSQL"**.
2. Name: `cefr-db`, Database: `cefr`, User: `levi`, Plan: `Free`.
3. Yaratilgach, **"Internal Database URL"** manzilini nusxalab oling.

### B. Veb-servisni yaratish:
1. Render Dashboard ➔ **"New +"** ➔ **"Web Service"**.
2. GitHub repozitoriyangizni ulang.
3. Sozlamalarni kiriting:
   - **Name:** `cefr-platform`
   - **Region:** Frankfurt (Oʻzbekistonga eng yaqin)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Pre-Deploy Command:** `python seed.py`
   - **Start Command:** `gunicorn wsgi:app --workers 2 --timeout 300`
4. **Environment Variables** (Sozlamalar boʻlimi):
   - `APP_ENV` = `production`
   - `PROXY_HOPS` = `1`
   - `SECRET_KEY` = tasodifiy 32 belgili satr
   - `DATABASE_URL` = yuqorida nusxalangan PostgreSQL URL
   - `OPENAI_API_KEY` = `sk-...`
   - `PYTHON_VERSION` = `3.11.9`
5. **"Create Web Service"** tugmasini bosing.

---

## 3. Oʻzingizni Admin qilish (Deploydan keyin)

Sayt ochilgach, roʻyxatdan oʻting. Soʻng oʻzingizni admin qilish uchun:
1. Render Dashboard ➔ `cefr-platform` xizmatingizga kiring.
2. Chap menyudan **"Shell"** (Terminal) boʻlimiga kiring.
3. Quyidagi buyruqni bajaring:
   ```bash
   flask --app app make-admin sizning_emailingiz@gmail.com
   ```
4. Endi saytda `/admin` sahifasiga kirish huquqiga ega boʻlasiz.
