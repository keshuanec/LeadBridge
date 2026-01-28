# Project Context: Lead Bridge

> Tento dokument slouží jako referenční zdroj pro Claude Code a vývojáře, aby snížil náklady na opětovné prozkoumávání celého codebase.

## Účel Projektu

**Lead Bridge** je CRM systém pro správu leadů a provizí v oblasti hypotečního poradenství. Systém spojuje realitní makléře (referrers) s hypotečními poradci (advisors) a automatizuje celý proces od prvního kontaktu až po vypořádání provizí.

### Hlavní Byznys Flow
1. Realitní makléř (Referrer) vytvoří lead a přiřadí ho hypotečnímu poradci
2. Poradce naplánuje schůzku s klientem, komunikuje a zpracovává hypotéku
3. Po úspěšném uzavření se vytvoří Deal s detaily úvěru
4. Systém automaticky vypočítá a rozdělí provize mezi makléře, manažera a kancelář
5. Automatické notifikace drží všechny strany informované o průběhu

## Technologický Stack

### Backend
- **Django 5.2.8** - Web framework
- **Python 3.12** - Programovací jazyk
- **PostgreSQL** - Produkční databáze (Railway.app)
- **SQLite3** - Vývojová databáze (lokálně)

### Email & Notifikace
- **SendGrid API** - Primární email backend (custom implementace v `leadbridge/sendgrid_backend.py`)
- SMTP fallback (Gmail) - Záložní řešení
- 11 HTML email šablon v `templates/emails/`

### Deployment & Infrastructure
- **Gunicorn** - WSGI server
- **WhiteNoise** - Static file serving s kompresí
- **Railway.app** - Doporučená produkční platforma
- **python-decouple** - Správa environment variables

### Utilities
- **Pillow** - Image handling
- **openpyxl** - Excel import uživatelů

## Architektura Projektu

```
Lead_Bridge/
├── leadbridge/              # Django project config
│   ├── settings.py          # Environment-based nastavení
│   ├── urls.py              # Hlavní URL routing
│   └── sendgrid_backend.py  # Custom email backend
│
├── accounts/                # User management
│   ├── models.py            # User, ReferrerProfile, Office, ManagerProfile
│   └── management/commands/
│       └── import_users.py  # Excel import uživatelů
│
├── leads/                   # Core business logic
│   ├── models.py            # Lead, Deal, LeadNote, LeadHistory, ActivityLog
│   ├── views.py             # 1,361 řádků - hlavní business logika
│   ├── forms.py             # 8+ Django forms s dynamickou logikou
│   ├── signals.py           # Auto-sync Lead ↔ Deal
│   ├── middleware.py        # Login/logout tracking
│   ├── services/
│   │   ├── access_control.py  # Role-based access control
│   │   ├── user_stats.py      # Výpočty statistik
│   │   ├── filters.py         # Filtrování, řazení a post-processing (vč. note filtering)
│   │   ├── model_helpers.py   # Helper pro procházení modelových vztahů
│   │   ├── events.py          # Zaznamenávání událostí (historie + notifikace)
│   │   └── notifications.py   # Email notification systém (427 řádků)
│   └── management/commands/
│       └── process_scheduled_callbacks.py  # Cron job pro zpracování callbacků
│
└── templates/               # 36 HTML šablon
    ├── leads/               # 21 šablon pro leads/deals
    └── emails/              # 11 email notifikací
```

## Datový Model

### User (accounts.User)
Custom User model s rozšířenými poli:
- **5 rolí**: ADMIN, ADVISOR, REFERRER, REFERRER_MANAGER, OFFICE
- **Provizní nastavení**:
  - `commission_total_per_million` - Základní provize za 1M Kč úvěru
  - `commission_referrer_pct` - Procento pro makléře
  - `commission_manager_pct` - Procento pro manažera
  - `commission_office_pct` - Procento pro kancelář
- **Speciální pole**:
  - `has_admin_access` - Poradci s admin přístupem vidí všechny podřízené leady
  - `phone` - Kontaktní telefon

### Lead (leads.Lead)
Primární business entita pro správu kontaktů:
- **Vztahy**:
  - `referrer` (FK) - Makléř, který lead vytvořil
  - `advisor` (FK) - Přiřazený hypoteční poradce
  - OneToOne s Deal (po úspěšné konverzi)
