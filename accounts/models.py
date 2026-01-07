from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings



class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        ADVISOR = "ADVISOR", "Poradce"
        REFERRER = "REFERRER", "Doporučitel"
        REFERRER_MANAGER = "REFERRER_MANAGER", "Manažer doporučitelů"
        OFFICE = "OFFICE", "Kancelář"

    # Přepsat first_name a last_name jako povinné
    first_name = models.CharField("Jméno", max_length=150)
    last_name = models.CharField("Příjmení", max_length=150)

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.REFERRER,
        help_text="Role uživatele v systému LeadBridge.",
    )

    phone = models.CharField(
        "Telefon",
        max_length=20,
        blank=True,
        help_text="Telefonní číslo uživatele.",
    )

    has_admin_access = models.BooleanField(
        "Administrativní přístup",
        default=False,
        help_text="Poradce s administrativním přístupem vidí leady a obchody všech svých podřízených doporučitelů.",
    )

    commission_total_per_million = models.DecimalField(
        "Celková provize za 1 mil. Kč",
        max_digits=10,
        decimal_places=0,
        default=0,
        help_text="Celková provize za každý 1 000 000 Kč realizované hypotéky (např. 7000).",
    )

    commission_referrer_pct = models.DecimalField(
        "Procento provize doporučitele",
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Procento z celkové provize pro doporučitele (např. 90.00 pro 90%).",
    )

    commission_manager_pct = models.DecimalField(
        "Procento provize manažera",
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Procento z celkové provize pro manažera (např. 10.00 pro 10%).",
    )

    commission_office_pct = models.DecimalField(
        "Procento provize kanceláře",
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Procento z celkové provize pro kancelář (např. 40.00 pro 40%).",
    )

    def clean(self):
        """Validace, že součet procent provizí nepřekročí 100%"""
        from django.core.exceptions import ValidationError

        total = (
            self.commission_referrer_pct
            + self.commission_manager_pct
            + self.commission_office_pct
        )
        if total > 100:
            raise ValidationError(
                f"Součet procent provizí ({total}%) nesmí překročit 100%."
            )

    def __str__(self):
        return self.get_full_name()


class ReferrerProfile(models.Model):
    """
    Profil doporučitele - může být makléř, manažer nebo kancelář.
    Všichni mohou vystupovat jako doporučitelé a mají:
    - přiřazeného manažera (pokud existuje)
    - dostupné poradce
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="referrer_profile",
        verbose_name="Doporučitel",
        help_text="Uživatel, který může vystupovat jako doporučitel (makléř, manažer, kancelář)",
    )

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_referrers",
        limit_choices_to={"role__in": [User.Role.REFERRER_MANAGER, User.Role.OFFICE]},
        verbose_name="Manažer doporučitelů",
        help_text="Manažer nebo kancelář, pod kterého tento doporučitel spadá.",
    )

    advisors = models.ManyToManyField(
        User,
        blank=True,
        related_name="referrers",
        limit_choices_to={"role": User.Role.ADVISOR},
        verbose_name="Přiřazení poradci",
        help_text="Poradci, ze kterých může tento doporučitel vybírat při zakládání leadu.",
    )

    last_chosen_advisor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preferred_by_referrers",
        limit_choices_to={"role": User.Role.ADVISOR},
        verbose_name="Naposledy zvolený poradce",
    )

    def __str__(self):
        return f"Profil doporučitele: {self.user}"


class Office(models.Model):
    """
    Realitní kancelář (nadřazený subjekt nad manažery doporučitelů).
    """
    name = models.CharField("Název kanceláře", max_length=255)

    # volitelné: vlastník / admin kanceláře
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_offices",
        limit_choices_to={"role": User.Role.OFFICE},
        verbose_name="Uživatel kanceláře",
    )

    def __str__(self):
        return self.name

class ManagerProfile(models.Model):
    """
    Rozšíření pro manažera doporučitelů.
    Umožňuje nám přiřadit manažera ke kanceláři.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="manager_profile",
        limit_choices_to={"role": User.Role.REFERRER_MANAGER},
        verbose_name="Manažer",
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managers",
        verbose_name="Kancelář",
    )

    def __str__(self):
        return f"Profil manažera: {self.user}"