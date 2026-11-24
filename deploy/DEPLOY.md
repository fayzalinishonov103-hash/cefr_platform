# Levi: serverga joylash (Ubuntu 22.04 / 24.04 VPS)

Bu ko'rsatma bitta VPS uchun: nginx + gunicorn + (ixtiyoriy) PostgreSQL. Fayllar shu papkada: `nginx.conf`, `levi.service`, `backup.sh`.

> **Avval huquqiy masala (serverni tanlashdan oldin):** O'zbekiston fuqarolarining shaxsiy ma'lumotlarini saqlash joyi va ma'lumotlar bazasini davlat reestridan ro'yxatdan o'tkazish bo'yicha qoidalar bor va yaqinda o'zgargan. Aniq talabni yurist bilan tekshiring. Eng xavfsiz yo'l: o'zbekistonlik hostingdagi VPS. Bilishingiz kerak: insho va speaking matnlari OpenAI'ga yuboriladi (maxfiylik siyosatida yozilgan).

## 1. Server tayyorlash
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx postgresql
sudo adduser --system --group --home /srv/levi levi
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

## 2. Kodni joylash
Zip'ni serverga yuboring (`scp cefr_platform_vXX.zip user@server:/tmp/`), keyin:
```bash
sudo mkdir -p /srv/levi && cd /srv/levi
sudo unzip /tmp/cefr_platform_vXX.zip && sudo mv cefr_platform app
sudo python3 -m venv venv && sudo ./venv/bin/pip install -r app/requirements.txt
sudo chown -R levi:levi /srv/levi
```

## 3. Sozlamalar (.env)
```bash
cd /srv/levi/app && sudo -u levi cp .env.example .env && sudo -u levi nano .env
```
Majburiylar: `OPENAI_API_KEY`, `SECRET_KEY` (`python3 -c "import secrets; print(secrets.token_hex(32))"`), `APP_ENV=production`, `PROXY_HOPS=1`.
Tavsiya: `AI_GLOBAL_DAILY_CAP` (masalan 1500: barcha foydalanuvchilar uchun kunlik AI chaqiruvlar chegarasi), `PRIVACY_CONTACT`, SMTP maʼlumotlari, Telegram bot.
PostgreSQL uchun: `sudo -u postgres createuser levi -P && sudo -u postgres createdb levi -O levi`, so'ng `.env` ga `DATABASE_URL=postgresql://levi:PAROL@localhost/levi`.

## 4. Ishga tushirish
```bash
sudo cp deploy/levi.service /etc/systemd/system/levi.service
sudo systemctl daemon-reload && sudo systemctl enable --now levi
sudo systemctl status levi          # "active (running)" boʻlsin
curl http://127.0.0.1:8000/health   # {"ok": true}
```
Birinchi marta: `cd /srv/levi/app && sudo -u levi ../venv/bin/python seed.py` (demo kontent). Admin qilish: saytda ro'yxatdan o'ting, so'ng
`sudo -u levi ../venv/bin/flask --app app make-admin sizning@emailingiz.uz`.

## 5. Nginx
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/levi    # ichidagi domenni almashtiring
sudo ln -s /etc/nginx/sites-available/levi /etc/nginx/sites-enabled/levi && sudo nginx -t && sudo systemctl reload nginx
```

## 6. HTTPS (majburiy)
Domenning A yozuvi serverga qaragan bo'lsin, keyin: `sudo certbot --nginx -d levi.example.uz -d www.levi.example.uz`. Sertifikat o'zi yangilanadi.

## 7. Tezlashtirish (bir marta, o'z kompyuteringizda)
```bash
python tools/build_css.py        # Tailwind ni CDN dan oʻzimizga koʻchiradi
python tools/fetch_fonts.py      # Google shriftlarini oʻzimizga koʻchiradi
```
Keyin hosil bo'lgan `static/css/` va `static/fonts/` ni serverga yuboring va `sudo systemctl restart levi`.

## 8. Zaxira nusxa (majburiy)
```bash
sudo -u levi crontab -e     # quyidagi qatorni qoʻshing:
0 3 * * * /srv/levi/app/deploy/backup.sh >> /srv/levi/backup.log 2>&1
```
Zaxirani boshqa joyga ham nusxalang, masalan boshqa serverga: `rsync -a /srv/levi/backups/ user@boshqa-server:/backups/levi/`.
**Zaxirani tiklab ko'ring** (bir marta): zaxira tiklanmasa, u zaxira emas.

## 9. Yangilash
Yangi zip'ni oching, `.env`, `instance/`, `static/audio/`, `static/maps/` ga tegmasdan kodni almashtiring, so'ng:
```bash
cd /srv/levi/app && ../venv/bin/pip install -r requirements.txt && sudo systemctl restart levi
```
Yangi jadval va ustunlar ilova ishga tushganda o'zi qo'shiladi.

## Ommaga ochishdan oldingi tekshiruv ro'yxati
- [ ] `https://domen/health` ishlaydi, sayt faqat HTTPS orqali ochiladi
- [ ] `python tools/check_smtp.py sizning@emailingiz.uz` xat yubordi; yangi hisob ochganda tasdiqlash kodi keladi
- [ ] Telegram bot: BotFather'da `/setdomain` ga domen kiritilgan, `TELEGRAM_BOT_USERNAME` va `TELEGRAM_BOT_TOKEN` berilgan
- [ ] OpenAI panelida oylik xarajat chegarasi va ogohlantirish qo'yilgan; `AI_GLOBAL_DAILY_CAP` berilgan
- [ ] 10–20 ta haqiqiy insho bilan `python tools/eval_writing.py insholar.csv --repeat 2` o'tkazilgan
- [ ] Zaxira tiklab ko'rilgan
- [ ] Maxfiylik siyosati va Foydalanish shartlari yurist ko'rigidan o'tgan, aloqa manzili (`PRIVACY_CONTACT`) berilgan
- [ ] Telefonda (sekin internetda) ro'yxatdan o'tish, test topshirish, intro tekshirilgan
- [ ] Uptime kuzatuv (masalan UptimeRobot) `/health` ni tekshiradi
