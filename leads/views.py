from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponseForbidden
from accounts.models import ReferrerProfile, Office
from django.shortcuts import render, redirect, get_object_or_404
from .models import Lead, LeadNote, LeadHistory, Deal
from .forms import LeadForm, LeadNoteForm, LeadMeetingForm, DealCreateForm, DealEditForm, MeetingResultForm
from django.db.models import Q, Count
from django.utils.http import urlencode
from django.utils import timezone
from .services import notifications


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
            qs.filter(
                Q(referrer__referrer_profile__manager=user) | Q(referrer=user)
            ),
            pk=pk,
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

def get_deal_for_user_or_404(user, pk: int) -> Deal:
    qs = Deal.objects.select_related(
        "lead",
        "lead__referrer",
        "lead__advisor",
        "lead__referrer__referrer_profile__manager",
        "lead__referrer__referrer_profile__manager__manager_profile__office",
    )

    deal = get_object_or_404(qs, pk=pk)
    # práva řešíme přes lead (už máš get_lead_for_user_or_404)
    _ = get_lead_for_user_or_404(user, deal.lead_id)
    return deal


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
            Q(referrer__referrer_profile__manager=user) | Q(referrer=user)
        ).distinct()

    elif user.role == User.Role.OFFICE:
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager__manager_profile__office__owner=user)
            | Q(referrer=user)
        ).distinct()

    # --- base queryset (na options do filtrů) ---
    base_leads_qs = leads_qs

    # pouze pro doporučitele: má smysl ukazovat sloupec/filtr poradce jen když existuje více poradců
    referrer_has_multiple_advisors = False
    if user.role == User.Role.REFERRER:
        advisor_ids = (
            base_leads_qs.exclude(advisor__isnull=True)
            .values_list("advisor_id", flat=True)
            .distinct()
        )
        referrer_has_multiple_advisors = advisor_ids.count() > 1

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

    if user.role == User.Role.REFERRER and not referrer_has_multiple_advisors:
        allowed.discard("advisor")

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

    is_admin_like = user.is_superuser or user.role == User.Role.ADMIN
    show_referrer_col = is_admin_like or user.role in (User.Role.REFERRER_MANAGER, User.Role.OFFICE, User.Role.ADVISOR)
    show_manager_col = is_admin_like or user.role in (User.Role.OFFICE, User.Role.ADVISOR)
    show_office_col = is_admin_like or user.role in (User.Role.ADVISOR,)
    show_advisor_col = (
            is_admin_like
            or user.role == User.Role.ADVISOR
            or (user.role == User.Role.REFERRER and referrer_has_multiple_advisors)
    )

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

        "show_referrer_col": show_referrer_col,
        "show_manager_col": show_manager_col,
        "show_office_col": show_office_col,
        "show_advisor_col": show_advisor_col,

        "qs_keep": qs_keep,
    }
    return render(request, "leads/my_leads.html", context)


@login_required
def lead_create(request):
    user: User = request.user

    if user.role not in (User.Role.REFERRER, User.Role.ADVISOR, User.Role.OFFICE, User.Role.REFERRER_MANAGER):
        return HttpResponseForbidden("Nemáš oprávnění vytvářet leady.")

    if request.method == "POST":
        form = LeadForm(request.POST, user=user)
        if form.is_valid():
            lead = form.save(commit=False)

            if user.role == User.Role.REFERRER:
                lead.referrer = user

            elif user.role == User.Role.ADVISOR:
                lead.advisor = user

            elif user.role == User.Role.REFERRER_MANAGER:
                # Manažer může vybírat za koho lead zakládá
                # Pokud nevybral, nastaví se on sám (default z formu)
                if not lead.referrer_id:
                    lead.referrer = user

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

            # Notifikace
            notifications.notify_lead_created(lead, created_by=user)

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

            # Notifikace
            notifications.notify_note_added(lead, note, added_by=user)

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

                # Notifikace
                notifications.notify_lead_updated(updated_lead, updated_by=user, changes_description="; ".join(changes))

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
        qs = qs.filter(
            Q(lead__referrer__referrer_profile__manager=user) | Q(lead__referrer=user)
        ).distinct()
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

    # Vidí: poradce, admin, manažer doporučitelů, kancelář, superuser
    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE]):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit doporučitele.")

    from accounts.models import ReferrerProfile

    queryset = (
        ReferrerProfile.objects
        .select_related("user", "manager")
        .prefetch_related("advisors")
        .annotate(
            leads_sent=Count("user__leads_created", distinct=True),
            meetings_planned=Count(
                "user__leads_created",
                filter=Q(user__leads_created__communication_status=Lead.CommunicationStatus.MEETING),
                distinct=True,
            ),
            meetings_done=Count(
                "user__leads_created",
                filter=Q(user__leads_created__meeting_done=True),
                distinct=True,
            ),
            deals_done=Count(
                "user__leads_created__deal",
                filter=Q(user__leads_created__deal__status=Deal.DealStatus.DRAWN),
                distinct=True,
            ),
        )
    )

    # Poradce vidí jen „svoje" doporučitele
    if user.role == User.Role.ADVISOR and not user.is_superuser:
        queryset = queryset.filter(advisors=user)

    # Manažer vidí svoje doporučitele
    if user.role == User.Role.REFERRER_MANAGER and not user.is_superuser:
        queryset = queryset.filter(manager=user)

    # Kancelář vidí doporučitele pod svými manažery
    if user.role == User.Role.OFFICE and not user.is_superuser:
        queryset = queryset.filter(manager__manager_profile__office__owner=user)

    context = {
        "referrer_profiles": queryset,
    }
    return render(request, "leads/referrers_list.html", context)

