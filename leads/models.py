from django.conf import settings
from django.db import models


class Lead(models.Model):
    class CommunicationStatus(models.TextChoices):
        NEW = "NEW", "Nový"
        IN_CONTACT = "IN_CONTACT", "V kontaktu"
        MEETING = "MEETING", "Schůzka domluvena"
        WON = "WON", "Uzavřeno"
        LOST = "LOST", "Ztraceno"

    class CommissionStatus(models.TextChoices):
        NOT_APPLICABLE = "NA", "Nevztahuje se"
        PENDING = "PENDING", "Čeká na vyplacení"
        PAID = "PAID", "Vyplaceno"
        CANCELLED = "CANCELLED", "Zrušeno"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    client_name = models.CharField("Jméno klienta", max_length=255)
    client_phone = models.CharField("Telefon klienta", max_length=50, blank=True)
    client_email = models.EmailField("E-mail klienta", blank=True)

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leads_created",
        verbose_name="Doporučitel (makléř)",
        help_text="Kdo tento lead zadal.",
    )

    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leads_assigned",
        verbose_name="Poradce",
        null=True,
        blank=True,
        help_text="Poradce, který lead obsluhuje.",
    )

    description = models.TextField("Poznámka", blank=True)

    communication_status = models.CharField(
        "Stav komunikace",
        max_length=32,
        choices=CommunicationStatus.choices,
        default=CommunicationStatus.NEW,
    )

    commission_amount = models.DecimalField(
        "Výše provize",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    commission_status = models.CharField(
        "Stav provize",
        max_length=32,
        choices=CommissionStatus.choices,
        default=CommissionStatus.NOT_APPLICABLE,
    )

    commission_due_date = models.DateField(
        "Termín vyplacení provize",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.client_name} – {self.referrer}"


class LeadNote(models.Model):
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name="Lead",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_notes",
        verbose_name="Autor",
    )
    text = models.TextField("Text poznámky")
    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Poznámka k {self.lead} ({self.created_at})"


class LeadHistory(models.Model):
    class EventType(models.TextChoices):
        CREATED = "CREATED", "Lead založen"
        NOTE_ADDED = "NOTE_ADDED", "Přidána poznámka"
        UPDATED = "UPDATED", "Lead upraven"
        MEETING_SCHEDULED = "MEETING_SCHEDULED", "Domluvena schůzka"
        DEAL_CREATED = "DEAL_CREATED", "Založen obchod"
        STATUS_CHANGED = "STATUS_CHANGED", "Změna stavu"

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Lead",
    )
    event_type = models.CharField(
        "Typ události",
        max_length=32,
        choices=EventType.choices,
    )
    description = models.TextField("Popis události", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_history_events",
        verbose_name="Uživatel",
    )
    created_at = models.DateTimeField("Čas události", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_event_type_display()} – {self.lead} ({self.created_at})"
