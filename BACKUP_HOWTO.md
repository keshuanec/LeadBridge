# 📦 Jak vytvořit zálohu databáze LeadBridge

## 🚀 Jednoduchý způsob - 1 příkaz

Otevřete terminál v projektové složce a spusťte:

```bash
./backup_database.sh
```

## 📋 Krok za krokem

### 1. Otevřete terminál

**macOS:**
- Stiskněte `Cmd + Space`
- Napište "Terminal" a stiskněte Enter

### 2. Přejděte do projektové složky

```bash
cd ~/PycharmProjects/Lead_Bridge
```

### 3. Spusťte skript

```bash
./backup_database.sh
```

### 4. Hotovo! 🎉

Záloha bude uložena v: `~/backups/leadbridge/backup_YYYYMMDD_HHMMSS.sql.gz`

## 📁 Kde najdu zálohy?

Všechny zálohy jsou uloženy v:
```
/Users/jirihavlas/backups/leadbridge/
```

Otevřete ve Finderu:
```bash
open ~/backups/leadbridge
```

## 🔄 Obnovení zálohy

Pokud budete potřebovat obnovit zálohu:

```bash
# 1. Rozbalte zálohu
gunzip ~/backups/leadbridge/backup_20260119_104358.sql.gz

# 2. Obnovte do databáze
psql "YOUR_DATABASE_URL" < ~/backups/leadbridge/backup_20260119_104358.sql
```

## ⚠️ Důležité poznámky

- **Railway musí být přihlášený**: Před spuštěním se ujistěte, že jste přihlášení (`railway login`)
- **Egress fees**: Stahování dat z Railway databáze může generovat malé poplatky (pár centů)
- **Bezpečnost**: Zálohy obsahují citlivá data - uchovávejte je bezpečně
- **Pravidelnost**: Doporučujeme vytvářet zálohu alespoň 1x týdně

## 🛠️ Řešení problémů

### "Permission denied"
```bash
chmod +x backup_database.sh
```

### "railway: command not found"
Nainstalujte Railway CLI:
```bash
brew install railway
railway login
```

### "pg_dump: command not found"
PostgreSQL tools jsou již nainstalovány. Pokud problém přetrvává:
```bash
brew reinstall postgresql@17
```

## 📅 Automatické zálohy (volitelné)

Pokud chcete pravidelné automatické zálohy, přidejte do cronu:

```bash
# Otevřete crontab
crontab -e

# Přidejte řádek pro týdenní zálohu (každou neděli v 2:00)
0 2 * * 0 cd ~/PycharmProjects/Lead_Bridge && ./backup_database.sh >> ~/backups/leadbridge/cron.log 2>&1
```
