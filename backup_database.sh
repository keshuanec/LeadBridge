#!/bin/bash

# ============================================
# LeadBridge Database Backup Script
# ============================================
#
# Použití:
#   ./backup_database.sh                          # Zkusí získat URL z Railway
#   ./backup_database.sh "postgresql://..."       # Použije předanou URL
#

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

# Získání DATABASE_URL
echo "🔗 Získávám připojení k databázi..."

# 1. Zkusit parametr příkazové řádky
if [ -n "$1" ]; then
    DATABASE_URL="$1"
    echo "   ✓ Použita URL z parametru"
# 2. Zkusit Railway CLI
elif command -v railway &> /dev/null; then
    DATABASE_URL=$(railway variables --json 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('DATABASE_PUBLIC_URL', ''))" 2>/dev/null)
    if [ -n "$DATABASE_URL" ]; then
        echo "   ✓ Použita URL z Railway CLI"
    fi
fi

# Kontrola, zda máme URL
if [ -z "$DATABASE_URL" ]; then
    echo "❌ CHYBA: Nepodařilo se získat DATABASE_URL"
    echo ""
    echo "💡 Řešení:"
    echo "   1. Předejte URL jako parametr:"
    echo "      ./backup_database.sh \"postgresql://user:pass@host:port/db\""
    echo ""
    echo "   2. Nebo přidejte DATABASE_PUBLIC_URL do Railway Variables"
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
