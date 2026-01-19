#!/bin/bash

# ============================================
# LeadBridge Database Restore Script
# ============================================

# Barvy pro výstup
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BACKUP_DIR="$HOME/backups/leadbridge"
PSQL="/usr/local/opt/postgresql@17/bin/psql"
DATABASE_URL="postgresql://postgres:qqEdDiZRruELqKJeDtYWLMMgijoGYshM@centerbeam.proxy.rlwy.net:28808/railway"

echo "🔄 LeadBridge Database Restore"
echo "================================"
echo ""

# Kontrola, zda existuje složka se zálohami
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}❌ Složka se zálohami neexistuje: $BACKUP_DIR${NC}"
    exit 1
fi

# Zobrazení dostupných záloh
echo "📋 Dostupné zálohy:"
echo ""
BACKUPS=($(ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null))

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}❌ Žádné zálohy nebyly nalezeny v $BACKUP_DIR${NC}"
    exit 1
fi

# Zobrazení seznamu s indexy
for i in "${!BACKUPS[@]}"; do
    FILENAME=$(basename "${BACKUPS[$i]}")
    SIZE=$(du -h "${BACKUPS[$i]}" | cut -f1)
    # Extrakt datumu z názvu souboru (backup_YYYYMMDD_HHMMSS.sql.gz)
    if [[ $FILENAME =~ backup_([0-9]{8})_([0-9]{6})\.sql\.gz ]]; then
        DATE="${BASH_REMATCH[1]}"
        TIME="${BASH_REMATCH[2]}"
        FORMATTED_DATE="${DATE:0:4}-${DATE:4:2}-${DATE:6:2} ${TIME:0:2}:${TIME:2:2}:${TIME:4:2}"
        echo "  [$i] $FILENAME ($SIZE) - $FORMATTED_DATE"
    else
        echo "  [$i] $FILENAME ($SIZE)"
    fi
done

echo ""
echo -e "${YELLOW}⚠️  VAROVÁNÍ: Obnovení databáze VYMAŽE všechna současná data!${NC}"
echo -e "${YELLOW}⚠️  Před obnovením doporučujeme vytvořit novou zálohu aktuálního stavu.${NC}"
echo ""

# Výběr zálohy
read -p "Zadejte číslo zálohy, kterou chcete obnovit (nebo 'q' pro zrušení): " CHOICE

if [[ "$CHOICE" == "q" ]] || [[ "$CHOICE" == "Q" ]]; then
    echo "❌ Obnovení zrušeno."
    exit 0
fi

# Kontrola, zda je volba validní
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -ge "${#BACKUPS[@]}" ]; then
    echo -e "${RED}❌ Neplatná volba.${NC}"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$CHOICE]}"
echo ""
echo "✅ Vybrána záloha: $(basename "$SELECTED_BACKUP")"
echo ""

# Poslední potvrzení
read -p "🔴 Opravdu chcete VYMAZAT všechna data a obnovit tuto zálohu? (ano/ne): " CONFIRM

if [[ "$CONFIRM" != "ano" ]]; then
    echo "❌ Obnovení zrušeno."
    exit 0
fi

echo ""
echo "🔄 Zahajuji obnovení databáze..."
echo ""

# Vytvoření zálohy před obnovením
echo "1️⃣  Vytvářím zálohu současného stavu (pro jistotu)..."
SAFETY_BACKUP="$BACKUP_DIR/before_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
/usr/local/opt/postgresql@17/bin/pg_dump "$DATABASE_URL" | gzip > "$SAFETY_BACKUP" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}   ✅ Bezpečnostní záloha vytvořena: $(basename "$SAFETY_BACKUP")${NC}"
else
    echo -e "${YELLOW}   ⚠️  Nepodařilo se vytvořit bezpečnostní zálohu (pokračuji)${NC}"
fi
echo ""

# Rozbalení vybrané zálohy
echo "2️⃣  Rozbaluji zálohu..."
TEMP_SQL="/tmp/leadbridge_restore_$(date +%s).sql"
gunzip -c "$SELECTED_BACKUP" > "$TEMP_SQL"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Chyba při rozbalování zálohy${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ Záloha rozbalena${NC}"
echo ""

# Vyčištění databáze
echo "3️⃣  Mažu současná data..."
$PSQL "$DATABASE_URL" -c "
DO \$\$ DECLARE
    r RECORD;
BEGIN
    -- Vypnutí foreign key constraints
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END \$\$;
" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}   ✅ Data vymazána${NC}"
else
    echo -e "${YELLOW}   ⚠️  Problém s mazáním dat (pokračuji)${NC}"
fi
echo ""

# Import zálohy
echo "4️⃣  Importuji data ze zálohy..."
$PSQL "$DATABASE_URL" < "$TEMP_SQL" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}   ✅ Data importována${NC}"
else
    echo -e "${RED}   ❌ Chyba při importu dat${NC}"
    echo ""
    echo "💡 Pokud chcete obnovit bezpečnostní zálohu, spusťte:"
    echo "   gunzip -c $SAFETY_BACKUP | psql \"$DATABASE_URL\""
    rm "$TEMP_SQL"
    exit 1
fi
echo ""

# Úklid
rm "$TEMP_SQL"

# Ověření
echo "5️⃣  Ověřuji obnovení..."
TABLE_COUNT=$($PSQL "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | xargs)

if [ -n "$TABLE_COUNT" ] && [ "$TABLE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}   ✅ Databáze obsahuje $TABLE_COUNT tabulek${NC}"
else
    echo -e "${YELLOW}   ⚠️  Varování: Databáze může být prázdná${NC}"
fi

echo ""
echo "🎉 Obnovení dokončeno!"
echo ""
echo "📋 Důležité další kroky:"
echo "   1. Zkontrolujte web: https://www.leadbridge.cz"
echo "   2. Přihlašte se a ověřte, že data jsou správná"
echo "   3. Pokud je něco špatně, máte bezpečnostní zálohu:"
echo "      $SAFETY_BACKUP"
echo ""