- **Klíčová pole**:
  - `client_first_name` - Křestní jméno klienta (volitelné, blank=True)
  - `client_last_name` - Příjmení klienta (povinné)
  - `client_name` - Property vrací "Příjmení Křestní" nebo jen příjmení
  - `client_phone`, `client_email` - Kontaktní údaje
  - `communication_status` - Lifecycle stav leadu
  - `meeting_scheduled`, `meeting_done` - Tracking schůzek
  - `callback_scheduled_date` - Datum pro follow-up
  - `is_personal_contact` - Osobní kontakt poradce (bez provize)
- **Communication statuses**: NEW, MEETING, SEARCHING_PROPERTY, WAITING_FOR_CLIENT, FAILED, DEAL_CREATED, COMMISSION_PAID

### Deal (leads.Deal)
Detaily hypotéky a provize:
- OneToOne vztah s Lead
- **Klíčová pole**:
  - `client_first_name`, `client_last_name` - Kopie jména z Lead (synchronizace přes signály)
  - `client_name` - Property vrací "Příjmení Křestní" nebo jen příjmení
  - `client_phone`, `client_email` - Kontaktní údaje
  - `loan_amount` - Výše úvěru v Kč
  - `bank` - 11 podporovaných bank
  - `property_type` - OWN vs OTHER
  - `status` - 8 stupňů procesu dealu
  - Vypočítané provize pro každou stranu
  - Payment tracking flags (`paid_referrer`, `paid_manager`, `paid_office`)
- **Provizní modely**:
  1. FULL_MINUS_STRUCTURE - Plná provize minus náklady struktury
  2. NET_WITH_STRUCTURE - Čistá provize (struktura se platí zvlášť)

