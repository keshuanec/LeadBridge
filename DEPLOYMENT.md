# 🚀 Návod na nasazení Lead Bridge do produkce

## ✅ Projekt je připravený pro nasazení na:
- **Railway.app** (doporučeno)
- DigitalOcean App Platform
- Heroku
- Jakýkoliv hosting s podporou Django + PostgreSQL

---

## 📦 Doporučený hosting: Railway.app

### Proč Railway?
- ✅ Nejjednodušší nasazení (3 kliky)
- ✅ Automatický PostgreSQL zdarma
- ✅ 5$ měsíčně kredit zdarma
- ✅ Automatické deploymenty z GitHubu
- ✅ Cena: ~$5-20/měsíc podle použití

---

## 🎯 Postup nasazení na Railway

### 1. Příprava projektu (už je hotová! ✅)
- ✅ `requirements.txt` - Python dependencies
- ✅ `Procfile` - příkazy pro spuštění
- ✅ `runtime.txt` - verze Pythonu
- ✅ `railway.json` - Railway konfigurace
- ✅ `.env.example` - šablona environment variables

### 2. Vytvoření účtu na Railway
1. Otevři https://railway.app
2. Klikni na "Start a New Project"
3. Přihlaš se přes GitHub účet

### 3. Nasazení aplikace

#### A) Připrav GitHub repozitář:
```bash
# Přidej všechny změny
git add .
git commit -m "Připraveno pro produkci"
git push origin main
```

#### B) Na Railway.app:
1. Klikni na **"New Project"**
2. Vyber **"Deploy from GitHub repo"**
3. Vyber svůj repozitář `Lead_Bridge`
4. Railway automaticky detekuje Django a začne build

#### C) Přidání PostgreSQL databáze:
1. V projektu klikni na **"+ New"**
2. Vyber **"Database" → "Add PostgreSQL"**
3. Railway automaticky vytvoří `DATABASE_URL` proměnnou

### 4. Nastavení Environment Variables

V Railway projektu → **Variables** přidej:

```env
SECRET_KEY=<vygeneruj nový - viz níže>
DEBUG=False
ALLOWED_HOSTS=<tvoje-domena>.up.railway.app

# Email (volitelné - zatím můžeš nechat console backend)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=tvuj-email@gmail.com
EMAIL_HOST_PASSWORD=<app-specific-password>
DEFAULT_FROM_EMAIL=noreply@leadbridge.cz
```

**Generování SECRET_KEY:**
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. První deploy
1. Railway automaticky spustí build
2. Po dokončení buildu se spustí `release` command (migrace + collectstatic)
3. Pak se spustí aplikace

### 6. Vytvoření superusera
V Railway projektu → **Deployments** → **View Logs** → najdi záložku **"Shell"**:

```bash
python manage.py createsuperuser
```

### 7. Ověření
1. Otevři URL z Railway (např. `https://leadbridge-production.up.railway.app`)
2. Přihlas se s superuserem
3. Vytvoř testovací data

---

## 📧 Nastavení emailů (Gmail)

### Pro Gmail (doporučeno pro začátek):
1. Zapni "2-Step Verification" v Google účtu
2. Jdi na https://myaccount.google.com/apppasswords
3. Vytvoř "App Password" pro "Mail"
4. Použij tento password v `EMAIL_HOST_PASSWORD`

### Environment variables pro Gmail:
```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=tvuj-email@gmail.com
EMAIL_HOST_PASSWORD=<16-char-app-password>
DEFAULT_FROM_EMAIL=noreply@leadbridge.cz
```

---

## 🔧 Troubleshooting

### Aplikace nefunguje:
1. Zkontroluj logy v Railway: **Deployments** → **View Logs**
2. Ověř environment variables
3. Zkontroluj že `DATABASE_URL` existuje

### Statické soubory se nenačítají:
- Railway automaticky spouští `collectstatic` v `release` příkazu
- Ověř v logs že to proběhlo bez chyb

### Database issues:
```bash
# V Railway Shell:
python manage.py migrate
python manage.py createsuperuser
```

---

## 💰 Ceny Railway

- **Free tier**: $5 kredit měsíčně (cca 500 hodin běhu)
- **Hobby**: $5-10/měsíc pro malé projekty
- **Pro**: $20+/měsíc pro větší projekty

Pro tvůj CRM bude stačit **Hobby** plán (~$8-12/měsíc).

---

## 🔐 Bezpečnost v produkci

### ✅ Už nastaveno:
- SECRET_KEY z environment variables
- DEBUG=False v produkci
- ALLOWED_HOSTS kontrola
- HTTPS redirect
- Secure cookies
- CSRF protection
- XSS protection

### Doporučené další kroky:
1. Zapnout vlastní doménu (např. crm.tvoje-firma.cz)
2. Pravidelné zálohy databáze (Railway má automatické)
3. Monitoring (Railway má základní metrics)

---

## 📝 Další hostingy

### DigitalOcean App Platform:
- Podobné Railway, ale trochu složitější
- $5-12/měsíc
- https://www.digitalocean.com/products/app-platform

### Heroku:
- Klasická volba, ale dražší
- Min. $7/měsíc za Hobby Dyno
- https://www.heroku.com

---

## 🆘 Potřebuješ pomoct?

Pokud narazíš na problém:
1. Zkontroluj logy v Railway
2. Ověř všechny environment variables
3. Zkontroluj že PostgreSQL běží
4. Spusť migrace manuálně v Shell

Railway má výbornou dokumentaci: https://docs.railway.app