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

    def __str__(self):
        return self.get_full_name() or self.username


class ReferrerProfile(models.Model):
    """
    Extra informace pro doporučitele (realitního makléře).
    - kdo je jeho manažer
    - jaké poradce má k dispozici
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="referrer_profile",
        verbose_name="Doporučitel",
    )

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_referrers",
        limit_choices_to={"role": User.Role.REFERRER_MANAGER},
        verbose_name="Manažer doporučitelů",
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