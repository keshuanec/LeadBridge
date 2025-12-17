from django.conf import settings
from django.db import models
from accounts.models import ReferrerProfile
from django.utils import timezone




class Lead(models.Model):
    class CommunicationStatus(models.TextChoices):
        NEW = "NEW", "Nový"
        MEETING = "MEETING", "Domluvená schůzka"
        SEARCHING_PROPERTY = "SEARCHING_PROPERTY", "Hledá nemovitost"
        WAITING_FOR_CLIENT = "WAITING_FOR_CLIENT", "Čekání na klienta"
        FAILED = "FAILED", "Neúspěšný"

        # tyto stavy budou nastavovány automaticky ze sekce Obchody
        DEAL_CREATED = "DEAL_CREATED", "Založen obchod"
        COMMISSION_PAID = "COMMISSION_PAID", "Provize vyplacena"


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

    meeting_at = models.DateTimeField("Datum a čas schůzky", null=True, blank=True)
    meeting_note = models.TextField("Poznámka ke schůzce", blank=True)

    @property
    def referrer_manager(self):
        """
        Vrátí manažera doporučitele (pokud existuje), jinak None.
        Bezpečné i pro leady, kde není ReferrerProfile.
        """
        try:
            return self.referrer.referrer_profile.manager
        except (ReferrerProfile.DoesNotExist, AttributeError):
            return None

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


class Deal(models.Model):
    class Bank(models.TextChoices):
        CS = "CS", "Česká spořitelna"
        CSOB_HB = "CSOB_HB", "ČSOB Hypoteční banka"
        KB = "KB", "Komerční banka"
        MBANK = "MBANK", "mBank"
        OBERBANK = "OBERBANK", "Oberbank"
        RB = "RB", "Raiffeisenbank"
        UCB = "UCB", "Unicredit bank"
        SSCS = "SSCS", "Stavební spořitelna České spořitelny"
        MP = "MP", "Modrá pyramida"
        CSOB_SS = "CSOB_SS", "ČSOB stavební spořitelna"
        RB_SS = "RB_SS", "Raiffeisen stavební spořitelna"

    class PropertyType(models.TextChoices):
        OWN = "OWN", "Vlastní"
        OTHER = "OTHER", "Cizí"

    class DealStatus(models.TextChoices):
        REQUEST_IN_BANK = "REQUEST_IN_BANK", "Žádost v bance"
        WAITING_FOR_APPRAISAL = "WAITING_FOR_APPRAISAL", "Čekání na odhad"
        PREP_APPROVAL = "PREP_APPROVAL", "Příprava schvalování"
        APPROVAL = "APPROVAL", "Schvalování"
        SIGN_PLANNING = "SIGN_PLANNING", "Plánování podpisu"
        SIGNED = "SIGNED", "Podepsaná smlouva"
        SIGNED_NO_PROPERTY = "SIGNED_NO_PROPERTY", "Podepsaná smlouva bez nemovitosti"
        DRAWN = "DRAWN", "Načerpáno"

    class CommissionStatus(models.TextChoices):
        PENDING = "PENDING", "Čekání na provizi"
        READY = "READY", "Provize připravená"
        PAID = "PAID", "Provize vyplacená"

    created_at = models.DateTimeField(auto_now_add=True)

    lead = models.OneToOneField(
        "Lead",
        on_delete=models.PROTECT,
        related_name="deal",
        verbose_name="Lead",
    )

    # kopie klienta v okamžiku založení obchodu (ať se to historicky nemění)
    client_name = models.CharField("Jméno klienta", max_length=255)
    client_phone = models.CharField("Telefon klienta", max_length=50, blank=True)
    client_email = models.EmailField("E-mail klienta", blank=True)

    loan_amount = models.PositiveBigIntegerField("Výše úvěru (Kč)")
    bank = models.CharField("Banka", max_length=32, choices=Bank.choices)
    property_type = models.CharField("Nemovitost", max_length=16, choices=PropertyType.choices)

    status = models.CharField(
        "Stav obchodu",
        max_length=32,
        choices=DealStatus.choices,
        default=DealStatus.REQUEST_IN_BANK,
    )

    # provize – zatím ručně/blank, výpočet doděláme později
    commission_total = models.PositiveIntegerField("Provize celkem (Kč)", null=True, blank=True)
    commission_referrer = models.PositiveIntegerField("Provize makléř (Kč)", null=True, blank=True)
    commission_manager = models.PositiveIntegerField("Provize manažer (Kč)", null=True, blank=True)
    commission_office = models.PositiveIntegerField("Provize kancelář (Kč)", null=True, blank=True)

    commission_status = models.CharField(
        "Stav provize",
        max_length=16,
        choices=CommissionStatus.choices,
        default=CommissionStatus.PENDING,
    )

    # při PAID zobrazíme checkboxy – které části byly vyplaceny
    paid_referrer = models.BooleanField("Vyplacen makléř", default=False)
    paid_manager = models.BooleanField("Vyplacen manažer", default=False)
    paid_office = models.BooleanField("Vyplacena kancelář", default=False)

    def __str__(self):
        return f"Obchod – {self.client_name} ({self.get_status_display()})"