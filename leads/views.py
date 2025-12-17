from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponseForbidden
from accounts.models import ReferrerProfile, Office
from django.shortcuts import render, redirect, get_object_or_404
from .models import Lead, LeadNote, LeadHistory, Deal
from .forms import LeadForm, LeadNoteForm, LeadMeetingForm, DealCreateForm
from django.db.models import Q
from django.utils.http import urlencode
from django.utils import timezone


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
    elif user.role == User.Role.OFFICE:
        return get_object_or_404(
            qs.filter(
                Q(referrer__referrer_profile__manager__manager_profile__office__owner=user)
                | Q(referrer=user)
            ),
            pk=pk,
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
        leads_qs = Lead.objects.all()

    elif user.role == User.Role.ADVISOR:
        leads_qs = Lead.objects.filter(advisor=user)

    elif user.role == User.Role.REFERRER:
        leads_qs = Lead.objects.filter(referrer=user)

    elif user.role == User.Role.REFERRER_MANAGER:
        leads_qs = Lead.objects.filter(
            referrer__referrer_profile__manager=user
        ).distinct()

    elif user.role == User.Role.OFFICE:
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager__manager_profile__office__owner=user)
            | Q(referrer=user)
        ).distinct()

    # --- base queryset (na options do filtrů) ---
    base_leads_qs = leads_qs

    # optimalizace – načteme referrera, poradce a manažera
    leads_qs = leads_qs.select_related(
        "referrer",
        "advisor",
        "referrer__referrer_profile__manager",
        "referrer__referrer_profile__manager__manager_profile__office",
    )

    # ===== Filtry povolené podle role =====
    allowed_filters = {
        User.Role.REFERRER: {"status", "advisor"},
        User.Role.REFERRER_MANAGER: {"status", "referrer", "advisor"},
        User.Role.OFFICE: {"status", "referrer", "manager", "advisor"},
        User.Role.ADVISOR: {"status", "referrer", "manager", "office"},
    }

    if user.is_superuser or user.role == User.Role.ADMIN:
        allowed = {"status", "referrer", "advisor", "manager", "office"}
    else:
        allowed = allowed_filters.get(user.role, set())

    # ===== Čtení filtrů z GET =====
    current_status = request.GET.get("status") or ""
    current_referrer = request.GET.get("referrer") or ""
    current_advisor = request.GET.get("advisor") or ""
    current_manager = request.GET.get("manager") or ""
    current_office = request.GET.get("office") or ""

    # ===== Aplikace filtrů (jen povolené) =====
    if "status" in allowed and current_status:
        leads_qs = leads_qs.filter(communication_status=current_status)

    if "referrer" in allowed and current_referrer:
        leads_qs = leads_qs.filter(referrer_id=current_referrer)

    if "advisor" in allowed and current_advisor:
        leads_qs = leads_qs.filter(advisor_id=current_advisor)

    if "manager" in allowed and current_manager:
        if current_manager == "__none__":
            leads_qs = leads_qs.filter(
                Q(referrer__referrer_profile__manager__isnull=True) |
                Q(referrer__referrer_profile__isnull=True)
            )
        else:
            leads_qs = leads_qs.filter(referrer__referrer_profile__manager_id=current_manager)

    if "office" in allowed and current_office:
        if current_office == "__none__":
            leads_qs = leads_qs.filter(
                Q(referrer__referrer_profile__manager__manager_profile__office__isnull=True) |
                Q(referrer__referrer_profile__manager__isnull=True) |
                Q(referrer__referrer_profile__isnull=True)
            )
        else:
            leads_qs = leads_qs.filter(
                referrer__referrer_profile__manager__manager_profile__office_id=current_office
            )

    # ===== ŘAZENÍ =====
    sort = request.GET.get("sort") or "created_at"
    direction = request.GET.get("dir") or "desc"

    sort_mapping = {
        "client": ["client_name"],
        "referrer": ["referrer__last_name", "referrer__first_name", "referrer__username"],
        "advisor": ["advisor__last_name", "advisor__first_name", "advisor__username"],
        "manager": [
            "referrer__referrer_profile__manager__last_name",
            "referrer__referrer_profile__manager__first_name",
            "referrer__referrer_profile__manager__username",
        ],
        "office": [
            "referrer__referrer_profile__manager__manager_profile__office__name",
        ],
        "comm_status": ["communication_status"],
        "commission": ["commission_status"],
        "created_at": ["created_at"],
    }

    if sort not in sort_mapping:
        sort = "created_at"
    if direction not in ["asc", "desc"]:
        direction = "desc"

    order_fields = sort_mapping[sort]
    leads_qs = leads_qs.order_by(*([("-" + f) for f in order_fields] if direction == "desc" else order_fields))

    # ===== Options do filtrů (vždy jen z base_leads_qs) =====
    status_choices = Lead.CommunicationStatus.choices

    referrer_options = User.objects.none()
    advisor_options = User.objects.none()
    manager_options = User.objects.none()
    office_options = Office.objects.none()

    if "referrer" in allowed:
        ref_ids = base_leads_qs.values_list("referrer_id", flat=True).distinct()
        referrer_options = User.objects.filter(id__in=ref_ids)

    if "advisor" in allowed:
        adv_ids = base_leads_qs.values_list("advisor_id", flat=True).distinct()
        advisor_options = User.objects.filter(id__in=[x for x in adv_ids if x])

    if "manager" in allowed:
        mgr_ids = base_leads_qs.values_list("referrer__referrer_profile__manager_id", flat=True).distinct()
        manager_options = User.objects.filter(id__in=[x for x in mgr_ids if x])

    if "office" in allowed:
        off_ids = base_leads_qs.values_list(
            "referrer__referrer_profile__manager__manager_profile__office_id",
            flat=True
        ).distinct()
        office_options = Office.objects.filter(id__in=[x for x in off_ids if x])

    # ===== Zachování filtrů při řazení (klik na sloupce) =====
    keep_params = {}
    if "status" in allowed and current_status:
        keep_params["status"] = current_status
    if "referrer" in allowed and current_referrer:
        keep_params["referrer"] = current_referrer
    if "advisor" in allowed and current_advisor:
        keep_params["advisor"] = current_advisor
    if "manager" in allowed and current_manager:
        keep_params["manager"] = current_manager
    if "office" in allowed and current_office:
        keep_params["office"] = current_office

    qs_keep = urlencode(keep_params)

    can_create_leads = user.role in [User.Role.REFERRER, User.Role.ADVISOR, User.Role.OFFICE]

    context = {
        "leads": leads_qs,
        "can_create_leads": can_create_leads,
        "current_sort": sort,
        "current_dir": direction,

        # filtry
        "allowed": allowed,
        "status_choices": status_choices,
        "referrer_options": referrer_options,
        "advisor_options": advisor_options,
        "manager_options": manager_options,
        "office_options": office_options,

        "current_status": current_status,
        "current_referrer": current_referrer,
        "current_advisor": current_advisor,
        "current_manager": current_manager,
        "current_office": current_office,

        "qs_keep": qs_keep,
    }
    return render(request, "leads/my_leads.html", context)


