# Lead-Deal Refactoring Summary (OneToOne → OneToMany)

**Date**: 2026-01-28
**Status**: ✅ COMPLETED

## Overview

Successfully refactored the Lead-Deal relationship from OneToOne (1:1) to OneToMany (1:N), allowing one Lead to have multiple Deals. This enables tracking multiple mortgages/loans for the same client.

## Changes Implemented

### 1. Database Migrations (4-step process)

✅ **Migration 0017**: Added `lead_fk` (ForeignKey) and `is_personal_deal` fields
✅ **Migration 0018**: Data migration - copied OneToOne → ForeignKey
✅ **Migration 0019**: Removed old `lead` (OneToOne) field
✅ **Migration 0020**: Renamed `lead_fk` → `lead`, set NOT NULL

**Rollback**: `python manage.py migrate leads 0016`

### 2. Model Changes

**File**: `leads/models.py`

#### Lead Model (lines 107-118)
- Added `get_latest_deal()` - returns newest deal or None
- Added `has_any_deal()` - checks if lead has any deals
- Added `deal_count` property - returns number of deals

#### Deal Model (lines 251-256, 280-285)
- Changed `lead` from OneToOneField → ForeignKey
- Changed `related_name` from "deal" → "deals"
- Added `is_personal_deal` BooleanField (line 281-285)

### 3. Signal Changes

**File**: `leads/signals.py` (lines 97-108)

Updated `sync_lead_to_deal()` to sync Lead changes into **ALL Deals** (not just one):
```python
deals = instance.deals.all()
if not deals.exists():
    return
deals.update(...)  # Bulk update all deals
```

### 4. View Changes

**File**: `leads/views.py`

#### deal_create_from_lead() (lines 912-915)
- **Removed**: Check for existing deal (`hasattr(lead, "deal")`)
- **New behavior**: Always allow creating additional deals

#### Business Logic
- Creating ANY deal → Lead status = DEAL_CREATED (even if other deals exist)
- Paying commission on ANY deal → Lead status = COMMISSION_PAID (even if other deals unpaid)

### 5. Form Changes

**File**: `leads/forms.py`

#### DealCreateForm (lines 323-406)
- Added `is_personal_deal` to fields list (line 326)
- Added checkbox logic in `__init__()` (lines 354-406):
  - **First deal** (from structure): checkbox HIDDEN, auto-set to False (provizovaný)
  - **Second+ deal** (from structure): checkbox VISIBLE, user can choose
  - **Personal contact leads**: checkbox HIDDEN, auto-set to True (vlastní)
  - Shows message if lead has existing deals
- Cannot edit `is_personal_deal` after creation (disabled in edit mode)

#### DealEditForm (lines 408-450)
- Added `is_personal_deal` to fields (line 420)
- Added `__init__()` to disable editing (lines 439-447)

### 6. Service Changes

#### access_control.py (lines 137-148)
Updated `get_deals_queryset()` for REFERRER_MANAGER and OFFICE:
```python
.exclude(Q(lead__is_personal_contact=True) | Q(is_personal_deal=True))
```

**Access rules**:
- REFERRER: Sees ALL their deals (including `is_personal_deal=True`)
- ADVISOR: Sees ALL assigned deals (including `is_personal_deal=True`)
- REFERRER_MANAGER: Does NOT see `is_personal_deal=True`
- OFFICE: Does NOT see `is_personal_deal=True`

#### user_stats.py (multiple lines)
Updated `_lead_stats()` (line 284):
- Added `exclude_personal_deals` parameter
- When True, excludes `is_personal_deal=True` from counts

Updated all structure stats functions:
- `stats_referrer_personal()` (line 480)
- `stats_manager()` (lines 512-513)
- `stats_office_user()` (lines 548-549)
- `get_team_stats()` (line 186)
- `get_office_stats()` (line 220)
- `get_referrer_stats_detailed()` (line 448)

**Important**: Advisor stats INCLUDE personal deals (they're the advisor's work).

### 7. Template Changes

#### lead_detail.html (lines 94-157)
- **Button**: "Založit obchod" vs "Založit další obchod" (conditional)
- **New section**: Table showing all deals (lines 104-157)
  - Columns: Typ, Datum, Banka, Výše úvěru, Stav, Provize, Akce
  - Visual indicators: 👤 Vlastní (blue) vs 💼 Provizovaný (green)
  - Light blue background for personal deals

#### deal_detail.html (lines 10-47)
- **New field**: "Typ obchodu" badge (lines 11-20)
- **New section**: Info box listing other deals (lines 23-45)
  - Shows "Tento klient má celkem X obchod(y)"
  - Links to other deals with bank, amount, status

#### deal_form.html (lines 11-19)
- **New alert**: Shows if lead already has deals
  - "Tento klient již má X obchod(y). Vytváříte další obchod pro stejného klienta."

#### deals_list.html (lines 284, 377-382)
- **New column**: "Typ" (60px width)
  - 👤 badge for personal deals (blue)
  - 💼 badge for commission deals (green)
  - Tooltip on hover

### 8. Management Command Changes

**File**: `leads/management/commands/fix_meeting_stats.py` (lines 28, 79)

Changed `hasattr(lead, 'deal')` → `lead.deals.exists()`

## Business Rules: is_personal_deal

### When checkbox is VISIBLE:
- Lead from structure (not personal contact)
- Creating 2nd+ deal for the same lead

