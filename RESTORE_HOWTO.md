# 🔄 Jak obnovit databázi LeadBridge ze zálohy

## ⚠️ DŮLEŽITÉ VAROVÁNÍ

**Obnovení databáze je DESTRUKTIVNÍ operace!**

- ❌ Vymaže **VŠECHNA** současná data na produkci
- ❌ Data z rozbité databáze budou **ZTRACENA**
- ✅ Před obnovením se automaticky vytvoří bezpečnostní záloha

**Doporučení:**
1. Použijte tuto funkci pouze v krajní nouzi
2. Pokud možno, zkuste problém vyřešit bez obnovení zálohy
3. Ujistěte se, že máte správnou zálohu (zkontrolujte datum)

---

## 🚀 Jednoduchý způsob - 1 příkaz

```bash
./restore_database.sh
```

## 📋 Krok za krokem

### 1. Otevřete terminál a přejděte do projektu

```bash
cd ~/PycharmProjects/Lead_Bridge
```

### 2. Spusťte restore skript

```bash
./restore_database.sh
```

### 3. Vyberte zálohu

Skript zobrazí seznam všech dostupných záloh:

```
📋 Dostupné zálohy:

  [0] backup_20260119_104853.sql.gz (23K) - 2026-01-19 10:48:53
  [1] backup_20260118_153022.sql.gz (22K) - 2026-01-18 15:30:22
  [2] backup_20260117_090015.sql.gz (21K) - 2026-01-17 09:00:15

Zadejte číslo zálohy, kterou chcete obnovit (nebo 'q' pro zrušení):
```

**Zadejte číslo** zálohy (např. `0` pro nejnovější).

### 4. Potvrďte obnovení

```
🔴 Opravdu chcete VYMAZAT všechna data a obnovit tuto zálohu? (ano/ne):
```

**Napište `ano`** a stiskněte Enter.

### 5. Počkejte na dokončení

Skript provede:
1. ✅ Vytvoří bezpečnostní zálohu aktuálního stavu
2. ✅ Rozbalí vybranou zálohu
3. ✅ Vymaže všechna data z databáze
4. ✅ Importuje data ze zálohy
5. ✅ Ověří, že obnovení proběhlo správně

### 6. Zkontrolujte web

Otevřete web a ověřte, že vše funguje správně:
```
https://www.leadbridge.cz
```

---

## 🛠️ Co dělat, když něco selže?

### Scénář 1: Obnovení se nezdařilo

Skript automaticky vytvořil bezpečnostní zálohu. Najdete ji v:
```
~/backups/leadbridge/before_restore_YYYYMMDD_HHMMSS.sql.gz
```

**Obnovte původní stav:**
```bash
./restore_database.sh
# Vyberte bezpečnostní zálohu (before_restore_...)
```

### Scénář 2: Web nefunguje po obnovení

1. **Zkontrolujte Railway logy:**
   ```bash
   railway logs
   ```

2. **Možná je potřeba restartovat službu:**
   - Jděte do Railway Dashboard
   - Vyberte službu "web"
   - Klikněte "Restart"

3. **Možná chybí migrace:**
   ```bash
   railway run python manage.py migrate
   ```

### Scénář 3: Chci obnovit starší zálohu

```bash
./restore_database.sh
# Vyberte číslo starší zálohy ze seznamu
```

---

## 📊 Co skript dělá?

```
┌─────────────────────────────────────────┐
│  1. Zobrazí seznam záloh                │
│  2. Nechá vás vybrat jednu              │
│  3. Vytvoří bezpečnostní zálohu         │
│  4. Rozbalí vybranou zálohu             │
│  5. Vymaže všechna data z DB            │
│  6. Importuje data ze zálohy            │
│  7. Ověří správnost obnovení            │
└─────────────────────────────────────────┘
```

---

## 💡 Tipy a triky

### Zobrazit všechny zálohy

```bash
ls -lh ~/backups/leadbridge/
```

### Otevřít složku se zálohami

```bash
open ~/backups/leadbridge
```

### Zkontrolovat, co je v záloze

```bash
# Rozbalit a zobrazit prvních 50 řádků
gunzip -c ~/backups/leadbridge/backup_20260119_104853.sql.gz | head -50
```

### Obnovit konkrétní zálohu ručně (pokročilé)

```bash
# 1. Rozbalit
gunzip ~/backups/leadbridge/backup_20260119_104853.sql.gz

# 2. Připojit se k databázi a importovat
psql "postgresql://user:pass@host:port/database" < ~/backups/leadbridge/backup_20260119_104853.sql
```

---

## ⚠️ Časté chyby

### "Permission denied"
```bash
chmod +x restore_database.sh
```

### "psql: command not found"
```bash
brew install postgresql@17
```

### "Connection refused"
- Zkontrolujte, že DATABASE_PUBLIC_URL je správné
- Zkontrolujte připojení k internetu
- Zkontrolujte, že Railway služba běží

---

## 🔒 Bezpečnost

- Zálohy obsahují **citlivá data** (hesla, osobní údaje)
- **NIKDY** je nenahrávejte na veřejné služby (Dropbox, Google Drive bez šifrování, atd.)
- Ukládejte je na **bezpečném místě** (šifrovaný disk, password manager)
- Po obnovení smažte dočasné soubory

---

## 📞 Potřebujete pomoc?

Pokud máte problém:
1. Zkontrolujte Railway logy: `railway logs`
2. Zkontrolujte, že máte poslední verzi skriptů z Gitu
3. Pokud nic nepomáhá, kontaktujte podporu

---

## ✅ Checklist před obnovením

- [ ] Mám správnou zálohu (zkontroloval jsem datum)
- [ ] Vím, proč potřebuji obnovit databázi
- [ ] Zkusil jsem jiná řešení před obnovením
- [ ] Jsem připraven, že současná data budou ztracena
- [ ] Mám čas zkontrolovat web po obnovení