@login_required
def referrer_detail(request, pk: int):
    user: User = request.user

    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE]):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit detail doporučitele.")

    profile = get_object_or_404(
        ReferrerProfile.objects.select_related("user", "manager", "manager__manager_profile__office").prefetch_related("advisors"),
        pk=pk,
    )

    # Omezení přístupu:
    # - Advisor jen pokud je v profile.advisors
    if user.role == User.Role.ADVISOR and not user.is_superuser and not profile.advisors.filter(id=user.id).exists():
        return HttpResponseForbidden("Nemáš oprávnění zobrazit detail tohoto doporučitele.")

    # - Manažer jen pokud je to jeho doporučitel
    if user.role == User.Role.REFERRER_MANAGER and not user.is_superuser and profile.manager_id != user.id:
        return HttpResponseForbidden("Nemáš oprávnění zobrazit detail tohoto doporučitele.")

    # - Kancelář jen pokud je doporučitel pod jejími manažery
    if user.role == User.Role.OFFICE and not user.is_superuser:
        manager_profile = getattr(profile.manager, "manager_profile", None) if profile.manager else None
        office = getattr(manager_profile, "office", None) if manager_profile else None
        if not office or office.owner_id != user.id:
            return HttpResponseForbidden("Nemáš oprávnění zobrazit detail tohoto doporučitele.")

    # Statistika pro konkrétního doporučitele
    leads_qs = Lead.objects.filter(referrer=profile.user)

    stats = {
        "leads_sent": leads_qs.count(),
        "meetings_planned": leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
        "meetings_done": leads_qs.filter(meeting_done=True).count(),
        "deals_done": Deal.objects.filter(lead__in=leads_qs, status=Deal.DealStatus.DRAWN).count(),
    }

    return render(request, "leads/referrer_detail.html", {"profile": profile, "stats": stats})


@login_required
def advisors_list(request):
    """Seznam poradců se statistikami"""
    user: User = request.user

    # Vidí: doporučitel, manažer, kancelář, admin, superuser
    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.REFERRER, User.Role.REFERRER_MANAGER, User.Role.OFFICE]):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit poradce.")

    # Základní queryset všech poradců se statistikami
    queryset = (
        User.objects
        .filter(role=User.Role.ADVISOR)
        .annotate(
            leads_received=Count("leads_assigned", distinct=True),
            meetings_planned=Count(
                "leads_assigned",
                filter=Q(leads_assigned__communication_status=Lead.CommunicationStatus.MEETING),
                distinct=True,
            ),
            meetings_done=Count(
                "leads_assigned",
                filter=Q(leads_assigned__meeting_done=True),
                distinct=True,
            ),
            deals_created=Count(
                "leads_assigned__deal",
                distinct=True,
            ),
            deals_completed=Count(
                "leads_assigned__deal",
                filter=Q(leads_assigned__deal__status=Deal.DealStatus.DRAWN),
                distinct=True,
            ),
        )
    )

    # Filtrování podle role
    if user.role == User.Role.REFERRER and not user.is_superuser:
        # Doporučitel vidí jen své přiřazené poradce
        profile = getattr(user, "referrer_profile", None)
        if profile:
            queryset = queryset.filter(id__in=profile.advisors.values_list("id", flat=True))
        else:
            queryset = queryset.none()

    elif user.role == User.Role.REFERRER_MANAGER and not user.is_superuser:
        # Manažer vidí poradce přiřazené k jeho doporučitelům
        referrer_profiles = ReferrerProfile.objects.filter(manager=user)
        advisor_ids = referrer_profiles.values_list("advisors__id", flat=True)
        queryset = queryset.filter(id__in=advisor_ids).distinct()

    elif user.role == User.Role.OFFICE and not user.is_superuser:
        # Kancelář vidí poradce pod svými manažery
        referrer_profiles = ReferrerProfile.objects.filter(manager__manager_profile__office__owner=user)
        advisor_ids = referrer_profiles.values_list("advisors__id", flat=True)
        queryset = queryset.filter(id__in=advisor_ids).distinct()

    # Admin a superuser vidí všechny

    context = {
        "advisors": queryset.order_by("last_name", "first_name", "username"),
    }
    return render(request, "leads/advisors_list.html", context)


