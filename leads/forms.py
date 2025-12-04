from django import forms
from .models import Lead
from django.contrib.auth import get_user_model
from accounts.models import ReferrerProfile

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
            "description",
        ]
        labels = {
            "client_name": "Jméno klienta",
            "client_phone": "Telefon klienta",
            "client_email": "E-mail klienta",
            "advisor": "Poradce",
            "referrer": "Doporučitel (makléř)",
            "description": "Poznámka",
        }

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

        if user is None:
            return

        # =========================
        #  ROLE: DOPORUČITEL
        # =========================
        if user.role == User.Role.REFERRER:
            advisors_qs = User.objects.filter(role=User.Role.ADVISOR)
            profile = None

            if hasattr(user, "referrer_profile"):
                profile: ReferrerProfile = user.referrer_profile
                if profile.advisors.exists():
                    advisors_qs = profile.advisors.all()

            # nastavíme queryset (i kdyby byl prázdný nebo s jedním)
            self.fields["advisor"].queryset = advisors_qs

            if advisors_qs.count() == 1:
                # přesně jeden poradce -> skryj select, předvyplň, zobraz jméno
                advisor = advisors_qs.first()
                self.fields["advisor"].initial = advisor
                self.fields["advisor"].widget = forms.HiddenInput()
                self.single_advisor = advisor

            elif advisors_qs.count() > 1 and hasattr(user, "referrer_profile"):
                # více poradců -> select, ale můžeme předvyplnit posledního oblíbeného
                profile = user.referrer_profile
                if (
                    profile.last_chosen_advisor
                    and advisors_qs.filter(pk=profile.last_chosen_advisor_id).exists()
                ):
                    self.fields["advisor"].initial = profile.last_chosen_advisor

            # referrer = přihlášený uživatel, pole schováme
            self.fields["referrer"].widget = forms.HiddenInput()
            self.fields["referrer"].initial = user

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
