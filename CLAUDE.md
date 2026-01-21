# Lead Bridge - Django CRM pro Hypoteční Poradenství

Pro detailní přehled projektu viz @PROJECT_CONTEXT.md

## Základní Info

- **Framework**: Django 5.2.8 + Python 3.12
- **Databáze**: PostgreSQL (prod), SQLite3 (dev)
- **Deployment**: Railway.app (main branch)
- **Email**: SendGrid API (custom backend v `leadbridge/sendgrid_backend.py`)

## Rychlé Příkazy

```bash
python manage.py runserver              # Dev server
python manage.py test                   # Testy
python manage.py import_users file.xlsx # Import uživatelů z Excelu
python manage.py process_scheduled_callbacks  # Zpracování callbacků (cron)
./backup_database.sh                    # Backup databáze
```

## Klíčové Soubory

- **Models**: `leads/models.py` (561 řádků), `accounts/models.py` (273 řádků)
- **Business Logic**: `leads/views.py` (2,148 řádků)
- **Notifikace**: `leads/services/notifications.py` (427 řádků)
- **Statistiky**: `leads/services/user_stats.py`
- **Email šablony**: `templates/emails/` (11 šablon)

## Business Flow

1. **Lead Creation**: Referrer vytvoří lead → přiřadí Advisorovi
2. **Meeting**: Advisor naplánuje schůzku, sleduje dokončení
3. **Deal**: Po úspěchu vytvoří Deal s výpočtem provizí
4. **Commission**: Automatické rozdělení pro referrer, manager, office

## 5 Rolí & Oprávnění

- **ADMIN**: Plný přístup + activity logs
- **ADVISOR**: Vidí přiřazené leady + osobní kontakty (`has_admin_access` vidí i podřízené)
- **REFERRER**: Vytváří leady, vidí pouze své
- **REFERRER_MANAGER**: Vidí leady svého týmu + vlastní
- **OFFICE**: Vidí všechny leady v hierarchii kanceláře

## Důležité Modely

### Lead
- `referrer` (FK User) - kdo vytvořil
- `advisor` (FK User) - přiřazený poradce
- `communication_status` - NEW, MEETING, SEARCHING_PROPERTY, WAITING_FOR_CLIENT, FAILED
- `is_personal_contact` - osobní kontakt poradce (bez provize)
- `meeting_scheduled`, `meeting_done` - tracking schůzek
- OneToOne s Deal

### Deal
- OneToOne s Lead
- `loan_amount` - výše úvěru v Kč
- `bank` - 11 podporovaných bank
- `status` - 8 stupňů (PREPARATION → DRAWN)
- Provizní fieldy: `commission_referrer`, `commission_manager`, `commission_office`
- Payment tracking: `paid_referrer`, `paid_manager`, `paid_office`

### User (Custom)
- 5 rolí: ADMIN, ADVISOR, REFERRER, REFERRER_MANAGER, OFFICE
- Provizní nastavení: `commission_total_per_million`, `commission_referrer_pct`, `commission_manager_pct`, `commission_office_pct`
- 2 modely provizí pro advisora: FULL_MINUS_STRUCTURE, NET_WITH_STRUCTURE

## Patterns & Konvence

### Access Control
- Vždy použij `get_lead_for_user_or_404(lead_id, request.user)` pro permission check
- Vždy použij `get_deal_for_user_or_404(deal_id, request.user)` pro permission check
- Všechny views musí mít `@login_required` dekorátor

### Django Signals
- `sync_lead_to_deal()` - automatická synchronizace Lead → Deal
- `sync_deal_to_lead()` - automatická synchronizace Deal → Lead
- Login/logout tracking v `leads/middleware.py`

### Notifikace
- 10+ typů emailů v `leads/services/notifications.py`
- `lead_change` notifikuje: referrer + advisor
- `deal_created` notifikuje: referrer + advisor + manager + office
- `commission_change` notifikuje: referrer + advisor + manager + office

### Optimalizace Queries
- Vždy použij `select_related()` pro ForeignKey
- Vždy použij `prefetch_related()` pro ManyToMany
- Viz příklady v `leads/views.py`

## Environment Variables

Klíčové proměnné v `.env`:
- `SECRET_KEY` - Django secret
- `DEBUG` - False v produkci
- `DATABASE_URL` - PostgreSQL connection string
- `SENDGRID_API_KEY` - SendGrid API klíč
- `DEFAULT_FROM_EMAIL` - Email odesílatele

## Deployment

- **Branch**: `dev` → merge do `master` → auto-deploy na Railway.app
- **Procfile**: Automaticky spustí migrace + collectstatic + gunicorn
- **Docs**: `DEPLOYMENT.md`, `BACKUP_HOWTO.md`, `RESTORE_HOWTO.md`

## Časté Úkoly

### Přidat nový notification typ
1. Definuj funkci v `leads/services/notifications.py`
2. Vytvoř HTML šablonu v `templates/emails/`
3. Zavolej funkci z příslušného view

### Změnit commission calculation
1. Uprav logiku v `leads/models.py` Deal model
2. Případně uprav v `leads/views.py` při vytváření dealu

### Přidat nové pole do Lead/Deal
1. Přidej field do modelu v `leads/models.py`
2. `python manage.py makemigrations`
3. Přidej do příslušného form v `leads/forms.py`
4. Uprav template v `templates/leads/`
5. Případně uprav signal v `leads/signals.py` pro sync

## Bezpečnost

- Nikdy necommituj `.env` soubor
- Používej `python-decouple` pro secrets
- HTTPS enforcement v produkci
- CSRF protection enabled
- XSS protection headers
- **Session timeout**: 8 hodin s rolling window (auto-odhlášení při nečinnosti)
- **Session expiration**: Při zavření browseru
- Dokumentace: `SECURITY_BEST_PRACTICES.md`