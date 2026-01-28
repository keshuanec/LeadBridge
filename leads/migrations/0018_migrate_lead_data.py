# Generated migration for copying data from OneToOne to ForeignKey
from django.db import migrations


def migrate_deals_forward(apps, schema_editor):
    """Copy data from lead (OneToOne) to lead_fk (ForeignKey)"""
    Deal = apps.get_model('leads', 'Deal')

    for deal in Deal.objects.all():
        deal.lead_fk = deal.lead  # Copy OneToOne reference to FK
        deal.save(update_fields=['lead_fk'])


def migrate_deals_backward(apps, schema_editor):
    """Rollback: copy data from lead_fk back to lead"""
    Deal = apps.get_model('leads', 'Deal')

    for deal in Deal.objects.all():
        if deal.lead_fk:
            deal.lead = deal.lead_fk
            deal.save(update_fields=['lead'])


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0017_add_deal_lead_fk_and_is_personal'),
    ]

    operations = [
        migrations.RunPython(migrate_deals_forward, migrate_deals_backward),
    ]
