from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Lead, Deal, LeadNote, ActivityLog
from django.contrib.auth import get_user_model

User = get_user_model()


# Pomocná proměnná pro sledování změn
_lead_old_values = {}
_deal_old_values = {}


@receiver(pre_save, sender=Lead)
def lead_pre_save(sender, instance, **kwargs):
    """Uloží starý stav Lead před uložením pro detekci změn"""
    if instance.pk:
        try:
            old_lead = Lead.objects.get(pk=instance.pk)
            _lead_old_values[instance.pk] = {
                'client_name': old_lead.client_name,
                'client_phone': old_lead.client_phone,
                'client_email': old_lead.client_email,
                'communication_status': old_lead.communication_status,
                'callback_scheduled_date': old_lead.callback_scheduled_date,
            }
        except Lead.DoesNotExist:
            pass


@receiver(post_save, sender=Lead)
def sync_lead_to_deal(sender, instance, created, **kwargs):
    """
    Synchronizuje změny v Lead do souvisejícího Deal.

    Pokud se změní client_name, client_phone nebo client_email v Lead,
    automaticky se aktualizuje i v Deal (pokud existuje).
    """
    # Logování vytvoření Lead
    if created:
        ActivityLog.objects.create(
            user=getattr(instance, '_created_by', instance.referrer),
            activity_type=ActivityLog.ActivityType.LEAD_CREATED,
            description=f"Vytvořen lead pro klienta {instance.client_name}",
            lead=instance,
            metadata={
                'client_name': instance.client_name,
                'referrer': instance.referrer.get_full_name() if instance.referrer else None,
                'advisor': instance.advisor.get_full_name() if instance.advisor else None,
            }
        )
        return

    # Logování změn
    if instance.pk in _lead_old_values:
        old_values = _lead_old_values[instance.pk]
        changes = {}

        if old_values['client_name'] != instance.client_name:
            changes['Jméno klienta'] = {'old': old_values['client_name'], 'new': instance.client_name}
        if old_values['client_phone'] != instance.client_phone:
            changes['Telefon'] = {'old': old_values['client_phone'], 'new': instance.client_phone}
        if old_values['client_email'] != instance.client_email:
            changes['Email'] = {'old': old_values['client_email'], 'new': instance.client_email}
        if old_values['communication_status'] != instance.communication_status:
            changes['Stav komunikace'] = {
                'old': old_values['communication_status'],
                'new': instance.communication_status
            }

        # Logování naplánovaného hovoru
        if old_values['callback_scheduled_date'] != instance.callback_scheduled_date and instance.callback_scheduled_date:
            ActivityLog.objects.create(
                user=getattr(instance, '_updated_by', None),
                activity_type=ActivityLog.ActivityType.LEAD_CALLBACK_SCHEDULED,
                description=f"Naplánován odložený hovor pro {instance.client_name} na {instance.callback_scheduled_date}",
                lead=instance,
                metadata={'callback_date': str(instance.callback_scheduled_date)}
            )

        if changes:
            change_description = ", ".join([f"{field}: '{old}' → '{new}'" for field, vals in changes.items() for old, new in [(vals['old'], vals['new'])]])
            ActivityLog.objects.create(
                user=getattr(instance, '_updated_by', None),
                activity_type=ActivityLog.ActivityType.LEAD_UPDATED,
                description=f"Upraven lead {instance.client_name}: {change_description}",
                lead=instance,
                metadata={'changes': changes}
            )

        # Vyčistit cache
        del _lead_old_values[instance.pk]

    # Synchronizace s Deal
    try:
        deal = instance.deal
    except Deal.DoesNotExist:
        return

    Deal.objects.filter(pk=deal.pk).update(
        client_name=instance.client_name,
        client_phone=instance.client_phone,
        client_email=instance.client_email,
    )


