from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponseForbidden
from accounts.models import ReferrerProfile
from django.shortcuts import render, redirect, get_object_or_404
from .models import Lead, LeadNote, LeadHistory
from .forms import LeadForm, LeadNoteForm





def get_lead_for_user_or_404(user, pk: int) -> Lead:
    qs = Lead.objects.select_related("referrer", "advisor")

    if user.is_superuser or user.role == User.Role.ADMIN:
        return get_object_or_404(qs, pk=pk)
    elif user.role == User.Role.ADVISOR:
        return get_object_or_404(qs, pk=pk, advisor=user)
    elif user.role == User.Role.REFERRER:
        return get_object_or_404(qs, pk=pk, referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        return get_object_or_404(
            qs,
            pk=pk,
            referrer__referrer_profile__manager=user,
        )
    else:
        raise HttpResponseForbidden("Nemáš oprávnění zobrazit tento lead.")


User = get_user_model()


@login_required
def my_leads(request):
    user: User = request.user

    # Default: nic
    leads_qs = Lead.objects.none()

    if user.is_superuser or user.role == User.Role.ADMIN:
        # Admin vidí všechno
        leads_qs = Lead.objects.all()
    elif user.role == User.Role.ADVISOR:
        # Poradce: leady, kde je přiřazen jako advisor
        leads_qs = Lead.objects.filter(advisor=user)
    elif user.role == User.Role.REFERRER:
        # Doporučitel: leady, které sám zadal
        leads_qs = Lead.objects.filter(referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manažer doporučitelů: leady všech jeho doporučitelů
        leads_qs = Lead.objects.filter(
            referrer__referrer_profile__manager=user
        ).distinct()

    leads_qs = leads_qs.select_related("referrer", "advisor").order_by("-created_at")

    # Tady přidáme info, kdo může vytvářet leady
    can_create_leads = user.role in [User.Role.REFERRER, User.Role.ADVISOR]

    context = {
        "leads": leads_qs,
        "can_create_leads": can_create_leads,
    }
    return render(request, "leads/my_leads.html", context)


@login_required
def lead_create(request):
    user: User = request.user

    if user.role not in (User.Role.REFERRER, User.Role.ADVISOR):
        return HttpResponseForbidden("Nemáš oprávnění vytvářet leady.")

    if request.method == "POST":
        form = LeadForm(request.POST, user=user)
        if form.is_valid():
            lead = form.save(commit=False)

            if user.role == User.Role.REFERRER:
                lead.referrer = user

            elif user.role == User.Role.ADVISOR:
                lead.advisor = user

            lead.save()
            # Zalogujeme vytvoření leadu
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.CREATED,
                user=user,
                description="Lead založen.",
            )

            # 🔽 Pokud je to doporučitel a má vybraného poradce, zapamatujeme si ho
            if user.role == User.Role.REFERRER and lead.advisor_id:
                try:
                    profile = user.referrer_profile
                except ReferrerProfile.DoesNotExist:
                    profile = None

                if profile is not None:
                    profile.last_chosen_advisor = lead.advisor
                    profile.save(update_fields=["last_chosen_advisor"])

            return redirect("my_leads")

    else:
        form = LeadForm(user=user)

    context = {
        "form": form,
        "is_advisor": user.role == User.Role.ADVISOR,
        "is_referrer": user.role == User.Role.REFERRER,
    }

    if request.method == "POST":
        form = LeadForm(request.POST, user=user)
        if form.is_valid():
            ...
        else:
            print(form.errors)  # jen pro vývoj, pak smaž


    return render(request, "leads/lead_form.html", {"form": form, "is_edit": False})

@login_required
def lead_detail(request, pk: int):
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    notes = lead.notes.select_related("author")
    history = lead.history.select_related("user")

    can_schedule_meeting = user.role == User.Role.ADVISOR or user.is_superuser
    can_create_deal = user.role == User.Role.ADVISOR or user.is_superuser

    if request.method == "POST":
        # Přidání poznámky
        note_form = LeadNoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.lead = lead
            note.author = user
            note.save()

            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.NOTE_ADDED,
                user=user,
                description="Přidána poznámka.",
            )

            return redirect("lead_detail", pk=lead.pk)
    else:
        note_form = LeadNoteForm()

    context = {
        "lead": lead,
        "notes": notes,
        "history": history,
        "note_form": note_form,
        "can_schedule_meeting": can_schedule_meeting,
        "can_create_deal": can_create_deal,
    }
    return render(request, "leads/lead_detail.html", context)

