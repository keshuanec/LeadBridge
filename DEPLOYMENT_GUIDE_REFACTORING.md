# Deployment Guide: Lead-Deal Refactoring

**Last Updated**: 2026-01-28
**Commit**: ce02c6f

## Pre-Deployment Checklist

### 1. Review Changes
```bash
git log -1 --stat
git show ce02c6f
```

Read `REFACTORING_SUMMARY.md` for complete details.

### 2. Backup Database
```bash
./backup_database.sh
# Or manually:
# SQLite: cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)
# PostgreSQL: pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql
```

### 3. Test on Staging (if available)
```bash
# On staging server:
git pull origin dev
python manage.py migrate
python manage.py check
python manage.py runserver
```

Test these critical paths:
- Create new lead
- Create first deal from lead
- Create second deal from same lead
- View lead detail (should show deals table)
- View deal detail (should show other deals)
- Check statistics (referrer, advisor, manager)

## Deployment Steps

### Step 1: Deploy Code
```bash
# On production server:
git pull origin dev
# Or push to Railway.app (auto-deploy)
```

### Step 2: Run Migrations
```bash
python manage.py migrate leads
```

This will run migrations 0017-0020 automatically.

**Expected output:**
```
Operations to perform:
  Target specific migration: 0020_rename_lead_fk_to_lead, from leads
Running migrations:
  Applying leads.0017_add_deal_lead_fk_and_is_personal... OK
  Applying leads.0018_migrate_lead_data... OK
  Applying leads.0019_remove_old_lead_field... OK
  Applying leads.0020_rename_lead_fk_to_lead... OK
```

### Step 3: Verify Data Integrity
```bash
python manage.py shell
```

```python
from leads.models import Deal, Lead

# Check counts
print(f"Total deals: {Deal.objects.count()}")
print(f"Total leads: {Lead.objects.count()}")

# Test relationship
lead = Lead.objects.filter(deals__isnull=False).first()
if lead:
    print(f"Lead: {lead.client_name}")
    print(f"Deals: {lead.deals.count()}")
    for deal in lead.deals.all():
        print(f"  - {deal.get_bank_display()}: {deal.loan_amount} Kč")

# Test sync
lead.client_phone = "TEST123"
lead.save()
for deal in lead.deals.all():
    print(f"Deal phone: {deal.client_phone}")  # Should be TEST123

exit()
```

### Step 4: System Check
```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

### Step 5: Restart Application
```bash
# If using Railway.app: automatic
# If using Gunicorn:
sudo systemctl restart leadbridge
# Or kill and restart gunicorn process
```

### Step 6: Monitor Logs
```bash
# Railway.app: Check deployment logs in dashboard
# Or local logs:
tail -f /var/log/leadbridge/error.log
```

Watch for any errors for 10-15 minutes.

## Post-Deployment Testing

### Test 1: Create New Deal
1. Navigate to existing lead
2. Click "Založit obchod" (or "Založit další obchod" if lead has deals)
3. Fill form, submit
4. Verify: Deal appears in deals table on lead detail

### Test 2: View Deals Table
1. Go to any lead with deals
2. Verify: Table shows all deals with columns:
   - Typ (👤 or 💼)
   - Datum
   - Banka
   - Výše úvěru
   - Stav
   - Provize
   - Akce

### Test 3: Create Second Deal
1. Find lead with 1 deal
2. Click "Založit další obchod"
3. Verify: Alert shows "Tento klient již má 1 obchod(y)"
4. Verify: Checkbox "Vlastní obchod (bez provize)" is visible
5. Try both checked and unchecked
6. Submit and verify correct behavior

### Test 4: Statistics
1. Check advisor stats: should include ALL deals
2. Check referrer stats: should exclude personal deals
3. Check manager stats: should exclude personal deals
4. Check office stats: should exclude personal deals

### Test 5: Access Control
1. Login as REFERRER: should see all their deals
2. Login as ADVISOR: should see all assigned deals
3. Login as REFERRER_MANAGER: should NOT see personal deals
4. Login as OFFICE: should NOT see personal deals

## Rollback Procedure

### If migrations fail:
```bash
python manage.py migrate leads 0016
```

### If data is corrupted:
```bash
# Restore from backup
./restore_database.sh backups/backup_<timestamp>.sql

# Or manually:
# SQLite:
cp db.sqlite3.backup_<timestamp> db.sqlite3

# PostgreSQL:
psql $DATABASE_URL < backup_<timestamp>.sql
```

### If code needs revert:
```bash
git revert ce02c6f
git push origin dev
# Re-deploy
python manage.py migrate  # Migrations will auto-rollback
```

## Known Issues & Workarounds

### Issue: Old code cached
**Symptom**: Still seeing "Přejít na obchod" button (OneToOne behavior)
**Fix**: Clear browser cache, restart gunicorn

### Issue: hasattr() errors
**Symptom**: AttributeError: 'Lead' object has no attribute 'deal'
**Fix**: Check if any old code still uses `lead.deal` instead of `lead.deals`

### Issue: Statistics don't exclude personal deals
**Symptom**: Manager sees counts including personal deals
**Fix**: Check that user_stats.py changes were deployed

## User Training

### For Advisors:
1. You can now create multiple deals per lead
2. First deal is always "provizovaný" (commissionable)
3. Second+ deals: you choose if "vlastní" (personal) or "provizovaný"
4. Personal deals don't show to referrer/manager/office
5. Cannot change deal type after creation

### For Referrers:
1. You'll see all YOUR deals (including personal)
2. Advisors can create multiple deals per lead
3. Some deals may be "vlastní" (no commission for you)

### For Managers/Office:
1. You'll see all structure deals
2. Personal deals (👤) are hidden from you
3. Only provizovaný deals (💼) count in your stats

## Performance Notes

- Sync signal uses bulk_update() for efficiency
- Most leads have 1-2 deals, minimal performance impact
- If you notice slowdowns, check database indices

## Support

If issues arise:
1. Check `REFACTORING_SUMMARY.md` for details
2. Check error logs
3. Run `python manage.py check`
4. Test in Django shell
5. Consider rollback if critical

## Next Steps

After successful deployment:
1. Monitor user feedback for 1-2 days
2. Update user documentation if needed
3. Consider adding deal count to overview dashboard
4. Consider adding filter for "multiple deals" in lead list

---

**Deployment completed**: _______________ (date/time)
**Deployed by**: _______________
**Issues encountered**: _______________
**Resolution**: _______________