@receiver(pre_save, sender=Deal)
def deal_pre_save(sender, instance, **kwargs):
    """Uloží starý stav Deal před uložením pro detekci změn"""
    if instance.pk:
        try:
            old_deal = Deal.objects.get(pk=instance.pk)
            _deal_old_values[instance.pk] = {
                'client_name': old_deal.client_name,
                'client_phone': old_deal.client_phone,
                'client_email': old_deal.client_email,
                'status': old_deal.status,
                'loan_amount': old_deal.loan_amount,
                'bank': old_deal.bank,
                'commission_status': old_deal.commission_status,
            }
        except Deal.DoesNotExist:
            pass


@receiver(post_save, sender=Deal)
def sync_deal_to_lead(sender, instance, created, **kwargs):
    """
    Synchronizuje změny v Deal do souvisejícího Lead.

    Pokud se změní client_name, client_phone nebo client_email v Deal,
    automaticky se aktualizuje i v Lead.
    """
    # Logování vytvoření Deal
    if created:
        ActivityLog.objects.create(
            user=getattr(instance, '_created_by', None),
            activity_type=ActivityLog.ActivityType.DEAL_CREATED,
            description=f"Vytvořen obchod pro klienta {instance.client_name}, banka: {instance.get_bank_display()}, částka: {instance.loan_amount:,} Kč",
            lead=instance.lead,
            deal=instance,
            metadata={
                'client_name': instance.client_name,
                'loan_amount': instance.loan_amount,
                'bank': instance.bank,
            }
        )
        return

    # Logování změn
    if instance.pk in _deal_old_values:
        old_values = _deal_old_values[instance.pk]
        changes = {}

        if old_values['client_name'] != instance.client_name:
            changes['Jméno klienta'] = {'old': old_values['client_name'], 'new': instance.client_name}
        if old_values['client_phone'] != instance.client_phone:
            changes['Telefon'] = {'old': old_values['client_phone'], 'new': instance.client_phone}
        if old_values['client_email'] != instance.client_email:
            changes['Email'] = {'old': old_values['client_email'], 'new': instance.client_email}
        if old_values['status'] != instance.status:
            changes['Stav obchodu'] = {'old': old_values['status'], 'new': instance.status}
        if old_values['loan_amount'] != instance.loan_amount:
            changes['Výše úvěru'] = {'old': old_values['loan_amount'], 'new': instance.loan_amount}
        if old_values['bank'] != instance.bank:
            changes['Banka'] = {'old': old_values['bank'], 'new': instance.bank}
        if old_values['commission_status'] != instance.commission_status:
            changes['Stav provize'] = {'old': old_values['commission_status'], 'new': instance.commission_status}

        if changes:
            change_description = ", ".join([f"{field}: '{old}' → '{new}'" for field, vals in changes.items() for old, new in [(vals['old'], vals['new'])]])
            ActivityLog.objects.create(
                user=getattr(instance, '_updated_by', None),
                activity_type=ActivityLog.ActivityType.DEAL_UPDATED,
                description=f"Upraven obchod {instance.client_name}: {change_description}",
                lead=instance.lead,
                deal=instance,
                metadata={'changes': changes}
            )

        # Vyčistit cache
        del _deal_old_values[instance.pk]

    # Synchronizace s Lead
    lead = instance.lead
    Lead.objects.filter(pk=lead.pk).update(
        client_name=instance.client_name,
        client_phone=instance.client_phone,
        client_email=instance.client_email,
    )


@receiver(post_save, sender=LeadNote)
def log_lead_note_created(sender, instance, created, **kwargs):
    """Logování přidání poznámky k leadu"""
    if created:
        ActivityLog.objects.create(
            user=instance.author,
            activity_type=ActivityLog.ActivityType.LEAD_NOTE_ADDED,
            description=f"Přidána {'soukromá ' if instance.is_private else ''}poznámka k leadu {instance.lead.client_name}: {instance.text[:50]}{'...' if len(instance.text) > 50 else ''}",
            lead=instance.lead,
            metadata={
                'is_private': instance.is_private,
                'note_preview': instance.text[:100]
            }
        )
