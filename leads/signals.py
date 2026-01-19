from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Lead, Deal


@receiver(post_save, sender=Lead)
def sync_lead_to_deal(sender, instance, created, **kwargs):
    """
    Synchronizuje změny v Lead do souvisejícího Deal.

    Pokud se změní client_name, client_phone nebo client_email v Lead,
    automaticky se aktualizuje i v Deal (pokud existuje).
    """
    # Pokud je Lead právě vytvořený, neděláme nic (Deal ještě neexistuje)
    if created:
        return

    # Zkontrolujeme, zda má Lead související Deal
    try:
        deal = instance.deal
    except Deal.DoesNotExist:
        # Lead ještě nemá Deal, není co synchronizovat
        return

    # Synchronizujeme data klienta z Lead do Deal
    # Používáme update() místo save() aby se nespustil další signal (zabránění nekonečné smyčky)
    Deal.objects.filter(pk=deal.pk).update(
        client_name=instance.client_name,
        client_phone=instance.client_phone,
        client_email=instance.client_email,
    )


@receiver(post_save, sender=Deal)
def sync_deal_to_lead(sender, instance, created, **kwargs):
    """
    Synchronizuje změny v Deal do souvisejícího Lead.

    Pokud se změní client_name, client_phone nebo client_email v Deal,
    automaticky se aktualizuje i v Lead.
    """
    # Pokud je Deal právě vytvořený, neděláme nic (data jsou už zkopírovaná při vytvoření)
    if created:
        return

    # Deal má vždy Lead (OneToOneField), takže můžeme rovnou synchronizovat
    lead = instance.lead

    # Synchronizujeme data klienta z Deal do Lead
    # Používáme update() místo save() aby se nespustil další signal (zabránění nekonečné smyčky)
    Lead.objects.filter(pk=lead.pk).update(
        client_name=instance.client_name,
        client_phone=instance.client_phone,
        client_email=instance.client_email,
    )
