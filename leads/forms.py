from django import forms
from django.contrib.auth import get_user_model
from accounts.models import ReferrerProfile
from .models import Lead, LeadNote

User = get_user_model()


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "client_name",
            "client_phone",
            "client_email",
            "advisor",
            "referrer",
            "communication_status",
            "description",
        ]
        labels = {
            "client_name": "Jméno klienta",
            "client_phone": "Telefon klienta",
            "client_email": "E-mail klienta",
            "advisor": "Poradce",
            "referrer": "Doporučitel (makléř)",
            "communication_status": "Stav leadu",
            "description": "Popis situace",
        }

    extra_note = forms.CharField(
        label="Poznámka ke změně stavu",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Default: žádný "single advisor"
        self.single_advisor = None

        # Základní querysety
        self.fields["advisor"].queryset = User.objects.filter(role=User.Role.ADVISOR)
        self.fields["referrer"].queryset = User.objects.filter(role=User.Role.REFERRER)

        # Poradce není povinný – může se doplnit později
        self.fields["advisor"].required = False

        # ----- STAV LEADU -----

        # Stavy, které může poradce volit ručně:
        manual_status_codes = {
            Lead.CommunicationStatus.NEW,
            Lead.CommunicationStatus.MEETING,
            Lead.CommunicationStatus.SEARCHING_PROPERTY,
            Lead.CommunicationStatus.WAITING_FOR_CLIENT,
            Lead.CommunicationStatus.FAILED,
        }

        # Všechny dostupné choices – použijeme je při filtrování
        all_choices = list(self.fields["communication_status"].choices)

        # Instance leadu (při editaci)
        instance = self.instance if getattr(self, "instance", None) and self.instance.pk else None

        if user is None:
            return

        # =========================
        #  ROLE: DOPORUČITEL
        # =========================
        if user.role == User.Role.REFERRER:
            advisors_qs = User.objects.filter(role=User.Role.ADVISOR)

            profile = getattr(user, "referrer_profile", None)
            if profile and profile.advisors.exists():
                advisors_qs = profile.advisors.all()

            # nastavíme queryset (i kdyby byl prázdný nebo s jedním)
            self.fields["advisor"].queryset = advisors_qs

            # přesně jeden poradce -> u NOVÉHO leadu skryj select, předvyplň, zobraz jméno
            if advisors_qs.count() == 1 and not instance:
                advisor = advisors_qs.first()
                self.fields["advisor"].initial = advisor
                self.fields["advisor"].widget = forms.HiddenInput()
                self.single_advisor = advisor

            # referrer = přihlášený uživatel, pole schováme
            self.fields["referrer"].widget = forms.HiddenInput()
            self.fields["referrer"].initial = user

            # doporučitel nemění stav leadu
            self.fields["communication_status"].widget = forms.HiddenInput()

        # =========================
        #  ROLE: PORADCE
        # =========================
        elif user.role == User.Role.ADVISOR:
            # advisor = přihlášený uživatel, pole schováme
            self.fields["advisor"].widget = forms.HiddenInput()
            self.fields["advisor"].initial = user

            # referrery omezíme na ty, kteří mají tohoto poradce přiřazeného
            referrer_profiles = ReferrerProfile.objects.filter(advisors=user)
            referrer_user_ids = referrer_profiles.values_list("user_id", flat=True)

            referrers_qs = User.objects.filter(
                id__in=referrer_user_ids,
                role=User.Role.REFERRER,
            )
            self.fields["referrer"].queryset = referrers_qs

            # ---- Stav leadu pro poradce ----
            current_status = instance.communication_status if instance else None

            # Kódy, které mají být v choice (vždy manuální + aktuální)
            allowed_codes = set(manual_status_codes)
            if current_status:
                allowed_codes.add(current_status)

            filtered_choices = [
                (code, label)
                for code, label in all_choices
                if code in allowed_codes
            ]
            self.fields["communication_status"].choices = filtered_choices

            # Pokud je aktuální stav "automatický" (není v manuálních),
            # zobrazíme ho, ale nepovolíme změnu:
            if current_status and current_status not in manual_status_codes:
                self.fields["communication_status"].disabled = True

        # =========================
        #  JINÉ ROLE (manager, admin, ...)
        # =========================
        else:
            # Zatím jim stav schováme – můžeme to později zpřesnit
            self.fields["communication_status"].widget = forms.HiddenInput()

class LeadNoteForm(forms.ModelForm):
    class Meta:
        model = LeadNote
        fields = ["text"]
        labels = {"text": "Poznámka"}
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
        }