@login_required
def lead_edit(request, pk: int):
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    # Tady můžeš případně zpřísnit, kdo smí editovat (např. jen poradce/referrer/admin).
    # Zatím necháme stejné role jako pro prohlížení.

    # Uložíme si původní hodnoty pro log změn
    tracked_fields = ["client_name", "client_phone", "client_email", "description", "communication_status"]
    old_values = {field: getattr(lead, field) for field in tracked_fields}

    if request.method == "POST":
        form = LeadForm(request.POST, user=user, instance=lead)
        if form.is_valid():
            updated_lead = form.save(commit=False)

            # Bezpečnostní zajištění referrer/advisor podle role
            if user.role == User.Role.REFERRER:
                updated_lead.referrer = user
            elif user.role == User.Role.ADVISOR:
                updated_lead.advisor = user

            updated_lead.save()

            # Zjistíme, co se změnilo
            changes = []
            labels = {
                "client_name": "Jméno klienta",
                "client_phone": "Telefon",
                "client_email": "E-mail",
                "description": "Poznámka",
                "communication_status": "Stav leadu",
            }

            status_changed = False
            status_labels = dict(Lead.CommunicationStatus.choices)

            for field in tracked_fields:
                old = old_values[field]
                new = getattr(updated_lead, field)
                if old != new:
                    # U poznámky nedává smysl vypisovat celý text
                    if field == "description":
                        changes.append("Změněna hlavní poznámka.")
                    elif field == "communication_status":
                        old_label = status_labels.get(old, old or "—")
                        new_label = status_labels.get(new, new or "—")
                        changes.append(f"Změněn stav leadu: {old_label} → {new_label}")
                        status_changed = True
                    else:
                        changes.append(f"Změněno {labels[field]}: {old or '—'} → {new or '—'}")

            if changes:
                LeadHistory.objects.create(
                    lead=updated_lead,
                    event_type=(
                        LeadHistory.EventType.STATUS_CHANGED
                        if status_changed
                        else LeadHistory.EventType.UPDATED
                    ),
                    user=user,
                    description="; ".join(changes),
                )

            return redirect("lead_detail", pk=updated_lead.pk)
    else:
        form = LeadForm(user=user, instance=lead)

    return render(request, "leads/lead_form.html", {"form": form, "lead": lead, "is_edit": True})


@login_required
def deals_list(request):
    # Placeholder – později sem dáme skutečné obchody
    return render(request, "leads/deals_list.html")

@login_required
def referrers_list(request):
    user: User = request.user

    # Vidí jen poradce, manažer doporučitelů a admin
    if not (user.role in [User.Role.ADVISOR, User.Role.REFERRER_MANAGER] or user.is_superuser):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit doporučitele.")

    from accounts.models import ReferrerProfile

    queryset = ReferrerProfile.objects.select_related("user", "manager").prefetch_related("advisors")

    # Poradce vidí jen „svoje“ doporučitele
    if user.role == User.Role.ADVISOR and not user.is_superuser:
        queryset = queryset.filter(advisors=user)

    # Manažer vidí svoje doporučitele
    if user.role == User.Role.REFERRER_MANAGER and not user.is_superuser:
        queryset = queryset.filter(manager=user)

    context = {
        "referrer_profiles": queryset,
    }
    return render(request, "leads/referrers_list.html", context)