@login_required
def advisor_detail(request, pk: int):
    """Detail poradce se statistikami"""
    user: User = request.user

    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.REFERRER, User.Role.REFERRER_MANAGER, User.Role.OFFICE]):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit detail poradce.")

    advisor = get_object_or_404(User, pk=pk, role=User.Role.ADVISOR)

    # Kontrola přístupu podle role
    has_access = False

    if user.is_superuser or user.role == User.Role.ADMIN:
        has_access = True
    elif user.role == User.Role.REFERRER:
        # Doporučitel musí mít tohoto poradce přiřazeného
        profile = getattr(user, "referrer_profile", None)
        if profile and profile.advisors.filter(id=advisor.id).exists():
            has_access = True
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manažer musí mít poradce přiřazeného k některému ze svých doporučitelů
        referrer_profiles = ReferrerProfile.objects.filter(manager=user)
        if referrer_profiles.filter(advisors=advisor).exists():
            has_access = True
    elif user.role == User.Role.OFFICE:
        # Kancelář musí mít poradce pod svými manažery
        referrer_profiles = ReferrerProfile.objects.filter(manager__manager_profile__office__owner=user)
        if referrer_profiles.filter(advisors=advisor).exists():
            has_access = True

    if not has_access:
        return HttpResponseForbidden("Nemáš oprávnění zobrazit detail tohoto poradce.")

    # Statistiky pro konkrétního poradce
    leads_qs = Lead.objects.filter(advisor=advisor)

    stats = {
        "leads_received": leads_qs.count(),
        "meetings_planned": leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
        "meetings_done": leads_qs.filter(meeting_done=True).count(),
        "deals_created": Deal.objects.filter(lead__advisor=advisor).count(),
        "deals_completed": Deal.objects.filter(lead__advisor=advisor, status=Deal.DealStatus.DRAWN).count(),
    }

    return render(request, "leads/advisor_detail.html", {"advisor": advisor, "stats": stats})


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

            # Notifikace
            notifications.notify_meeting_scheduled(lead, scheduled_by=user)

            return redirect("lead_detail", pk=lead.pk)
    else:
        form = LeadMeetingForm(instance=lead)

    return render(request, "leads/lead_meeting_form.html", {"lead": lead, "form": form})


