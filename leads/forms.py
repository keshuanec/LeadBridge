from django import forms
from django.contrib.auth import get_user_model
from accounts.models import ReferrerProfile
from .models import Lead, LeadNote, Deal
from django.db.models import Q


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
            "is_personal_contact",
            "communication_status",
            "description",
        ]
        labels = {
            "client_name": "Jméno klienta",
            "client_phone": "Telefon klienta",
            "client_email": "E-mail klienta",
            "advisor": "Poradce",
            "referrer": "Doporučitel (makléř)",
            "is_personal_contact": "Vlastní kontakt (bez provizí)",
            "communication_status": "Stav leadu",
            "description": "Popis situace",
        }
        help_texts = {
            "is_personal_contact": "Zaškrtni, pokud je to tvůj vlastní kontakt bez provizí pro manažera/kancelář.",
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
        self.fields["advisor"].queryset = User.objects.filter(role=User.Role.ADVISOR).order_by("last_name", "first_name")
        self.fields["referrer"].queryset = User.objects.filter(role=User.Role.REFERRER).order_by("last_name", "first_name")

        # Poradce není povinný – může se doplnit později
        self.fields["advisor"].required = True
        self.fields["advisor"].empty_label = None


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
            advisors_qs = User.objects.filter(role=User.Role.ADVISOR).order_by("last_name", "first_name")

            profile: ReferrerProfile | None = getattr(user, "referrer_profile", None)
            if profile and profile.advisors.exists():
                advisors_qs = profile.advisors.all().order_by("last_name", "first_name")

            # nastavíme queryset (i kdyby byl prázdný nebo s jedním)
            self.fields["advisor"].queryset = advisors_qs

            # přesně jeden poradce -> skryj select, předvyplň, zobraz jméno
            if advisors_qs.count() == 1:
                advisor = advisors_qs.first()
                self.fields["advisor"].initial = advisor
                self.fields["advisor"].widget = forms.HiddenInput()
                self.single_advisor = advisor

            # více poradců -> zkusíme předvyplnit posledně zvoleného
            elif advisors_qs.count() > 1 and profile and profile.last_chosen_advisor:
                if advisors_qs.filter(pk=profile.last_chosen_advisor_id).exists():
                    self.fields["advisor"].initial = profile.last_chosen_advisor

            # referrer = přihlášený uživatel, pole schováme
            self.fields["referrer"].widget = forms.HiddenInput()
            self.fields["referrer"].initial = user

            # doporučitel nemění stav leadu
            self.fields["communication_status"].widget = forms.HiddenInput()

            # Doporučitel nemůže označit lead jako vlastní kontakt
            self.fields["is_personal_contact"].widget = forms.HiddenInput()
            self.fields["is_personal_contact"].initial = False

        # =========================
        #  ROLE: PORADCE
        # =========================
        elif user.role == User.Role.ADVISOR:
            # referrery omezíme na ty, kteří mají tohoto poradce přiřazeného
            # může to být kdokoliv s ReferrerProfile (REFERRER, REFERRER_MANAGER, OFFICE, ADVISOR)
            referrer_profiles = ReferrerProfile.objects.filter(advisors=user)
            referrer_user_ids = referrer_profiles.values_list("user_id", flat=True)

            referrers_qs = User.objects.filter(id__in=referrer_user_ids).order_by("last_name", "first_name")

            # pokud má poradce svůj ReferrerProfile, přidáme i jeho samotného
            profile: ReferrerProfile | None = getattr(user, "referrer_profile", None)
            if profile:
                referrers_qs = User.objects.filter(
                    Q(id__in=referrer_user_ids) | Q(id=user.id)
                ).distinct().order_by("last_name", "first_name")

                # Poradce s ReferrerProfile může vybrat advisora ze svých přiřazených advisorů
                if profile.advisors.exists():
                    advisors_qs = profile.advisors.all().order_by("last_name", "first_name")

                    # nastavíme queryset
                    self.fields["advisor"].queryset = advisors_qs

                    # přesně jeden advisor -> předvyplníme
                    if advisors_qs.count() == 1:
                        advisor = advisors_qs.first()
                        self.fields["advisor"].initial = advisor
                    # více advisorů -> zkusíme předvyplnit posledně zvoleného, jinak sebe
                    elif advisors_qs.count() > 1:
                        if profile.last_chosen_advisor and advisors_qs.filter(pk=profile.last_chosen_advisor_id).exists():
                            self.fields["advisor"].initial = profile.last_chosen_advisor
                        else:
                            self.fields["advisor"].initial = user
                else:
                    # nemá žádné advisory → advisor = on sám, schováme
                    self.fields["advisor"].widget = forms.HiddenInput()
                    self.fields["advisor"].initial = user
            else:
                # advisor bez ReferrerProfile → advisor = on sám, schováme
                self.fields["advisor"].widget = forms.HiddenInput()
                self.fields["advisor"].initial = user

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
        #  ROLE: MANAŽER DOPORUČITELŮ
        # =========================
        elif user.role == User.Role.REFERRER_MANAGER:
            # doporučitelé, které tento manažer řídí
            # může to být kdokoliv s ReferrerProfile (REFERRER, REFERRER_MANAGER, OFFICE, ADVISOR)
            managed_profiles = ReferrerProfile.objects.filter(manager=user).select_related("user")
            referrer_ids = managed_profiles.values_list("user_id", flat=True)

            # referrers = managed referrers + manažer sám
            referrers_qs = User.objects.filter(
                Q(id__in=referrer_ids) | Q(id=user.id)
            ).distinct().order_by("last_name", "first_name")

            self.fields["referrer"].queryset = referrers_qs

            # při zakládání nového leadu předvyplníme referrer = manažer
            if not instance:
                self.fields["referrer"].initial = user

            # poradci přidělení těmto doporučitelům (přes M2M advisors)
            advisor_ids = managed_profiles.values_list("advisors__id", flat=True)
            advisors_qs = User.objects.filter(
                id__in=advisor_ids,
                role=User.Role.ADVISOR,
            ).distinct().order_by("last_name", "first_name")

            self.fields["advisor"].queryset = advisors_qs

            # Stav leadu manažer zatím nemění – necháme hidden:
            self.fields["communication_status"].widget = forms.HiddenInput()

            # Manažer nemůže označit lead jako vlastní kontakt
            self.fields["is_personal_contact"].widget = forms.HiddenInput()
            self.fields["is_personal_contact"].initial = False

        # =========================
        #  ROLE: KANCELÁŘ
        # =========================

        elif user.role == User.Role.OFFICE:

            # doporučitelé pod manažery této kanceláře
            # může to být kdokoliv s ReferrerProfile (REFERRER, REFERRER_MANAGER, OFFICE, ADVISOR)
            referrer_profiles = ReferrerProfile.objects.filter(
                manager__manager_profile__office__owner=user
            ).select_related("user")

            referrer_ids = referrer_profiles.values_list("user_id", flat=True)

            # referrery = doporučitelé pod kanceláří + kancelář sama
            referrers_qs = User.objects.filter(
                Q(id__in=referrer_ids) | Q(id=user.id)
            ).distinct().order_by("last_name", "first_name")

            self.fields["referrer"].queryset = referrers_qs

            # při zakládání nového leadu předvyplníme referrer = kancelář

            if not instance:
                self.fields["referrer"].initial = user

            # poradci, kteří jsou přiřazeni k těmto doporučitelům

            advisor_ids = referrer_profiles.values_list("advisors__id", flat=True)

            advisors_qs = User.objects.filter(

                id__in=advisor_ids,

                role=User.Role.ADVISOR,

            ).distinct().order_by("last_name", "first_name")

            self.fields["advisor"].queryset = advisors_qs

            # stav leadu kancelář zatím nemění

            self.fields["communication_status"].widget = forms.HiddenInput()

            # Kancelář nemůže označit lead jako vlastní kontakt
            self.fields["is_personal_contact"].widget = forms.HiddenInput()
            self.fields["is_personal_contact"].initial = False

        # =========================
        #  JINÉ ROLE (admin atd.)
        # =========================
        else:
            self.fields["communication_status"].widget = forms.HiddenInput()

            # Ostatní role nemohou označit lead jako vlastní kontakt
            self.fields["is_personal_contact"].widget = forms.HiddenInput()
            self.fields["is_personal_contact"].initial = False

    def clean(self):
        """Validace a automatické nastavení referrer pro vlastní kontakty"""
        cleaned_data = super().clean()
        is_personal_contact = cleaned_data.get("is_personal_contact")
        advisor = cleaned_data.get("advisor")

        # Pokud je to vlastní kontakt, nastavíme referrer = advisor
        if is_personal_contact and advisor:
            cleaned_data["referrer"] = advisor

        return cleaned_data


class LeadNoteForm(forms.ModelForm):
    class Meta:
        model = LeadNote
        fields = ["text", "is_private"]
        labels = {
            "text": "Poznámka",
            "is_private": "Soukromá poznámka (uvidíte jen vy)"
        }
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
        }

class LeadMeetingForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["meeting_at", "meeting_note"]
        labels = {
            "meeting_at": "Datum a čas schůzky",
            "meeting_note": "Poznámka",
        }
        widgets = {
            "meeting_at": forms.DateTimeInput(attrs={"type": "datetime-local", "step": "900"}),
            "meeting_note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_meeting_at(self):
        value = self.cleaned_data["meeting_at"]
        if value is None:
            raise forms.ValidationError("Vyber datum a čas schůzky.")
        return value


class DealCreateForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = ["client_name", "client_phone", "client_email", "loan_amount", "bank", "property_type"]
        labels = {
            "client_name": "Jméno klienta",
            "client_phone": "Telefon",
            "client_email": "E-mail",
            "loan_amount": "Výše úvěru",
            "bank": "Banka",
            "property_type": "Nemovitost",
        }

    def __init__(self, *args, **kwargs):
        lead = kwargs.pop("lead", None)
        super().__init__(*args, **kwargs)

        # klientské údaje jen jako „předvyplněné“ – můžeš je dát readonly
        if lead is not None and not self.instance.pk:
            self.fields["client_name"].initial = lead.client_name
            self.fields["client_phone"].initial = lead.client_phone
            self.fields["client_email"].initial = lead.client_email

        # pokud chceš zakázat editaci klienta v dealu:
        self.fields["client_name"].disabled = True
        self.fields["client_phone"].disabled = True
        self.fields["client_email"].disabled = True

class DealEditForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            "client_name",
            "client_phone",
            "client_email",
            "loan_amount",
            "bank",
            "property_type",
            "status",
        ]
        labels = {
            "client_name": "Jméno klienta",
            "client_phone": "Telefon",
            "client_email": "E-mail",
            "loan_amount": "Výše úvěru (Kč)",
            "bank": "Banka",
            "property_type": "Nemovitost",
            "status": "Stav obchodu",
        }