@login_required
def lead_create(request):
    user: User = request.user

    if user.role not in (User.Role.REFERRER, User.Role.ADVISOR, User.Role.OFFICE):
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
    tracked_fields = ["client_name", "client_phone", "client_email", "description", "communication_status", "advisor"]
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
                "advisor": "Poradce",
            }

            status_changed = False
            status_labels = dict(Lead.CommunicationStatus.choices)

            for field in tracked_fields:
                old = old_values[field]
                new = getattr(updated_lead, field)
                if old != new:
                    # U poznámky nedává smysl vypisovat celý text
                    if field == "description":
                        changes.append("Změněn popis situace.")
                    elif field == "communication_status":
                        old_label = status_labels.get(old, old or "—")
                        new_label = status_labels.get(new, new or "—")
                        changes.append(f"Změněn stav leadu: {old_label} → {new_label}")
                        status_changed = True
                    else:
                        changes.append(f"Změněno {labels[field]}: {old or '—'} → {new or '—'}")

            if changes:
                # Pokud poradce přidal extra poznámku, uložíme ji jako LeadNote
                extra_note = form.cleaned_data.get("extra_note")
                if extra_note:
                    LeadNote.objects.create(
                        lead=updated_lead,
                        author=user,
                        text=extra_note,
                    )
                    # vytvoříme log události NOTE_ADDED
                    LeadHistory.objects.create(
                        lead=updated_lead,
                        event_type=LeadHistory.EventType.NOTE_ADDED,
                        user=user,
                        description=f"Přidána poznámka ke změně stavu.",
                    )
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
    user: User = request.user

    qs = Deal.objects.select_related(
        "lead",
        "lead__referrer",
        "lead__advisor",
        "lead__referrer__referrer_profile__manager",
        "lead__referrer__referrer_profile__manager__manager_profile__office",
    )

    # přístup stejně jako leady (podle leadu)
    if user.is_superuser or user.role == User.Role.ADMIN:
        pass
    elif user.role == User.Role.ADVISOR:
        qs = qs.filter(lead__advisor=user)
    elif user.role == User.Role.REFERRER:
        qs = qs.filter(lead__referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        qs = qs.filter(lead__referrer__referrer_profile__manager=user).distinct()
    elif user.role == User.Role.OFFICE:
        qs = qs.filter(
            Q(lead__referrer__referrer_profile__manager__manager_profile__office__owner=user)
            | Q(lead__referrer=user)
        ).distinct()
    else:
        return HttpResponseForbidden("Nemáš oprávnění zobrazit obchody.")

    qs = qs.order_by("-created_at")

    # pro šablonu si připravíme helper hodnoty (bez rizika padání v template)
    deals = []
    for d in qs:
        rp = getattr(d.lead.referrer, "referrer_profile", None)
        manager = getattr(rp, "manager", None) if rp else None
        office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None

        d.referrer_name = str(d.lead.referrer)
        d.manager_name = str(manager) if manager else None
        d.office_name = office.name if office else None
        d.advisor_name = str(d.lead.advisor) if d.lead.advisor else None
        deals.append(d)

    return render(request, "leads/deals_list.html", {"deals": deals})


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

@login_required
def lead_schedule_meeting(request, pk: int):
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    # jen poradce (a admin/superuser)
    if not (user.is_superuser or user.role == User.Role.ADMIN or user.role == User.Role.ADVISOR):
        return HttpResponseForbidden("Nemáš oprávnění domluvit schůzku.")

    if request.method == "POST":
        form = LeadMeetingForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)

            # změna stavu
            lead.communication_status = Lead.CommunicationStatus.MEETING
            lead.save(update_fields=["meeting_at", "meeting_note", "communication_status", "updated_at"])

            # historie
            when = timezone.localtime(lead.meeting_at).strftime("%d.%m.%Y %H:%M") if lead.meeting_at else "—"
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.MEETING_SCHEDULED,
                user=user,
                description=f"Domluvena schůzka na {when}.",
            )

            # pokud chceš mít poznámku i v seznamu poznámek (doporučuji)
            if lead.meeting_note:
                LeadNote.objects.create(
                    lead=lead,
                    author=user,
                    text=f"Schůzka: {lead.meeting_note}",
                )
                LeadHistory.objects.create(
                    lead=lead,
                    event_type=LeadHistory.EventType.NOTE_ADDED,
                    user=user,
                    description="Přidána poznámka ke schůzce.",
                )

            return redirect("lead_detail", pk=lead.pk)
    else:
        form = LeadMeetingForm(instance=lead)

    return render(request, "leads/lead_meeting_form.html", {"lead": lead, "form": form})


