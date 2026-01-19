# 🔒 Bezpečnostní Best Practices pro LeadBridge

## ⚠️ Co jsme se naučili

Dne 19.1.2026 jsme měli bezpečnostní incident:
- ❌ Hardcoded database credentials v Git repozitáři
- ✅ GitGuardian to okamžitě detekoval
- ✅ Heslo bylo změněno v Railway
- ✅ Scripty byly opraveny

**Poučení: NIKDY neukládejte credentials přímo do kódu!**

---

## ✅ Správné praktiky

### 1. Secrets a Credentials

**❌ NIKDY:**
```bash
DATABASE_URL="postgresql://user:password@host:port/db"  # ❌ Špatně!
API_KEY="sk-1234567890abcdef"                          # ❌ Špatně!
```

**✅ VŽDY:**
```bash
# Použijte environment variables z Railway CLI
DATABASE_URL=$(railway run sh -c 'echo $DATABASE_URL')

# Nebo Django environment variables
# settings.py
DATABASE_URL = os.environ.get('DATABASE_URL')
```

### 2. .gitignore

Ujistěte se, že tyto soubory jsou v `.gitignore`:
```
.env
.env.local
*.sql
*.sql.gz
backups/
*credentials*
*secrets*
```

### 3. Environment Variables

**Kde ukládat secrets:**
- ✅ Railway Variables (pro produkci)
- ✅ `.env` soubor (pro lokální vývoj, ale NIKDY ho necommitujte!)
- ✅ Password manager (1Password, Bitwarden)
- ❌ Nikdy v Git repozitáři

### 4. Railway Variables

Jak nastavit secrets v Railway:
1. Jděte do Railway Dashboard
2. Vyberte službu
3. Variables → Add Variable
4. Služba se automaticky restartuje s novými proměnnými

**Důležité proměnné v LeadBridge:**
- `DATABASE_URL` (automaticky generováno Railway)
- `DATABASE_PUBLIC_URL` (automaticky generováno Railway)
- `SECRET_KEY` (Django secret key)
- `SENDGRID_API_KEY` (pro emaily)
- `ALLOWED_HOSTS` (seznam povolených domén)

---

## 🚨 Co dělat při úniku credentials

### Okamžitá reakce (do 5 minut):

1. **Změňte heslo/API key IHNED**
   - Railway: Regenerate credentials
   - API keys: Revoke + Generate new

2. **Zkontrolujte logy**
   - Railway logs: `railway logs`
   - Hledejte podezřelou aktivitu

3. **Notifikujte tým**
   - Informujte všechny, kdo mají přístup

### Dlouhodobá náprava:

4. **Odstraňte credentials z kódu**
   ```bash
   # Najděte všechny výskyty
   git grep -i "password\|secret\|key"
   ```

5. **Commitujte opravu**
   ```bash
   git commit -m "SECURITY FIX: Remove hardcoded credentials"
   ```

6. **Pushnout na GitHub**
   ```bash
   git push origin master
   ```

**POZNÁMKA:** Git historie stále obsahuje staré commity!
To je OK, pokud jste změnili heslo (staré je neplatné).

---

## 🛡️ Prevence

### Před každým commitem:

```bash
# 1. Zkontrolujte, co commitujete
git diff --staged

# 2. Hledejte podezřelé stringy
git diff --staged | grep -i "password\|secret\|key\|token"

# 3. Pokud najdete něco podezřelého - NECOMMITUJTE!
git reset HEAD <file>
```

### Automatická ochrana - Git hooks

Můžete nastavit pre-commit hook, který zastaví commit s credentials:

```bash
# .git/hooks/pre-commit
#!/bin/bash
if git diff --cached | grep -iE "(password|secret|api[_-]?key|token).*=.*['\"]"; then
    echo "❌ VAROVÁNÍ: Možný únik credentials!"
    echo "Zkontrolujte soubory před commitem."
    exit 1
fi
```

### Použijte GitGuardian

- ✅ Už máte aktivní (poslali vám email)
- ✅ Automaticky skenuje všechny commity
- ✅ Pošle alert pokud najde credentials

---

## 📋 Security Checklist

### Před deployem:

- [ ] Žádné hardcoded credentials v kódu
- [ ] `.env` je v `.gitignore`
- [ ] Všechny secrets jsou v Railway Variables
- [ ] `DEBUG=False` v produkci
- [ ] `ALLOWED_HOSTS` správně nastaveno
- [ ] Railway má automatické SSL certifikáty
- [ ] Database má povoleno pouze private networking (nebo public s firewall)

### Pravidelně (měsíčně):

- [ ] Zkontrolujte Railway logs na podezřelou aktivitu
- [ ] Aktualizujte Django a dependencies (`pip list --outdated`)
- [ ] Zkontrolujte GitGuardian alerts
- [ ] Rotujte API keys (pokud je to možné)

### Po incidentu:

- [ ] Změňte všechny potenciálně kompromitované credentials
- [ ] Zkontrolujte access logy
- [ ] Informujte uživatele (pokud byli ovlivněni)
- [ ] Dokumentujte incident a poučení

---

## 🔐 Další bezpečnostní tipy

### Django Security

```python
# settings.py - PRODUKCE
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
```

### Database Security

- ✅ Používejte Railway Private Networking (pokud možno)
- ✅ Public networking pouze když je potřeba (backupy)
- ✅ Pravidelné rotace hesel (každých 90 dní)
- ✅ Silná hesla (generovaná automaticky Railway)

### Backup Security

- ✅ Zálohy obsahují citlivá data
- ✅ Uchovávejte je šifrované
- ✅ Nikdy je nenahrávejte na veřejné služby
- ✅ Lokální zálohy: `~/backups/` (mimo Git)

---

## 📚 Užitečné odkazy

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Django Security Best Practices](https://docs.djangoproject.com/en/stable/topics/security/)
- [Railway Security](https://docs.railway.app/guides/security)
- [GitGuardian](https://www.gitguardian.com/)

---

## 🆘 V případě nouze

Pokud si nejste jisti bezpečností:
1. **NEJDŘÍV** změňte credentials
2. **PAK** řešte problém
3. **NIKDY** nečekejte "až to dodělám"

**Heslo můžete změnit za 30 sekund, data obnovit za hodiny.**