@login_required
def lead_meeting_completed(request, pk: int):
    """View pro oznámení že schůzka proběhla"""
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    # jen poradce (a admin/superuser)
    if not (user.is_superuser or user.role == User.Role.ADMIN or user.role == User.Role.ADVISOR):
        return HttpResponseForbidden("Nemáš oprávnění měnit stav schůzky.")

    # kontrola že lead je ve stavu MEETING
    if lead.communication_status != Lead.CommunicationStatus.MEETING:
        return HttpResponseForbidden("Lead není ve stavu domluvené schůzky.")

    if request.method == "POST":
        form = MeetingResultForm(request.POST)
        if form.is_valid():
            next_action = form.cleaned_data.get("next_action")
            result_note = form.cleaned_data.get("result_note", "").strip()

            # nastavíme meeting_done na True
            lead.meeting_done = True
            lead.meeting_done_at = timezone.now()

            # změníme stav podle vybrané akce
            if next_action == "CREATE_DEAL":
                # Pro založení obchodu jen označíme schůzku jako proběhlou
                # Stav se automaticky změní na DEAL_CREATED při vytvoření dealu
                lead.save(update_fields=["meeting_done", "meeting_done_at", "updated_at"])
            elif next_action in ["SEARCHING_PROPERTY", "WAITING_FOR_CLIENT", "FAILED"]:
                # Nastavíme nový stav
                lead.communication_status = next_action
                lead.save(update_fields=["meeting_done", "meeting_done_at", "communication_status", "updated_at"])

            # přidáme poznámku pokud je vyplněna
            if result_note:
                LeadNote.objects.create(
                    lead=lead,
                    author=user,
                    text=f"Výsledek schůzky: {result_note}",
                )
                LeadHistory.objects.create(
                    lead=lead,
                    event_type=LeadHistory.EventType.NOTE_ADDED,
                    user=user,
                    description="Přidána poznámka k výsledku schůzky.",
                )

            # historie
            action_labels = {
                "SEARCHING_PROPERTY": "Hledá nemovitost",
                "WAITING_FOR_CLIENT": "Čekání na klienta",
                "FAILED": "Neúspěšný",
                "CREATE_DEAL": "Založit obchod",
            }
            action_label = action_labels.get(next_action, next_action)
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.STATUS_CHANGED,
                user=user,
                description=f"Schůzka proběhla. Další krok: {action_label}",
            )

            # Notifikace
            notifications.notify_meeting_completed(lead, completed_by=user, next_action=action_label)

            # přesměrování podle akce
            if next_action == "CREATE_DEAL":
                return redirect("deal_create_from_lead", pk=lead.pk)
            else:
                return redirect("lead_detail", pk=lead.pk)
    else:
        form = MeetingResultForm()

    return render(request, "leads/lead_meeting_result_form.html", {"lead": lead, "form": form})


@login_required
def lead_meeting_cancelled(request, pk: int):
    """View pro zrušení schůzky - změní stav na FAILED"""
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    # jen poradce (a admin/superuser)
    if not (user.is_superuser or user.role == User.Role.ADMIN or user.role == User.Role.ADVISOR):
        return HttpResponseForbidden("Nemáš oprávnění měnit stav leadu.")

    # kontrola že lead je ve stavu MEETING
    if lead.communication_status != Lead.CommunicationStatus.MEETING:
        return HttpResponseForbidden("Lead není ve stavu domluvené schůzky.")

    if request.method == "POST":
        # získáme poznámku
        cancel_note = request.POST.get("cancel_note", "").strip()

        # změníme stav na FAILED
        lead.communication_status = Lead.CommunicationStatus.FAILED
        lead.save(update_fields=["communication_status", "updated_at"])

        # přidáme poznámku pokud je vyplněna
        if cancel_note:
            LeadNote.objects.create(
                lead=lead,
                author=user,
                text=f"Schůzka zrušena: {cancel_note}",
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.NOTE_ADDED,
                user=user,
                description="Přidána poznámka ke zrušení schůzky.",
            )

        # historie
        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.STATUS_CHANGED,
            user=user,
            description="Schůzka zrušena, lead označen jako neúspěšný.",
        )

        return redirect("lead_detail", pk=lead.pk)

    # GET request - zobrazíme potvrzovací stránku
    return render(request, "leads/lead_meeting_cancel_form.html", {"lead": lead})


