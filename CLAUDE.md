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
- **Views**: `leads/views.py` (1,361 řádků, z původních 2,170)
- **Service Layer**: `leads/services/` (6 služeb)
  - `access_control.py` - Role-based access control
  - `user_stats.py` - Statistiky uživatelů
  - `filters.py` - Filtrování a řazení list views
  - `model_helpers.py` - Helper pro procházení modelových vztahů
  - `events.py` - Zaznamenávání událostí (historie + notifikace)
  - `notifications.py` - Email notifikace (427 řádků)
- **Email šablony**: `templates/emails/` (11 šablon)
- **List Templates**: `templates/leads/my_leads.html`, `templates/leads/deals_list.html`
  - Kolapsibilní filtry s animacemi
  - Toggleable note column pro poznámky
  - Fixované šířky sloupců pro mobilní zobrazení

## Business Flow

1. **Lead Creation**: Referrer vytvoří lead → přiřadí Advisorovi
2. **Meeting**: Advisor naplánuje schůzku, sleduje dokončení
3. **Deal**: Po úspěchu vytvoří Deal s výpočtem provizí
4. **Commission**: Automatické rozdělení pro referrer, manager, office

## 5 Rolí & Oprávnění

- **ADMIN**: Plný přístup + activity logs, vidí všechny dealy včetně personal deals
- **ADVISOR**: Vidí přiřazené leady + osobní kontakty + všechny dealy (včetně personal deals); `has_admin_access` vidí i podřízené
- **REFERRER**: Vytváří leady, vidí pouze své; **nevidí** personal deals
- **REFERRER_MANAGER**: Vidí leady svého týmu + vlastní; **nevidí** osobní kontakty ani personal deals
- **OFFICE**: Vidí všechny leady v hierarchii kanceláře; **nevidí** osobní kontakty ani personal deals

## Důležité Modely

### Lead
- `client_first_name` (CharField, blank=True) - křestní jméno klienta (volitelné)
- `client_last_name` (CharField, required) - příjmení klienta (povinné)
- `client_name` (property) - vrací "Příjmení Křestní" nebo jen příjmení
- `referrer` (FK User) - kdo vytvořil
- `advisor` (FK User) - přiřazený poradce
- `communication_status` - NEW, MEETING, SEARCHING_PROPERTY, WAITING_FOR_CLIENT, FAILED
- `is_personal_contact` - osobní kontakt poradce (bez provize)
- `meeting_scheduled`, `meeting_done` - tracking schůzek
- OneToMany s Deal (jeden lead může mít více dealů)

### LeadNote
- `lead` (FK Lead) - vztah k leadu
- `author` (FK User) - autor poznámky
- `text` (TextField) - text poznámky
- `is_private` (BooleanField) - soukromá poznámka
- **Oprávnění pro zobrazení**:
  - Veřejné poznámky (`is_private=False`) - vidí všichni s přístupem k leadu
  - Soukromé poznámky (`is_private=True`) - vidí pouze autor a admin
  - V seznamech leadů/dealů se filtrují automaticky přes `ListFilterService`

### Deal
- OneToMany vztah s Lead (jeden lead může mít více dealů)
- `client_first_name`, `client_last_name` - kopie jména z Lead (synchronizace přes signály)
- `client_name` (property) - vrací "Příjmení Křestní" nebo jen příjmení
- `loan_amount` - výše úvěru v Kč
- `bank` - 11 podporovaných bank a stavebních spořitelen
- `status` - 9 stupňů (REQUEST_IN_BANK → DRAWN)
- `is_personal_deal` - vlastní obchod poradce (bez provize pro strukturu)
- Provizní fieldy: `commission_referrer`, `commission_manager`, `commission_office`
- Payment tracking: `paid_referrer`, `paid_manager`, `paid_office`
- **Viditelnost**: Personal deals vidí pouze advisors a admins

### User (Custom)
- 5 rolí: ADMIN, ADVISOR, REFERRER, REFERRER_MANAGER, OFFICE
- Provizní nastavení: `commission_total_per_million`, `commission_referrer_pct`, `commission_manager_pct`, `commission_office_pct`
- 2 modely provizí pro advisora: FULL_MINUS_STRUCTURE, NET_WITH_STRUCTURE

## Patterns & Konvence

### Service Layer Pattern

Business logika je organizována do service vrstvy v `leads/services/`:

**1. LeadAccessService** - Centralizované řízení přístupu
```python
from leads.services import LeadAccessService

# Získání filtrovaného querysetu podle role
leads_qs = LeadAccessService.get_leads_queryset(user)
deals_qs = LeadAccessService.get_deals_queryset(user)

# Kontrola oprávnění
can_edit = LeadAccessService.can_edit_lead(user, lead)
```

**2. UserStatsService** - Statistiky pro všechny role
```python
from leads.services import UserStatsService

# Detailní statistiky poradce
advisor_stats = UserStatsService.get_advisor_stats_detailed(advisor, date_from, date_to)

# Převod dataclass na dictionary pro template
stats_dict = UserStatsService.advisor_stats_to_dict(advisor_stats)

# Team a office statistiky
team_stats = UserStatsService.get_team_stats(manager, date_from, date_to)
office_stats = UserStatsService.get_office_stats(office_owner, date_from, date_to)
```

**Důležité poznámky k statistikám:**
- `deals_created`, `deals_completed`: Počítají se **unique leady** s alespoň jedním dealem (ne celkový počet dealů)
- Personal contacts (`is_personal_contact=True`) a personal deals (`is_personal_deal=True`) se **vyloučují** ze standardních statistik
- Personal statistiky se zobrazují v dedikovaných položkách: `deals_created_personal`, `deals_completed_personal`

**3. ListFilterService** - Filtrování a řazení
```python
from leads.services import ListFilterService

# Inicializace
filter_service = ListFilterService(user, request, context='leads')

# Použití
filter_params = filter_service.get_filter_params()
allowed = filter_service.get_allowed_filters()
queryset = filter_service.apply_filters(queryset, allowed, filter_params)
queryset, sort, direction = filter_service.apply_sorting(queryset)

# Post-processing pro šablony (přidává last_note_text a last_note_is_private)
leads = filter_service.process_leads_for_template(leads_qs)
deals = filter_service.process_deals_for_template(deals_qs)
```

**Filtrování poznámek podle oprávnění:**
- `process_leads_for_template()` a `process_deals_for_template()` automaticky filtrují poznámky
- Uživatel vidí pouze veřejné poznámky + své vlastní soukromé poznámky
- Admin vidí všechny poznámky

**4. LeadHierarchyHelper** - Procházení hierarchie referrer → manager → office
```python
from leads.services import LeadHierarchyHelper

# Inicializace s Lead nebo User objektem
helper = LeadHierarchyHelper(lead)

# Bezpečné získání manažera a kanceláře
manager = helper.get_manager()
office = helper.get_office()
hierarchy = helper.get_hierarchy_dict()
```

**5. LeadEventService** - Události s historií a notifikacemi
```python
from leads.services import LeadEventService

# Vytvoření leadu
LeadEventService.record_lead_created(lead, user)

# Aktualizace leadu
LeadEventService.record_lead_updated(lead, user, changes_description, status_changed=True)

# Schůzky
LeadEventService.record_meeting_scheduled(lead, user, meeting_datetime, meeting_note)
LeadEventService.record_meeting_completed(lead, user, next_action_label, result_note)

# Obchody a provize
LeadEventService.record_deal_created(deal, lead, user)
LeadEventService.record_commission_paid(deal, user, recipient_type, changes, all_paid)
```

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

### UI Komponenty & Mobilní Zobrazení
- **Kolapsibilní filtry**: Filtry se defaultně skrývají, rozbalí se tlačítkem "Zobrazit filtry"
- **Toggleable poznámky**: Sloupec poznámek se zobrazí/skryje tlačítkem "Zobrazit poznámky"
  - Zobrazuje pouze poznámky, které má uživatel právo vidět (veřejné + vlastní soukromé)
  - Soukromé poznámky jsou označeny žlutým pozadím (#FFF9E6), oranžovým borderem (#F39C12) a ikonou 🔒
- **Fixované šířky sloupců**:
  - `.client-col` - 90px pro jméno klienta
  - `.person-col` - 70px pro jména osob (Doporučitel, Poradce, Manažer, Kancelář)
  - `.status-col` - 85px pro statusy
  - `.date-col` - 85px pro data
  - `.note-col` - 400px při zobrazení, 0px při skrytí (s animací)
- **Mobilní optimalizace**: Tabulky používají `overflow-x: auto` a `table-layout: fixed` pro scroll na mobilech

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