### Podpůrné Modely
- **ReferrerProfile** - Propojuje makléře s manažery a poradci
- **Office** - Entity realitních kanceláří
- **ManagerProfile** - Propojuje manažery s kancelářemi
- **LeadNote** - Poznámky k leadům s podporou soukromých poznámek
  - `lead` (FK) - vztah k leadu
  - `author` (FK) - autor poznámky
  - `text` - text poznámky
  - `is_private` - soukromá poznámka
  - **Oprávnění zobrazení**:
    - Veřejné poznámky (`is_private=False`) - vidí všichni s přístupem k leadu
    - Soukromé poznámky (`is_private=True`) - vidí pouze autor a admin/superuser
    - Filtrování v seznamech zajištěno přes `ListFilterService.process_leads_for_template()` a `process_deals_for_template()`
  - **Vizuální označení**: Soukromé poznámky mají žluté pozadí (#FFF9E6), oranžový border (#F39C12) a ikonu 🔒
- **LeadHistory** - Audit trail všech změn leadů
- **ActivityLog** - Systémový log všech aktivit (login, CRUD operace) s IP adresami

## Klíčové Funkcionality

### Role-Based Access Control (RBAC)

**1. REFERRER (Realitní makléř)**
- Vytváří leady a přiřazuje je dostupným poradcům
- Vidí pouze své vlastní leady
- Může označit schůzku jako dokončenou
- Dostává notifikace o svých leadech

**2. ADVISOR (Hypoteční poradce)**
- Vidí leady přiřazené jemu
- Plánuje schůzky, vytváří dealy
- S `has_admin_access=True`: vidí leady podřízených referrerů
- Spravuje osobní kontakty (bez dělení provize)

**3. REFERRER_MANAGER**
- Vidí všechny leady od řízených referrerů + vlastní referrer leady
- Nevidí osobní kontakty poradců
- Dostává provizi z dealů svého týmu

**4. OFFICE (Vlastník kanceláře)**
- Vidí všechny leady v hierarchii své kanceláře
- Nevidí osobní kontakty poradců
- Dostává procento provize z kanceláře

**5. ADMIN/Superuser**
- Plný přístup do systému
- Vidí activity logs
- Spravuje všechny uživatele a data

### Notifikační Systém

**10+ typů automatických emailů:**
1. `notify_lead_created()` - Nový lead
2. `notify_lead_updated()` - Změny v leadu
3. `notify_note_added()` - Přidána poznámka
4. `notify_meeting_scheduled()` - Naplánována schůzka
5. `notify_meeting_completed()` - Schůzka dokončena
6. `notify_deal_created()` - Vytvořen deal (notifikuje makléře + poradce + manažera + kancelář)
7. `notify_deal_updated()` - Změny v dealu
8. `notify_commission_ready()` - Provize připravena k výplatě
9. `notify_commission_paid()` - Provize vyplacena
10. `notify_callback_due()` - Připomínka scheduled callbacku

**Logika příjemců:**
- `lead_change` události: makléř + poradce
- `deal_created` události: makléř + poradce + manažer + kancelář
- `commission_change` události: makléř + poradce + manažer + kancelář
- Vylučuje uživatele, který akci provedl

### Statistiky & Dashboard

**Služba statistik** (`leads/services/user_stats.py`):
- `stats_referrer_personal()` - Statistiky makléře
- `stats_advisor()` - Statistiky poradce
- `stats_manager()` - Statistiky manažera (osobní + tým)
- `stats_office_user()` - Statistiky kanceláře (osobní + tým)

**Metriky:**
- Celkový počet kontaktů
- Naplánované schůzky
- Dokončené schůzky
- Vytvořené dealy
- Úspěšné dealy (status=DRAWN)

**Filtrování dat:**
- Vše, Tento rok, Tento měsíc, Vlastní rozsah

**Důležité výjimky:**
- **Vlastní kontakty** (`is_personal_contact=True`) se **nezahrnují** do běžných statistik jako doporučitel
- Vlastní kontakty se zobrazují **pouze** v dedikovaných položkách u poradců:
  - "Založené obchody (vlastní)" (`deals_created_personal`)
  - "Dokončené obchody (vlastní)" (`deals_completed_personal`)
- Implementováno pomocí `.exclude(is_personal_contact=True)` ve všech quersetech pro referrer statistiky
- Platí pro všechny views: `advisor_detail()`, `user_detail()` a statistické funkce v `user_stats.py`

### Session Management

**Automatické odhlášení pro ochranu citlivých dat:**

- **Rolling window timeout**: 8 hodin od poslední aktivity
- **Browser close**: Session končí při zavření prohlížeče
- **Session refresh**: Každá aktivita prodlužuje timeout
- **Konfigurace**: `settings.py` řádky 148-157

**Nastavení:**
- `SESSION_COOKIE_AGE = 28800` (8 hodin)
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`
- `SESSION_SAVE_EVERY_REQUEST = True` (rolling window)

**Důvody implementace:**
- Ochrana citlivých finančních dat klientů
- GDPR compliance pro osobní údaje
- Bezpečnostní audit pro CRM systém
- Prevence neoprávněného přístupu na opuštěných zařízeních

### Django Signals

**Pre-save signály:**
- Sledují staré hodnoty pro detekci změn (Lead, Deal)

**Post-save signály:**
1. `sync_lead_to_deal()` - Synchronizuje změny z Lead do Deal
2. `sync_deal_to_lead()` - Synchronizuje změny z Deal do Lead
3. `log_lead_note_created()` - Loguje vytvoření poznámky

**Middleware signály:**
- Login/logout tracking přes `leads/middleware.py`
- IP adresa se loguje pro bezpečnostní audit

## Management Commands

### 1. Import Uživatelů z Excelu
```bash
python manage.py import_users path/to/file.xlsx [--dry-run]
```
- Importuje User + ReferrerProfile
- Propojuje makléře s manažery
- Podpora dry-run režimu
- Soubor: `accounts/management/commands/import_users.py` (329 řádků)

### 2. Zpracování Scheduled Callbacků
```bash
python manage.py process_scheduled_callbacks
```
- Zpracovává zpožděné callbacky
- Vrací leady do stavu NEW
- Posílá email notifikace poradcům
- **Doporučeno jako cron job**: každý den v 8:00
- Soubor: `leads/management/commands/process_scheduled_callbacks.py`

### 3. Fix Meeting Stats (One-time)
```bash
python manage.py fix_meeting_stats
```
- Jednorázová migrace dat
- Opravuje `meeting_scheduled` flagy pro historická data
- Soubor: `leads/management/commands/fix_meeting_stats.py`

## Důležité URL Endpointy

### Autentizace
- `/accounts/login/` - Login
- `/accounts/logout/` - Logout
- `/account/settings/` - Profil uživatele
- `/account/settings/password/` - Změna hesla

### Správa Leadů
- `GET /leads/` - Seznam leadů (filtrováno podle role)
- `GET /leads/new/` - Vytvoření nového leadu
- `GET /leads/<id>/` - Detail leadu
- `POST /leads/<id>/edit/` - Editace leadu
- `POST /leads/<id>/meeting/` - Naplánování schůzky
- `POST /leads/<id>/meeting/completed/` - Označení schůzky jako dokončené
- `POST /leads/<id>/callback/` - Naplánování callbacku

### Správa Dealů
- `GET /leads/deals/` - Seznam dealů
- `GET /leads/deals/<id>/` - Detail dealu
- `POST /leads/<id>/deal/new/` - Vytvoření dealu z leadu
- `POST /leads/deals/<id>/edit/` - Editace dealu
- `POST /leads/deals/<id>/commission/ready/` - Označení provize jako připravené
- `POST /leads/deals/<id>/commission/paid/<part>/` - Označení provize jako vyplacené

### Dashboard & Stats
- `GET /overview/` - Dashboard se statistikami a nadcházejícími schůzkami

### Uživatelé
- `GET /leads/referrers/` - Seznam makléřů
- `GET /leads/advisors/` - Seznam poradců se statistikami
- `GET /leads/advisors/<id>/` - Detail poradce

### Admin
- `GET /leads/activities/` - Activity log (pouze superuser)

## Backup & Restore

### Backup Databáze
```bash
./backup_database.sh
```
- Vytváří timestampovaný backup SQLite/PostgreSQL
- Dokumentace: `BACKUP_HOWTO.md`

### Restore Databáze
```bash
./restore_database.sh path/to/backup.sql
```
- Obnovuje databázi z backup souboru
- Dokumentace: `RESTORE_HOWTO.md`

## Environment Variables

Klíčové proměnné v `.env`:
- `SECRET_KEY` - Django secret key
- `DEBUG` - Debug mód (False v produkci)
- `DATABASE_URL` - PostgreSQL connection string (produkce)
- `SENDGRID_API_KEY` - SendGrid API klíč
- `DEFAULT_FROM_EMAIL` - Email odesílatele
- `ALLOWED_HOSTS` - Povolené domény

Šablona: `.env.example`

## Deployment

### Produkční Konfigurace
- Platforma: **Railway.app** (doporučeno)
- Dokumentace: `DEPLOYMENT.md`
- Procfile zahrnuje:
  - Migrace databáze
  - Collect static files
  - Spuštění Gunicorn serveru

### Bezpečnostní Nastavení
- SSL/HTTPS enforcement
- Secure cookies (CSRF, Session)
- XSS protection headers
- HSTS enabled
- Dokumentace: `SECURITY_BEST_PRACTICES.md`

## Lokalizace

- **Jazyk**: Čeština (cs)
- **Časové pásmo**: Europe/Prague
- **Formáty datumů**: Lokalizované pro CZ

## Databázové Migrace

- **accounts app**: 21 migrací
- **leads app**: 19 migrací (poslední 3: split client_name → client_first_name + client_last_name)
- **Celkem**: 40 schema changes

## Code Statistics

- **Python soubory**: 67
- **HTML šablony**: 36
- **Hlavní soubory**:
  - `leads/views.py`: 1,361 řádků (refaktorováno z původních 2,170)
  - `leads/models.py`: 561 řádků
  - `leads/services/notifications.py`: 427 řádků
  - `accounts/models.py`: 273 řádků

## Návrhové Vzory

1. **Service Layer Pattern** - Business logika v `/services/` adresářích
2. **Signal-based Data Sync** - Automatická synchronizace Lead ↔ Deal (včetně client_first_name a client_last_name)
3. **Role-based Query Filtering** - Konzistentní permission checking
4. **Form Customization** - Dynamická pole podle role uživatele
5. **Environment-based Configuration** - Různé nastavení pro dev/prod
6. **Personal Contacts Exclusion** - Vlastní kontakty poradce se vyloučají z referrer statistik pomocí `.exclude(is_personal_contact=True)`
7. **Collapsible UI Components** - Kolapsibilní filtry a toggleable sloupce pro optimalizaci prostoru
8. **Client Name Pattern** - Jméno rozděleno na `client_first_name` (volitelné) a `client_last_name` (povinné), property `client_name` vrací "Příjmení Křestní" nebo jen příjmení pro zpětnou kompatibilitu
9. **Privacy-Aware Note Filtering** - Automatické filtrování poznámek podle oprávnění uživatele v seznamových views (pouze veřejné + vlastní soukromé poznámky)

## UI Komponenty & Mobilní Zobrazení

### List Views (Leady a Dealy)
- **Kolapsibilní filtry**: Filtry se defaultně skrývají, rozbalí se tlačítkem "Zobrazit filtry"
  - Animace při rozbalení/sbalení
  - Tlačítka "Filtrovat" a "Zrušit filtry" se zobrazí pouze při rozbalených filtrech
- **Toggleable poznámky**: Sloupec s posledními poznámkami
  - Skrytý defaultně pro úsporu prostoru
  - Zobrazí/skryje se tlačítkem "Zobrazit poznámky"
  - Smooth CSS animace při přechodu
  - Text limitován na 2 řádky s ellipsis
  - **Automatické filtrování podle oprávnění**: Zobrazují se pouze poznámky, které má uživatel právo vidět
    - Veřejné poznámky - vidí všichni
    - Soukromé poznámky - vidí pouze autor a admin
  - **Vizuální označení soukromých poznámek**:
    - Žluté pozadí (#FFF9E6)
    - Oranžový levý border (3px, #F39C12)
    - Ikona zámku 🔒 před textem
    - Stejný styl jako v detailu leadu/dealu

### Mobilní Optimalizace
- **Fixované šířky sloupců** pro prevenci prolínání na malých displejích:
  - `.client-col` - 90px (jméno klienta)
  - `.person-col` - 70px (Doporučitel, Poradce, Manažer, Kancelář)
  - `.status-col` - 85px (statusy)
  - `.date-col` - 85px (data)
  - `.note-col` - 400px při zobrazení, 0px při skrytí (s CSS transition)
  - `.commission-col` - 70px (provize v deals listu)
  - `.loan-col` - 90px (výše úvěru)
- **Tabulka nastavení**:
  - `table-layout: fixed` - pevné rozložení
  - `overflow-x: auto` - horizontální scroll na mobilech
  - `white-space: normal` - zalamování textu v buňkách
- **Kompaktní typography**: Menší font-size (12-13px) a line-height (1.3) pro efektivní využití prostoru

## Často Používané Helper Funkce

- `get_lead_for_user_or_404()` - Role-based přístup k leadům
- `get_deal_for_user_or_404()` - Role-based přístup k dealům
- Komplexní query filtry podle role uživatele

## Podporované Banky (11)

Uvedeno v `leads/models.py` Deal model:
- Česká spořitelna, ČSOB, Komerční banka, Moneta, Raiffeisen, UniCredit, Air Bank, Hypoteční banka, Fio banka, mBank, Equa Bank

## Property Types

- **OWN** - Vlastní nemovitost
- **OTHER** - Cizí nemovitost

## Deal Status Flow (8 stupňů)

1. PREPARATION - Příprava podkladů
2. SENT_TO_BANK - Odesláno do banky
3. SENT_TO_RU - Odesláno k realitní úvěrové expertize
4. APPROVED - Schváleno
5. SIGNING - Podepisování
6. DRAWN - Čerpáno (úspěšný deal)
7. CANCELLED - Zrušeno
8. REJECTED - Zamítnuto

## Poznámky pro Další Vývoj

- Všechny views vyžadují `@login_required`
- Role-based access control je implementován v každém view
- Queries jsou optimalizovány s `select_related`/`prefetch_related`
- Email notifikace běží synchronně (zvážit async task queue pro škálování)
- Scheduled callbacks vyžadují cron job setup v produkci
- Import uživatelů podporuje Excel formát s definovanými sloupci

---

**Poslední aktualizace**: 2026-01-28
**Django verze**: 5.2.8
**Python verze**: 3.12