@login_required
def overview(request):
    user: User = request.user

    # Vezmeme stejný "base" přístup jako v my_leads
    leads_qs = Lead.objects.none()

    if user.is_superuser or user.role == User.Role.ADMIN:
        leads_qs = Lead.objects.all()
    elif user.role == User.Role.ADVISOR:
        leads_qs = Lead.objects.filter(advisor=user)
    elif user.role == User.Role.REFERRER:
        leads_qs = Lead.objects.filter(referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        leads_qs = Lead.objects.filter(referrer__referrer_profile__manager=user).distinct()
    elif user.role == User.Role.OFFICE:
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager__manager_profile__office__owner=user) | Q(referrer=user)
        ).distinct()

    leads_qs = leads_qs.select_related(
        "referrer",
        "advisor",
        "referrer__referrer_profile__manager",
        "referrer__referrer_profile__manager__manager_profile__office",
    )

    # 1) Schůzky – jen leady se schůzkou (ať už jsou ve stavu MEETING nebo i později, pokud chceš)
    meetings = (
        leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING, meeting_at__isnull=False)
    )

    # 2) Nové leady – pouze stav NEW
    new_leads = (
        leads_qs.filter(communication_status=Lead.CommunicationStatus.NEW)
        .order_by("-created_at")[:20]
    )

    # 3) Obchody – placeholder
    deals_placeholder = True

    context = {
        "meetings": meetings,
        "new_leads": new_leads,
        "deals_placeholder": deals_placeholder,
    }
    return render(request, "leads/overview.html", context)

@login_required
def deal_create_from_lead(request, pk: int):
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    # jen poradce (+ admin/superuser)
    if not (user.is_superuser or user.role == User.Role.ADMIN or user.role == User.Role.ADVISOR):
        return HttpResponseForbidden("Nemáš oprávnění založit obchod.")

    # pokud už obchod existuje, pošli rovnou do seznamu nebo detailu (zatím do seznamu)
    if hasattr(lead, "deal"):
        return redirect("deals_list")

    if request.method == "POST":
        form = DealCreateForm(request.POST, lead=lead)
        if form.is_valid():
            deal = form.save(commit=False)
            deal.lead = lead

            # kopie klienta z leadu (protože pole jsou disabled)
            deal.client_name = lead.client_name
            deal.client_phone = lead.client_phone
            deal.client_email = lead.client_email
            deal.save()

            # Lead -> stav Založen obchod
            lead.communication_status = Lead.CommunicationStatus.DEAL_CREATED
            lead.save(update_fields=["communication_status", "updated_at"])

            # historie
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.DEAL_CREATED,
                user=user,
                description="Založen obchod.",
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.STATUS_CHANGED,
                user=user,
                description="Změněn stav leadu: → Založen obchod",
            )

            return redirect("deals_list")
    else:
        form = DealCreateForm(lead=lead)

    return render(request, "leads/deal_form.html", {"lead": lead, "form": form})
