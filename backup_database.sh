#!/bin/bash

# ============================================
# LeadBridge Database Backup Script
# ============================================

# Nastavení
BACKUP_DIR="$HOME/backups/leadbridge"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"
PG_DUMP="/usr/local/opt/postgresql@17/bin/pg_dump"

# Vytvoření backup adresáře pokud neexistuje
mkdir -p "$BACKUP_DIR"

echo "🔄 Zahajuji zálohu databáze LeadBridge..."
echo "📅 Datum: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Získání DATABASE_PUBLIC_URL z Railway
echo "🔗 Získávám připojení k databázi..."
# Bezpečně získáme URL z Railway CLI (nikdy neukládáme heslo přímo do kódu!)
DATABASE_URL=$(railway run sh -c 'echo $DATABASE_PUBLIC_URL')

if [ -z "$DATABASE_URL" ]; then
    echo "❌ CHYBA: Nepodařilo se získat DATABASE_PUBLIC_URL z Railway"
    echo "💡 TIP: Zkontrolujte, že jste přihlášení do Railway (railway login)"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "❌ CHYBA: Nepodařilo se získat DATABASE_PUBLIC_URL z Railway"
    echo "💡 TIP: Zkontrolujte, že jste přihlášení do Railway (railway login)"
    exit 1
fi

# Vytvoření zálohy
echo "💾 Vytvářím SQL dump..."
$PG_DUMP "$DATABASE_URL" > "$BACKUP_FILE" 2>&1

if [ $? -eq 0 ]; then
    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ SQL dump vytvořen: $BACKUP_FILE ($FILE_SIZE)"

    # Komprimace zálohy
    echo "🗜️  Komprimuji zálohu..."
    gzip -f "$BACKUP_FILE"
    COMPRESSED_SIZE=$(du -h "$BACKUP_FILE.gz" | cut -f1)
    echo "✅ Komprimovaná záloha: $BACKUP_FILE.gz ($COMPRESSED_SIZE)"

    echo ""
    echo "🎉 Záloha byla úspěšně dokončena!"
    echo "📁 Umístění: $BACKUP_FILE.gz"

    # Zobrazení seznamu všech záloh
    echo ""
    echo "📋 Všechny dostupné zálohy:"
    ls -lh "$BACKUP_DIR"/*.gz 2>/dev/null | awk '{print "   " $9 " (" $5 ")"}'

    # Počet záloh
    BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/*.gz 2>/dev/null | wc -l)
    echo ""
    echo "📊 Celkem záloh: $BACKUP_COUNT"

else
    echo "❌ CHYBA: Záloha se nezdařila!"
    echo "💡 TIP: Zkontrolujte připojení k Railway a DATABASE_PUBLIC_URL"
    exit 1
fi