@login_required
def overview(request):
    user: User = request.user

    # Base přístup (stejně jako my_leads)
    leads_qs = Lead.objects.none()

    if user.is_superuser or user.role == User.Role.ADMIN:
        leads_qs = Lead.objects.all()
    elif user.role == User.Role.ADVISOR:
        leads_qs = Lead.objects.filter(advisor=user)
    elif user.role == User.Role.REFERRER:
        leads_qs = Lead.objects.filter(referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager=user) | Q(referrer=user)
        ).distinct()
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

    # Meetings – domluvené schůzky
    meetings = (
        leads_qs.filter(
            communication_status=Lead.CommunicationStatus.MEETING,
            meeting_at__isnull=False,
        )
        .order_by("meeting_at")[:20]
    )

    # Nové leady
    new_leads = (
        leads_qs.filter(communication_status=Lead.CommunicationStatus.NEW)
        .order_by("-created_at")[:20]
    )

    # Běžící obchody – jen ty, které už existují a nejsou "Načerpáno"
    deals_qs = Deal.objects.select_related(
        "lead",
        "lead__referrer",
        "lead__advisor",
        "lead__referrer__referrer_profile__manager",
        "lead__referrer__referrer_profile__manager__manager_profile__office",
    )

    # stejné oprávnění jako u leadů (přes lead)
    if user.is_superuser or user.role == User.Role.ADMIN:
        pass
    elif user.role == User.Role.ADVISOR:
        deals_qs = deals_qs.filter(lead__advisor=user)
    elif user.role == User.Role.REFERRER:
        deals_qs = deals_qs.filter(lead__referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        deals_qs = deals_qs.filter(lead__referrer__referrer_profile__manager=user).distinct()
    elif user.role == User.Role.OFFICE:
        deals_qs = deals_qs.filter(
            Q(lead__referrer__referrer_profile__manager__manager_profile__office__owner=user)
            | Q(lead__referrer=user)
        ).distinct()
    else:
        deals_qs = Deal.objects.none()

    deals = (
        deals_qs.exclude(status=Deal.DealStatus.DRAWN)
        .order_by("-created_at")[:20]
    )

    # --- sloupce podle role (stejně jako v tabulce leadů) ---
    show_referrer = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE]
    show_advisor = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.REFERRER, User.Role.REFERRER_MANAGER, User.Role.OFFICE]
    show_manager = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.OFFICE]
    show_office = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]

    context = {
        "meetings": meetings,
        "new_leads": new_leads,
        "deals": deals,

        "show_referrer": show_referrer,
        "show_advisor": show_advisor,
        "show_manager": show_manager,
        "show_office": show_office,
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

            # Notifikace
            notifications.notify_deal_created(deal, lead, created_by=user)

            return redirect("deals_list")
    else:
        form = DealCreateForm(lead=lead)

    return render(request, "leads/deal_form.html", {"lead": lead, "form": form})


@login_required
def deal_detail(request, pk: int):
    user: User = request.user
    deal = get_deal_for_user_or_404(user, pk)
    lead = deal.lead

    # poznámky a historie jsou z leadu
    notes = lead.notes.select_related("author")
    history = lead.history.select_related("user")

    # role-based viditelnost údajů
    show_referrer = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE]
    show_manager = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.OFFICE]
    show_office = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]

    # provize celkem vidí všichni kromě doporučitele
    show_commission_total = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE]

    # tlačítka vyplácení: jen poradce + admin
    can_manage_commission = user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]

    # informace o manager/office (kvůli ikonám)
    rp = getattr(lead.referrer, "referrer_profile", None)
    manager = getattr(rp, "manager", None) if rp else None
    office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None

    has_manager = manager is not None
    has_office = office is not None

    # přidání poznámky (LeadNote)
    if request.method == "POST":
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
                description="Přidána poznámka (z detailu obchodu).",
            )

            # Notifikace
            notifications.notify_note_added(lead, note, added_by=user)

            return redirect("deal_detail", pk=deal.pk)
    else:
        note_form = LeadNoteForm()

    context = {
        "deal": deal,
        "lead": lead,
        "notes": notes,
        "history": history,
        "note_form": note_form,

        "show_referrer": show_referrer,
        "show_manager": show_manager,
        "show_office": show_office,
        "show_commission_total": show_commission_total,
        "can_manage_commission": can_manage_commission,
        "has_manager": has_manager,
        "has_office": has_office,
    }
    return render(request, "leads/deal_detail.html", context)


@login_required
def deal_commission_ready(request, pk: int):
    if request.method != "POST":
        return HttpResponseForbidden("Použij POST.")

    user: User = request.user
    deal = get_deal_for_user_or_404(user, pk)

    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]):
        return HttpResponseForbidden("Nemáš oprávnění měnit provizi.")

    if deal.commission_status != Deal.CommissionStatus.READY:
        deal.commission_status = Deal.CommissionStatus.READY
        deal.save(update_fields=["commission_status"])

        LeadHistory.objects.create(
            lead=deal.lead,
            event_type=LeadHistory.EventType.UPDATED,
            user=user,
            description="Provize nastavena na: připravená k vyplacení.",
        )

        # Notifikace
        notifications.notify_commission_ready(deal, marked_by=user)

    return redirect("deal_detail", pk=deal.pk)


