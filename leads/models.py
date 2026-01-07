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
    meeting_done = models.BooleanField("Schůzka proběhla", default=False)
    meeting_done_at = models.DateTimeField("Schůzka proběhla (čas)", null=True, blank=True)


    @property
    def referrer_manager(self):
        rp = getattr(self.referrer, "referrer_profile", None)
        return getattr(rp, "manager", None) if rp else None

    @property
    def referrer_office(self):
        manager = self.referrer_manager
        mp = getattr(manager, "manager_profile", None) if manager else None
        office = getattr(mp, "office", None) if mp else None
        return office

    class Meta:
        indexes = [
            models.Index(fields=["referrer"]),
            models.Index(fields=["advisor"]),
            models.Index(fields=["communication_status"]),
            models.Index(fields=["meeting_done"]),
            models.Index(fields=["created_at"]),
        ]


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

    def calculate_commission_parts(self):
        """
        Vypočítá provize podle toho, kdo je referrer.
        Vrací dict s částkami pro každou roli.

        Všechny procenta se berou z referrera (ne z manažera/kanceláře).
        """
        referrer = self.lead.referrer

        if not referrer or not self.loan_amount:
            return {
                'referrer': 0,
                'manager': 0,
                'office': 0,
                'total': 0
            }

        # Základní provize na základě výše úvěru
        commission_base = (
            referrer.commission_total_per_million * self.loan_amount / 1_000_000
        )

        # Výpočet provizí podle procent z referrera
        commission_referrer = int(commission_base * (referrer.commission_referrer_pct / 100))
        commission_manager = int(commission_base * (referrer.commission_manager_pct / 100))
        commission_office = int(commission_base * (referrer.commission_office_pct / 100))

        return {
            'referrer': commission_referrer,
            'manager': commission_manager,
            'office': commission_office,
            'total': commission_referrer + commission_manager + commission_office
        }

    @property
    def calculated_commission_referrer(self):
        """Vypočítá provizi pro doporučitele"""
        parts = self.calculate_commission_parts()
        return parts['referrer']

    @property
    def calculated_commission_manager(self):
        """Vypočítá provizi pro manažera"""
        parts = self.calculate_commission_parts()
        return parts['manager']

    @property
    def calculated_commission_office(self):
        """Vypočítá provizi pro kancelář"""
        parts = self.calculate_commission_parts()
        return parts['office']

    @property
    def calculated_commission_total(self):
        """Vypočítá celkovou provizi (součet všech)"""
        parts = self.calculate_commission_parts()
        return parts['total']

    def get_own_commission(self, user):
        """
        Vrací 'vlastní provizi' podle role uživatele a referrera.

        - Referrer (makléř): pouze commission_referrer
        - Manager jako referrer: commission_referrer + commission_manager
        - Office jako referrer: všechny tři provize
        """
        from accounts.models import User

        if not user:
            return 0

        parts = self.calculate_commission_parts()
        referrer = self.lead.referrer

        # Pokud je to normální makléř (REFERRER role)
        if referrer.role == User.Role.REFERRER:
            if user == referrer:
                return parts['referrer']
            # Pokud je user manager tohoto makléře
            rp = getattr(referrer, 'referrer_profile', None)
            manager = getattr(rp, 'manager', None) if rp else None
            if user == manager:
                return parts['manager']
            # Pokud je user office nad tímto manažerem
            if manager:
                mp = getattr(manager, 'manager_profile', None)
                office = getattr(mp, 'office', None) if mp else None
                office_owner = getattr(office, 'owner', None) if office else None
                if user == office_owner:
                    return parts['office']

        # Pokud je referrer manager
        elif referrer.role == User.Role.REFERRER_MANAGER:
            if user == referrer:
                # Manager jako referrer vidí svou "manažerskou" + "doporučitelskou" část
                return parts['referrer'] + parts['manager']
            # Office nad tímto manažerem
            mp = getattr(referrer, 'manager_profile', None)
            office = getattr(mp, 'office', None) if mp else None
            office_owner = getattr(office, 'owner', None) if office else None
            if user == office_owner:
                return parts['office']

        # Pokud je referrer office
        elif referrer.role == User.Role.OFFICE:
            if user == referrer:
                # Kancelář jako referrer dostává všechny tři
                return parts['referrer'] + parts['manager'] + parts['office']

        return 0

    @property
    def all_commissions_paid(self):
        """Zkontroluje, jestli jsou všichni účastníci vyplacení"""
        # Makléř musí být vždy vyplacený
        if not self.paid_referrer:
            return False

        # Pokud existuje manažer, musí být vyplacený
        referrer = self.lead.referrer
        profile = getattr(referrer, "referrer_profile", None)
        manager = getattr(profile, "manager", None) if profile else None
        if manager and not self.paid_manager:
            return False

        # Pokud existuje kancelář, musí být vyplacená
        manager_profile = getattr(manager, "manager_profile", None) if manager else None
        office = getattr(manager_profile, "office", None) if manager_profile else None
        if office and not self.paid_office:
            return False

        return True