class MeetingResultForm(forms.Form):
    """Formulář pro záznam výsledku schůzky"""

    ACTION_CHOICES = [
        ("SEARCHING_PROPERTY", "Hledá nemovitost"),
        ("WAITING_FOR_CLIENT", "Čekání na klienta"),
        ("FAILED", "Neúspěšný"),
        ("CREATE_DEAL", "Založit obchod"),
    ]

    next_action = forms.ChoiceField(
        label="Co bude následovat?",
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect,
        required=True,
        help_text="Vyberte další krok po proběhlé schůzce"
    )

    result_note = forms.CharField(
        label="Poznámka k výsledku schůzky",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
        help_text="Jak schůzka proběhla?"
    )


class CallbackScheduleForm(forms.ModelForm):
    """Formulář pro odložení hovoru"""
    class Meta:
        model = Lead
        fields = ["callback_scheduled_date", "callback_note"]
        labels = {
            "callback_scheduled_date": "Datum plánovaného hovoru",
            "callback_note": "Poznámka k hovoru",
        }
        widgets = {
            "callback_scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "callback_note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_callback_scheduled_date(self):
        value = self.cleaned_data["callback_scheduled_date"]
        if value is None:
            raise forms.ValidationError("Vyber datum plánovaného hovoru.")
        return value