@login_required
def deal_commission_paid(request, pk: int, part: str):
    if request.method != "POST":
        return HttpResponseForbidden("Použij POST.")

    user: User = request.user
    deal = get_deal_for_user_or_404(user, pk)
    lead = deal.lead

    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]):
        return HttpResponseForbidden("Nemáš oprávnění měnit provizi.")

    rp = getattr(lead.referrer, "referrer_profile", None)
    manager = getattr(rp, "manager", None) if rp else None
    office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None

    has_manager = manager is not None
    has_office = office is not None

    changes = []

    if part == "referrer":
        if not deal.paid_referrer:
            deal.paid_referrer = True
            changes.append("Vyplaceno makléři")
    elif part == "manager":
        if not has_manager:
            return HttpResponseForbidden("Tento obchod nemá manažera.")
        if not deal.paid_manager:
            deal.paid_manager = True
            changes.append("Vyplaceno manažerovi")
    elif part == "office":
        if not has_office:
            return HttpResponseForbidden("Tento obchod nemá kancelář.")
        if not deal.paid_office:
            deal.paid_office = True
            changes.append("Vyplaceno kanceláři")
    else:
        return HttpResponseForbidden("Neznámá část provize.")

    # pokud něco změněno, uložit
    if changes:
        # pokud je aspoň něco vyplaceno, nastavíme PAID
        deal.commission_status = Deal.CommissionStatus.PAID
        deal.save(update_fields=["paid_referrer", "paid_manager", "paid_office", "commission_status"])

        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.UPDATED,
            user=user,
            description="; ".join(changes),
        )

        # Notifikace
        notifications.notify_commission_paid(deal, recipient_type=part, marked_by=user)

        # pokud chceš: když jsou vyplacené všechny relevantní části, přepni lead na "Provize vyplacena"
        all_paid = deal.paid_referrer and (deal.paid_manager or not has_manager) and (deal.paid_office or not has_office)
        if all_paid:
            lead.communication_status = Lead.CommunicationStatus.COMMISSION_PAID
            lead.save(update_fields=["communication_status", "updated_at"])
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.STATUS_CHANGED,
                user=user,
                description="Změněn stav leadu: → Provize vyplacena",
            )

    return redirect("deal_detail", pk=deal.pk)


@login_required
def deal_edit(request, pk: int):
    user: User = request.user
    deal = get_deal_for_user_or_404(user, pk)
    lead = deal.lead

    # edit povolíme poradci + admin
    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]):
        return HttpResponseForbidden("Nemáš oprávnění upravit obchod.")

    tracked_deal_fields = ["client_name", "client_phone", "client_email", "loan_amount", "bank", "property_type", "status"]
    old = {f: getattr(deal, f) for f in tracked_deal_fields}
    old_lead = {"client_name": lead.client_name, "client_phone": lead.client_phone, "client_email": lead.client_email}

    if request.method == "POST":
        form = DealEditForm(request.POST, instance=deal)
        if form.is_valid():
            updated = form.save()

            # sync klientských údajů do leadu
            lead.client_name = updated.client_name
            lead.client_phone = updated.client_phone
            lead.client_email = updated.client_email
            lead.save(update_fields=["client_name", "client_phone", "client_email", "updated_at"])

            # historie (do leadu)
            changes = []
            if old["loan_amount"] != updated.loan_amount:
                changes.append(f"Změněna výše úvěru: {old['loan_amount']} → {updated.loan_amount}")
            if old["bank"] != updated.bank:
                changes.append(f"Změněna banka: {deal.Bank(old['bank']).label if old['bank'] else old['bank']} → {updated.get_bank_display()}")
            if old["property_type"] != updated.property_type:
                changes.append(f"Změněna nemovitost: {deal.PropertyType(old['property_type']).label if old['property_type'] else old['property_type']} → {updated.get_property_type_display()}")
            if old["status"] != updated.status:
                changes.append(f"Změněn stav obchodu: {deal.DealStatus(old['status']).label if old['status'] else old['status']} → {updated.get_status_display()}")

            # změna klientských údajů
            if old_lead["client_name"] != lead.client_name:
                changes.append("Změněno jméno klienta (propagováno do leadu).")
            if old_lead["client_phone"] != lead.client_phone:
                changes.append("Změněn telefon klienta (propagováno do leadu).")
            if old_lead["client_email"] != lead.client_email:
                changes.append("Změněn email klienta (propagováno do leadu).")

            if changes:
                LeadHistory.objects.create(
                    lead=lead,
                    event_type=LeadHistory.EventType.UPDATED,
                    user=user,
                    description="; ".join(changes),
                )

                # Notifikace
                notifications.notify_deal_updated(deal, updated_by=user, changes_description="; ".join(changes))

            return redirect("deal_detail", pk=deal.pk)
    else:
        form = DealEditForm(instance=deal)

    return render(request, "leads/deal_form_edit.html", {"deal": deal, "lead": lead, "form": form})