### When checkbox is HIDDEN (auto-set):
- **First deal from structure**: Always `is_personal_deal=False` (provizovaný)
- **Personal contact leads**: All deals `is_personal_deal=True` (vlastní)

### Cannot change after creation:
- Field is disabled in edit forms
- Prevents gaming the commission system

### Visibility by role:
| Role | Sees personal deals? | Reason |
|------|---------------------|---------|
| REFERRER | ✅ Yes | It's their deal |
| ADVISOR | ✅ Yes | It's their work |
| REFERRER_MANAGER | ❌ No | No commission for structure |
| OFFICE | ❌ No | No commission for structure |

## Testing Results

✅ All 4 migrations ran successfully
✅ Relationship works: `lead.deals.all()` returns queryset
✅ Sync works: Changing `lead.client_phone` updates all deals
✅ Helper methods work: `get_latest_deal()`, `has_any_deal()`, `deal_count`
✅ `is_personal_deal` field exists with default=False
✅ Django system check: 0 issues

### Test Script
Created `test_refactor.py` for validation:
- Basic relationship (Lead → multiple Deals)
- Sync Lead → Deals (bulk update)
- Helper methods
- is_personal_deal field

## Key Differences from Original Plan

### What was NOT implemented (as requested):
- ❌ `is_primary` field on Deal
- ❌ Concept of "primary deal"
- ❌ `deal_set_primary()` view
- ❌ UI for setting primary deal

### What WAS implemented (new feature):
- ✅ `is_personal_deal` field
- ✅ Checkbox logic for 2nd+ deals
- ✅ First deal always provizovaný
- ✅ Cannot edit after creation
- ✅ Manager/Office don't see personal deals
- ✅ Statistics exclude personal deals for structure

## File Summary

### Modified Files (15)
1. `leads/models.py` - Lead helper methods, Deal ForeignKey, is_personal_deal
2. `leads/signals.py` - Sync to all deals
3. `leads/views.py` - Remove deal existence check
4. `leads/forms.py` - Checkbox logic, field additions
5. `leads/services/access_control.py` - Exclude personal deals
6. `leads/services/user_stats.py` - Exclude personal deals from structure stats
7. `leads/management/commands/fix_meeting_stats.py` - exists() check
8. `templates/leads/lead_detail.html` - Deals table
9. `templates/leads/deal_detail.html` - Type badge, other deals info
10. `templates/leads/deal_form.html` - Existing deals alert
11. `templates/leads/deals_list.html` - Type column

### Created Files (5)
12. `leads/migrations/0017_add_deal_lead_fk_and_is_personal.py`
13. `leads/migrations/0018_migrate_lead_data.py`
14. `leads/migrations/0019_remove_old_lead_field.py`
15. `leads/migrations/0020_rename_lead_fk_to_lead.py`

### Services NOT Changed (as expected)
- `leads/services/filters.py` - Already compatible with ForeignKey
- `leads/services/events.py` - Already compatible
- `leads/services/notifications.py` - Already compatible
- `leads/services/model_helpers.py` - Already compatible

## Deployment Checklist

### Pre-deployment:
- [x] Full database backup
- [x] Code review
- [x] Test migrations on dev
- [x] System check passed

### Deployment:
1. [ ] Production backup (`./backup_database.sh`)
2. [ ] Deploy code to server
3. [ ] Run migrations: `python manage.py migrate leads`
4. [ ] Verify: `Deal.objects.count()` matches pre-deployment
5. [ ] Test critical paths:
   - Create new deal
   - View lead detail
   - View deal detail
   - Check statistics
6. [ ] Monitor error logs (1 hour)

### Post-deployment:
- [ ] User training (status lifecycle behavior)
- [ ] Monitor feedback
- [ ] Update changelog

## Rollback Plan

### If migrations fail:
```bash
python manage.py migrate leads 0016
```

### If full rollback needed:
```bash
./restore_database.sh backups/backup_before_refactor.sql
git revert <commit-hash>
```

## Known Behaviors

### Lead Status Lifecycle:
1. **Creating ANY deal** → Lead status = DEAL_CREATED
   - Even if first deal already has COMMISSION_PAID
2. **Paying commission on ANY deal** → Lead status = COMMISSION_PAID
   - Even if other deals still have unpaid commissions

**Rationale**: Lead status tracks the **most recent activity** on **any deal**, not the overall state of all deals.

### Example:
```
Lead A:
├─ Deal 1: DRAWN, provize vyplacena → Lead status = COMMISSION_PAID
├─ [Create Deal 2]                  → Lead status = DEAL_CREATED ✓
└─ Deal 2: DRAWN, provize vyplacena → Lead status = COMMISSION_PAID ✓
```

## Performance Notes

- **Sync signal** uses `bulk_update()` for efficiency
- Most leads have 1-2 deals, so performance impact is minimal
- Queries optimized with `select_related()`/`prefetch_related()` where needed

## Security Notes

- `is_personal_deal` cannot be changed after creation (prevents gaming)
- Access control properly filters by role
- CSRF protection maintained
- No new security vulnerabilities introduced

## Documentation Updates

This file serves as the primary documentation for the refactoring. Update the following if needed:
- `CLAUDE.md` - Add note about OneToMany relationship
- `PROJECT_CONTEXT.md` - Update model descriptions

---

**Implementation completed by**: Claude Sonnet 4.5
**Date**: 2026-01-28
**Status**: ✅ Ready for production deployment
