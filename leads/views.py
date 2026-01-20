from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponseForbidden
from accounts.models import ReferrerProfile, Office
from django.shortcuts import render, redirect, get_object_or_404
from .models import Lead, LeadNote, LeadHistory, Deal
from .forms import LeadForm, LeadNoteForm, LeadMeetingForm, DealCreateForm, DealEditForm, MeetingResultForm, CallbackScheduleForm
from django.db.models import Q, Count, Case, When, IntegerField
from django.utils.http import urlencode
from django.utils import timezone
from datetime import timedelta
from .services import notifications
from .stats_filters import parse_date_filters

User = get_user_model()


def landing_page(request):
    """Landing page pro nepřihlášené uživatele"""
    if request.user.is_authenticated:
        return redirect('overview')
    return render(request, 'leads/landing_page.html')


def get_lead_for_user_or_404(user, pk: int) -> Lead:
    qs = Lead.objects.select_related("referrer", "advisor")

    if user.is_superuser or user.role == User.Role.ADMIN:
        return get_object_or_404(qs, pk=pk)
    elif user.role == User.Role.ADVISOR:
        # Pokud má advisor administrativní přístup, vidí i leady svých podřízených doporučitelů
        if user.has_admin_access:
            return get_object_or_404(
                qs.filter(
                    Q(advisor=user) | Q(referrer__referrer_profile__advisors=user)
                ).distinct(),
                pk=pk,
            )
        else:
            # Bez admin přístupu vidí jen své leady
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
        # Pokud má advisor administrativní přístup, vidí i leady svých podřízených doporučitelů
        if user.has_admin_access:
            # Vidí své leady, leady svých podřízených doporučitelů A vlastní kontakty podřízených advisorů
            leads_qs = Lead.objects.filter(
                Q(advisor=user) |
                Q(referrer__referrer_profile__advisors=user) |
                Q(is_personal_contact=True, advisor__referrer_profile__advisors=user)
            ).distinct()
        else:
            # Bez admin přístupu vidí jen své leady (včetně vlastních kontaktů)
            leads_qs = Lead.objects.filter(advisor=user)

    elif user.role == User.Role.REFERRER:
        leads_qs = Lead.objects.filter(referrer=user)

    elif user.role == User.Role.REFERRER_MANAGER:
        # Manažer nevidí vlastní kontakty poradců
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager=user) | Q(referrer=user)
        ).exclude(is_personal_contact=True).distinct()

    elif user.role == User.Role.OFFICE:
        # Kancelář nevidí vlastní kontakty poradců
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager__manager_profile__office__owner=user)
            | Q(referrer=user)
        ).exclude(is_personal_contact=True).distinct()

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
                # Pokud advisor nemá ID (nebyl vybrán ve formuláři), nastav přihlášeného uživatele
                if not lead.advisor_id:
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

            # 🔽 Pokud je to advisor s ReferrerProfile a vybral advisora, zapamatujeme si ho
            if user.role == User.Role.ADVISOR and lead.advisor_id:
                try:
                    profile = user.referrer_profile
                except ReferrerProfile.DoesNotExist:
                    profile = None

                if profile is not None and lead.advisor_id != user.id:
                    # Zapamatovat jen pokud vybral někoho jiného než sebe
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

    # Filtrování poznámek podle oprávnění
    if user.is_superuser or user.role == User.Role.ADMIN:
        # Admini vidí všechny poznámky
        notes = lead.notes.select_related("author")
    else:
        # Ostatní vidí jen veřejné + vlastní soukromé
        notes = lead.notes.filter(
            Q(is_private=False) | Q(author=user)
        ).select_related("author")

    # Filtrování historie podle oprávnění
    if user.is_superuser or user.role == User.Role.ADMIN:
        # Admini vidí všechny záznamy historie
        history = lead.history.select_related("user")
    else:
        # Ostatní vidí jen záznamy bez poznámky nebo s poznámkou, kterou mají právo vidět
        history = lead.history.filter(
            Q(note__isnull=True) |  # záznamy bez poznámky
            Q(note__is_private=False) |  # záznamy s veřejnou poznámkou
            Q(note__is_private=True, note__author=user)  # záznamy s vlastní soukromou poznámkou
        ).select_related("user")

    can_schedule_meeting = user.role == User.Role.ADVISOR or user.is_superuser
    can_create_deal = user.role == User.Role.ADVISOR or user.is_superuser

    # Oprávnění pro odkládání hovoru: autor, manažer, kancelář, poradce
    can_schedule_callback = False
    if user.is_superuser or user.role == User.Role.ADMIN:
        can_schedule_callback = True
    elif user.role == User.Role.ADVISOR and lead.advisor == user:
        can_schedule_callback = True
    elif user.role == User.Role.REFERRER and lead.referrer == user:
        can_schedule_callback = True
    elif user.role == User.Role.REFERRER_MANAGER:
        if lead.referrer_manager == user:
            can_schedule_callback = True
    elif user.role == User.Role.OFFICE:
        rp = getattr(lead.referrer, "referrer_profile", None)
        manager = getattr(rp, "manager", None) if rp else None
        office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None
        if office and office.owner == user:
            can_schedule_callback = True

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
                description="Přidána soukromá poznámka." if note.is_private else "Přidána poznámka.",
                note=note,
            )

            # Notifikace - pouze pro veřejné poznámky
            if not note.is_private:
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
        "can_schedule_callback": can_schedule_callback,
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
                    note = LeadNote.objects.create(
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
                        note=note,
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
        # Pokud má advisor administrativní přístup, vidí i dealy svých podřízených doporučitelů
        if user.has_admin_access:
            qs = qs.filter(
                Q(lead__advisor=user) | Q(lead__referrer__referrer_profile__advisors=user)
            ).distinct()
        else:
            # Bez admin přístupu vidí jen své dealy
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

    # --- base queryset (na options do filtrů) ---
    base_deals_qs = qs

    # ===== Filtry povolené podle role =====
    allowed_filters = {
        User.Role.REFERRER: {"status", "commission"},
        User.Role.REFERRER_MANAGER: {"status", "commission", "referrer", "advisor"},
        User.Role.OFFICE: {"status", "commission", "referrer", "manager", "advisor"},
        User.Role.ADVISOR: {"status", "commission", "referrer", "manager", "office"},
    }

    if user.is_superuser or user.role == User.Role.ADMIN:
        allowed = {"status", "commission", "referrer", "advisor", "manager", "office"}
    else:
        allowed = allowed_filters.get(user.role, set())

    # ===== Čtení filtrů z GET =====
    current_status = request.GET.get("status") or ""
    current_commission = request.GET.get("commission") or ""
    current_referrer = request.GET.get("referrer") or ""
    current_advisor = request.GET.get("advisor") or ""
    current_manager = request.GET.get("manager") or ""
    current_office = request.GET.get("office") or ""

    # ===== Aplikace filtrů (jen povolené) =====
    if "status" in allowed and current_status:
        qs = qs.filter(status=current_status)

    if "commission" in allowed and current_commission:
        qs = qs.filter(commission_status=current_commission)

    if "referrer" in allowed and current_referrer:
        qs = qs.filter(lead__referrer_id=current_referrer)

    if "advisor" in allowed and current_advisor:
        qs = qs.filter(lead__advisor_id=current_advisor)

    if "manager" in allowed and current_manager:
        if current_manager == "__none__":
            qs = qs.filter(
                Q(lead__referrer__referrer_profile__manager__isnull=True) |
                Q(lead__referrer__referrer_profile__isnull=True)
            )
        else:
            qs = qs.filter(lead__referrer__referrer_profile__manager_id=current_manager)

    if "office" in allowed and current_office:
        if current_office == "__none__":
            qs = qs.filter(
                Q(lead__referrer__referrer_profile__manager__manager_profile__office__isnull=True) |
                Q(lead__referrer__referrer_profile__manager__isnull=True) |
                Q(lead__referrer__referrer_profile__isnull=True)
            )
        else:
            qs = qs.filter(
                lead__referrer__referrer_profile__manager__manager_profile__office_id=current_office
            )

    # ===== ŘAZENÍ =====
    # Přidání custom priority pole pro řazení podle kategorií statusů
    qs = qs.annotate(
        status_priority=Case(
            # Kategorie 1: Nedokončené obchody (priorita 1 - zobrazí se nahoře)
            When(status__in=[
                Deal.DealStatus.REQUEST_IN_BANK,
                Deal.DealStatus.WAITING_FOR_APPRAISAL,
                Deal.DealStatus.PREP_APPROVAL,
                Deal.DealStatus.APPROVAL,
                Deal.DealStatus.SIGN_PLANNING,
            ], then=1),
            # Kategorie 2: Dokončené obchody (priorita 2)
            When(status__in=[
                Deal.DealStatus.SIGNED,
                Deal.DealStatus.SIGNED_NO_PROPERTY,
                Deal.DealStatus.DRAWN,
            ], then=2),
            # Kategorie 3: Neúspěšné obchody (priorita 3 - zobrazí se na konci)
            When(status=Deal.DealStatus.FAILED, then=3),
            default=4,
            output_field=IntegerField(),
        )
    )

    sort = request.GET.get("sort") or "created_at"
    direction = request.GET.get("dir") or "desc"

    sort_mapping = {
        "client": ["lead__client_name"],
        "referrer": ["lead__referrer__last_name", "lead__referrer__first_name"],
        "advisor": ["lead__advisor__last_name", "lead__advisor__first_name"],
        "manager": [
            "lead__referrer__referrer_profile__manager__last_name",
            "lead__referrer__referrer_profile__manager__first_name",
        ],
        "office": [
            "lead__referrer__referrer_profile__manager__manager_profile__office__name",
        ],
        "status": ["status"],
        "commission": ["commission_status"],
        "loan_amount": ["loan_amount"],
        "created_at": ["created_at"],
    }

    if sort not in sort_mapping:
        sort = "created_at"
    if direction not in ["asc", "desc"]:
        direction = "desc"

    order_fields = sort_mapping[sort]
    # Primární řazení podle priority kategorie, sekundárně podle zvoleného pole
    qs = qs.order_by("status_priority", *([("-" + f) for f in order_fields] if direction == "desc" else order_fields))

    # ===== Options do filtrů (vždy jen z base_deals_qs) =====
    status_choices = Deal.DealStatus.choices
    commission_choices = Deal.CommissionStatus.choices

    referrer_options = User.objects.none()
    advisor_options = User.objects.none()
    manager_options = User.objects.none()
    office_options = Office.objects.none()

    if "referrer" in allowed:
        ref_ids = base_deals_qs.values_list("lead__referrer_id", flat=True).distinct()
        referrer_options = User.objects.filter(id__in=ref_ids)

    if "advisor" in allowed:
        adv_ids = base_deals_qs.values_list("lead__advisor_id", flat=True).distinct()
        advisor_options = User.objects.filter(id__in=[x for x in adv_ids if x])

    if "manager" in allowed:
        mgr_ids = base_deals_qs.values_list("lead__referrer__referrer_profile__manager_id", flat=True).distinct()
        manager_options = User.objects.filter(id__in=[x for x in mgr_ids if x])

    if "office" in allowed:
        off_ids = base_deals_qs.values_list(
            "lead__referrer__referrer_profile__manager__manager_profile__office_id",
            flat=True
        ).distinct()
        office_options = Office.objects.filter(id__in=[x for x in off_ids if x])

    # ===== Zachování filtrů při řazení (klik na sloupce) =====
    keep_params = {}
    if "status" in allowed and current_status:
        keep_params["status"] = current_status
    if "commission" in allowed and current_commission:
        keep_params["commission"] = current_commission
    if "referrer" in allowed and current_referrer:
        keep_params["referrer"] = current_referrer
    if "advisor" in allowed and current_advisor:
        keep_params["advisor"] = current_advisor
    if "manager" in allowed and current_manager:
        keep_params["manager"] = current_manager
    if "office" in allowed and current_office:
        keep_params["office"] = current_office

    qs_keep = urlencode(keep_params)

    is_admin_like = user.is_superuser or user.role == User.Role.ADMIN
    show_referrer_col = is_admin_like or user.role in (User.Role.REFERRER_MANAGER, User.Role.OFFICE, User.Role.ADVISOR)
    show_manager_col = is_admin_like or user.role in (User.Role.OFFICE, User.Role.ADVISOR)
    show_office_col = is_admin_like or user.role in (User.Role.ADVISOR,)
    show_advisor_col = is_admin_like or user.role in (User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE)

    # pro šablonu si připravíme helper hodnoty (bez rizika padání v template)
    deals = []
    for d in qs:
        rp = getattr(d.lead.referrer, "referrer_profile", None)
        manager = getattr(rp, "manager", None) if rp else None
        office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None

        d.referrer_name = str(d.lead.referrer)
        d.referrer_id = d.lead.referrer.pk if d.lead.referrer else None
        d.manager_name = str(manager) if manager else None
        d.manager_id = manager.pk if manager else None
        d.office_name = office.name if office else None
        d.office_owner_id = office.owner.pk if office and office.owner else None
        d.advisor_name = str(d.lead.advisor) if d.lead.advisor else None
        d.advisor_id = d.lead.advisor.pk if d.lead.advisor else None

        # Helper pro kontrolu vyplacení provizí relevantních pro aktuálního uživatele
        if user.role == User.Role.REFERRER:
            # Doporučitel sleduje jen svou provizi
            d.user_commissions_paid = d.paid_referrer
        elif user.role == User.Role.REFERRER_MANAGER:
            # Manažer sleduje provizi makléře + svou
            d.user_commissions_paid = d.paid_referrer and (not manager or d.paid_manager)
        elif user.role == User.Role.OFFICE:
            # Kancelář sleduje všechny tři (makléř + manažer + kancelář)
            d.user_commissions_paid = d.all_commissions_paid
        else:
            # Admin/Advisor vidí všechny
            d.user_commissions_paid = d.all_commissions_paid

        deals.append(d)

    context = {
        "deals": deals,
        "current_sort": sort,
        "current_dir": direction,

        # filtry
        "allowed": allowed,
        "status_choices": status_choices,
        "commission_choices": commission_choices,
        "referrer_options": referrer_options,
        "advisor_options": advisor_options,
        "manager_options": manager_options,
        "office_options": office_options,

        "current_status": current_status,
        "current_commission": current_commission,
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

    return render(request, "leads/deals_list.html", context)


@login_required
def referrers_list(request):
    user: User = request.user

    # Vidí: poradce, admin, manažer doporučitelů, kancelář, superuser
    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR, User.Role.REFERRER_MANAGER, User.Role.OFFICE]):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit doporučitele.")

    from accounts.models import ReferrerProfile, Office

    # === ČASOVÉ FILTROVÁNÍ ===
    date_filter = parse_date_filters(request)
    date_from = date_filter['date_from']
    date_to = date_filter['date_to']

    # Q objekty pro časové filtrování leadů
    lead_date_q = Q()
    if date_from:
        lead_date_q &= Q(user__leads_created__created_at__gte=date_from)
    if date_to:
        lead_date_q &= Q(user__leads_created__created_at__lt=date_to + timedelta(days=1))

    # Q objekty pro časové filtrování dealů
    deal_date_q = Q()
    if date_from:
        deal_date_q &= Q(user__leads_created__deal__created_at__gte=date_from)
    if date_to:
        deal_date_q &= Q(user__leads_created__deal__created_at__lt=date_to + timedelta(days=1))

    queryset = (
        ReferrerProfile.objects
        .select_related("user", "manager", "manager__manager_profile__office")
        .prefetch_related("advisors")
        .annotate(
            # Vlastní kontakty (is_personal_contact=True) se nezapočítávají do statistik
            leads_sent=Count(
                "user__leads_created",
                filter=Q(user__leads_created__is_personal_contact=False) & lead_date_q,
                distinct=True
            ),
            meetings_planned=Count(
                "user__leads_created",
                filter=Q(
                    user__leads_created__communication_status=Lead.CommunicationStatus.MEETING,
                    user__leads_created__is_personal_contact=False
                ) & lead_date_q,
                distinct=True,
            ),
            meetings_done=Count(
                "user__leads_created",
                filter=Q(
                    user__leads_created__meeting_done=True,
                    user__leads_created__is_personal_contact=False
                ) & lead_date_q,
                distinct=True,
            ),
            deals_done=Count(
                "user__leads_created__deal",
                filter=Q(
                    user__leads_created__deal__status=Deal.DealStatus.DRAWN,
                    user__leads_created__is_personal_contact=False
                ) & deal_date_q,
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

    # === FILTRY ===
    current_manager = request.GET.get("manager", "")
    current_office = request.GET.get("office", "")

    if current_manager:
        if current_manager == "__none__":
            queryset = queryset.filter(manager__isnull=True)
        else:
            queryset = queryset.filter(manager_id=current_manager)

    if current_office:
        if current_office == "__none__":
            queryset = queryset.filter(manager__manager_profile__office__isnull=True)
        else:
            queryset = queryset.filter(manager__manager_profile__office_id=current_office)

    # === ŘAZENÍ ===
    current_sort = request.GET.get("sort", "referrer")
    current_dir = request.GET.get("dir", "asc")

    sort_mapping = {
        "referrer": "user__last_name" if current_dir == "asc" else "-user__last_name",
        "manager": "manager__last_name" if current_dir == "asc" else "-manager__last_name",
        "office": "manager__manager_profile__office__name" if current_dir == "asc" else "-manager__manager_profile__office__name",
        "leads": "leads_sent" if current_dir == "asc" else "-leads_sent",
        "meetings_planned": "meetings_planned" if current_dir == "asc" else "-meetings_planned",
        "meetings_done": "meetings_done" if current_dir == "asc" else "-meetings_done",
        "deals": "deals_done" if current_dir == "asc" else "-deals_done",
    }

    order_by = sort_mapping.get(current_sort, "user__last_name")
    queryset = queryset.order_by(order_by)

    # === MOŽNOSTI PRO FILTRY ===
    # Manažeři
    manager_qs = User.objects.filter(role=User.Role.REFERRER_MANAGER)
    if user.role == User.Role.OFFICE and not user.is_superuser:
        manager_qs = manager_qs.filter(manager_profile__office__owner=user)
    manager_options = manager_qs.order_by("last_name", "first_name")

    # Kanceláře
    office_qs = Office.objects.all()
    if user.role == User.Role.OFFICE and not user.is_superuser:
        office_qs = office_qs.filter(owner=user)
    office_options = office_qs.order_by("name")

    # Sestavení query stringu bez sort a dir
    qs_keep_parts = []
    if current_manager:
        qs_keep_parts.append(f"manager={current_manager}")
    if current_office:
        qs_keep_parts.append(f"office={current_office}")
    qs_keep = "&".join(qs_keep_parts)

    context = {
        "referrer_profiles": queryset,
        "current_manager": current_manager,
        "current_office": current_office,
        "current_sort": current_sort,
        "current_dir": current_dir,
        "manager_options": manager_options,
        "office_options": office_options,
        "qs_keep": qs_keep,
        "date_filter": date_filter,
    }
    return render(request, "leads/referrers_list.html", context)


@login_required
def advisors_list(request):
    """Seznam poradců se statistikami"""
    user: User = request.user

    # Vidí: doporučitel, manažer, kancelář, admin, superuser
    if not (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.REFERRER, User.Role.REFERRER_MANAGER, User.Role.OFFICE]):
        return HttpResponseForbidden("Nemáš oprávnění zobrazit poradce.")

    # === ČASOVÉ FILTROVÁNÍ ===
    date_filter = parse_date_filters(request)
    date_from = date_filter['date_from']
    date_to = date_filter['date_to']

    # Q objekty pro časové filtrování leadů
    lead_date_q = Q()
    if date_from:
        lead_date_q &= Q(leads_assigned__created_at__gte=date_from)
    if date_to:
        lead_date_q &= Q(leads_assigned__created_at__lt=date_to + timedelta(days=1))

    # Q objekty pro časové filtrování dealů
    deal_date_q = Q()
    if date_from:
        deal_date_q &= Q(leads_assigned__deal__created_at__gte=date_from)
    if date_to:
        deal_date_q &= Q(leads_assigned__deal__created_at__lt=date_to + timedelta(days=1))

    # Vlastní kontakty se NIKDY nezapočítávají do statistik poradců
    # Statistiky mají ukazovat práci s kontakty, které poradce obdržel, ne s vlastními
    queryset = (
        User.objects
        .filter(role=User.Role.ADVISOR)
        .annotate(
            leads_received=Count(
                "leads_assigned",
                filter=Q(leads_assigned__is_personal_contact=False) & lead_date_q,
                distinct=True
            ),
            meetings_planned=Count(
                "leads_assigned",
                filter=Q(
                    leads_assigned__communication_status=Lead.CommunicationStatus.MEETING,
                    leads_assigned__is_personal_contact=False
                ) & lead_date_q,
                distinct=True,
            ),
            meetings_done=Count(
                "leads_assigned",
                filter=Q(
                    leads_assigned__meeting_done=True,
                    leads_assigned__is_personal_contact=False
                ) & lead_date_q,
                distinct=True,
            ),
            deals_created=Count(
                "leads_assigned__deal",
                filter=Q(leads_assigned__is_personal_contact=False) & deal_date_q,
                distinct=True,
            ),
            deals_completed=Count(
                "leads_assigned__deal",
                filter=Q(
                    leads_assigned__deal__status=Deal.DealStatus.DRAWN,
                    leads_assigned__is_personal_contact=False
                ) & deal_date_q,
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
        "date_filter": date_filter,
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

    # === ČASOVÉ FILTROVÁNÍ ===
    date_filter = parse_date_filters(request)
    date_from = date_filter['date_from']
    date_to = date_filter['date_to']

    # Statistiky pro konkrétního poradce
    # DŮLEŽITÉ: Vyloučit vlastní kontakty (kde referrer=advisor a is_personal_contact=True)
    leads_qs = Lead.objects.filter(advisor=advisor).exclude(
        is_personal_contact=True, referrer=advisor
    )
    if date_from:
        leads_qs = leads_qs.filter(created_at__gte=date_from)
    if date_to:
        leads_qs = leads_qs.filter(created_at__lt=date_to + timedelta(days=1))

    advisor_stats = {
        "leads_received": leads_qs.count(),
        # Domluvené schůzky: všechny kde byla NĚKDY domluvena schůzka
        "meetings_planned": leads_qs.filter(meeting_scheduled=True).count(),
        # Realizované schůzky: všechny kde schůzka proběhla
        "meetings_done": leads_qs.filter(meeting_done=True).count(),
    }

    # Pro deals použít časový filtr na Deal.created_at
    # Vyloučit vlastní kontakty
    deals_qs = Deal.objects.filter(lead__advisor=advisor).exclude(
        lead__is_personal_contact=True, lead__referrer=advisor
    )
    if date_from:
        deals_qs = deals_qs.filter(created_at__gte=date_from)
    if date_to:
        deals_qs = deals_qs.filter(created_at__lt=date_to + timedelta(days=1))

    advisor_stats["deals_created"] = deals_qs.count()
    advisor_stats["deals_completed"] = deals_qs.filter(status=Deal.DealStatus.DRAWN).count()

    # Přidat statistiku vlastních obchodů
    personal_deals_qs = Deal.objects.filter(
        lead__advisor=advisor,
        lead__is_personal_contact=True,
        lead__referrer=advisor
    )
    if date_from:
        personal_deals_qs = personal_deals_qs.filter(created_at__gte=date_from)
    if date_to:
        personal_deals_qs = personal_deals_qs.filter(created_at__lt=date_to + timedelta(days=1))

    advisor_stats["deals_created_personal"] = personal_deals_qs.count()
    advisor_stats["deals_completed_personal"] = personal_deals_qs.filter(status=Deal.DealStatus.DRAWN).count()

    # Pokud má poradce také ReferrerProfile, počítáme i statistiky jako doporučitel
    referrer_stats = None
    referrer_profile = getattr(advisor, "referrer_profile", None)
    if referrer_profile:
        referrer_leads_qs = Lead.objects.filter(referrer=advisor)
        if date_from:
            referrer_leads_qs = referrer_leads_qs.filter(created_at__gte=date_from)
        if date_to:
            referrer_leads_qs = referrer_leads_qs.filter(created_at__lt=date_to + timedelta(days=1))

        referrer_stats = {
            "leads_sent": referrer_leads_qs.count(),
            "meetings_planned": referrer_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
            "meetings_done": referrer_leads_qs.filter(meeting_done=True).count(),
        }

        # Deals pro referrera
        referrer_deals_qs = Deal.objects.filter(lead__in=referrer_leads_qs)
        if date_from:
            referrer_deals_qs = referrer_deals_qs.filter(created_at__gte=date_from)
        if date_to:
            referrer_deals_qs = referrer_deals_qs.filter(created_at__lt=date_to + timedelta(days=1))

        referrer_stats["deals_done"] = referrer_deals_qs.filter(status=Deal.DealStatus.DRAWN).count()

    return render(request, "leads/advisor_detail.html", {
        "advisor": advisor,
        "stats": advisor_stats,
        "referrer_stats": referrer_stats,
        "referrer_profile": referrer_profile,
        "date_filter": date_filter,
    })


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
            lead.meeting_scheduled = True  # Označit že schůzka byla domluvena
            lead.save(update_fields=["meeting_at", "meeting_note", "meeting_scheduled", "communication_status", "updated_at"])

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
                note = LeadNote.objects.create(
                    lead=lead,
                    author=user,
                    text=f"Schůzka: {lead.meeting_note}",
                )
                LeadHistory.objects.create(
                    lead=lead,
                    event_type=LeadHistory.EventType.NOTE_ADDED,
                    user=user,
                    description="Přidána poznámka ke schůzce.",
                    note=note,
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
                note = LeadNote.objects.create(
                    lead=lead,
                    author=user,
                    text=f"Výsledek schůzky: {result_note}",
                )
                LeadHistory.objects.create(
                    lead=lead,
                    event_type=LeadHistory.EventType.NOTE_ADDED,
                    user=user,
                    description="Přidána poznámka k výsledku schůzky.",
                    note=note,
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
            note = LeadNote.objects.create(
                lead=lead,
                author=user,
                text=f"Schůzka zrušena: {cancel_note}",
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.NOTE_ADDED,
                user=user,
                description="Přidána poznámka ke zrušení schůzky.",
                note=note,
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
def schedule_callback(request, pk: int):
    """View pro odložení hovoru - lead se nastaví do stavu WAITING_FOR_CLIENT"""
    user: User = request.user
    lead = get_lead_for_user_or_404(user, pk)

    # Oprávnění: autor leadu (referrer), manažer, kancelář, poradce
    can_schedule = False

    if user.is_superuser or user.role == User.Role.ADMIN:
        can_schedule = True
    elif user.role == User.Role.ADVISOR and lead.advisor == user:
        can_schedule = True
    elif user.role == User.Role.REFERRER and lead.referrer == user:
        can_schedule = True
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manažer pokud je manažerem referrera
        if lead.referrer_manager == user:
            can_schedule = True
    elif user.role == User.Role.OFFICE:
        # Kancelář pokud je kanceláří referrera
        rp = getattr(lead.referrer, "referrer_profile", None)
        manager = getattr(rp, "manager", None) if rp else None
        office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None
        if office and office.owner == user:
            can_schedule = True

    if not can_schedule:
        return HttpResponseForbidden("Nemáš oprávnění odložit hovor u tohoto leadu.")

    if request.method == "POST":
        form = CallbackScheduleForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.communication_status = Lead.CommunicationStatus.WAITING_FOR_CLIENT
            lead.save()

            # Přidáme poznámku do historie
            callback_note = form.cleaned_data.get("callback_note", "").strip()
            callback_date = form.cleaned_data["callback_scheduled_date"]

            note_text = f"Hovor odložen na {callback_date.strftime('%d.%m.%Y')}"
            if callback_note:
                note_text += f"\nPoznámka: {callback_note}"

            note = LeadNote.objects.create(
                lead=lead,
                author=user,
                text=note_text,
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.NOTE_ADDED,
                user=user,
                description="Přidána poznámka k odložení hovoru.",
                note=note,
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.STATUS_CHANGED,
                user=user,
                description=f"Hovor odložen na {callback_date.strftime('%d.%m.%Y')}. Stav změněn na 'Čekání na klienta'.",
            )

            return redirect("lead_detail", pk=lead.pk)
    else:
        form = CallbackScheduleForm(instance=lead)

    return render(request, "leads/callback_schedule_form.html", {"lead": lead, "form": form})


@login_required
def overview(request):
    user: User = request.user

    # Base přístup (stejně jako my_leads)
    leads_qs = Lead.objects.none()

    if user.is_superuser or user.role == User.Role.ADMIN:
        leads_qs = Lead.objects.all()
    elif user.role == User.Role.ADVISOR:
        # Pokud má advisor administrativní přístup, vidí i leady svých podřízených doporučitelů
        if user.has_admin_access:
            leads_qs = Lead.objects.filter(
                Q(advisor=user) |
                Q(referrer__referrer_profile__advisors=user) |
                Q(is_personal_contact=True, advisor__referrer_profile__advisors=user)
            ).distinct()
        else:
            # Bez admin přístupu vidí jen své leady (včetně vlastních kontaktů)
            leads_qs = Lead.objects.filter(advisor=user)
    elif user.role == User.Role.REFERRER:
        leads_qs = Lead.objects.filter(referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manažer nevidí vlastní kontakty poradců
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager=user) | Q(referrer=user)
        ).exclude(is_personal_contact=True).distinct()
    elif user.role == User.Role.OFFICE:
        # Kancelář nevidí vlastní kontakty poradců
        leads_qs = Lead.objects.filter(
            Q(referrer__referrer_profile__manager__manager_profile__office__owner=user) | Q(referrer=user)
        ).exclude(is_personal_contact=True).distinct()

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
        # Pokud má advisor administrativní přístup, vidí i dealy svých podřízených doporučitelů
        if user.has_admin_access:
            deals_qs = deals_qs.filter(
                Q(lead__advisor=user) |
                Q(lead__referrer__referrer_profile__advisors=user) |
                Q(lead__is_personal_contact=True, lead__advisor__referrer_profile__advisors=user)
            ).distinct()
        else:
            # Bez admin přístupu vidí jen své dealy (včetně vlastních kontaktů)
            deals_qs = deals_qs.filter(lead__advisor=user)
    elif user.role == User.Role.REFERRER:
        deals_qs = deals_qs.filter(lead__referrer=user)
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manažer nevidí vlastní kontakty poradců
        deals_qs = deals_qs.filter(lead__referrer__referrer_profile__manager=user).exclude(lead__is_personal_contact=True).distinct()
    elif user.role == User.Role.OFFICE:
        # Kancelář nevidí vlastní kontakty poradců
        deals_qs = deals_qs.filter(
            Q(lead__referrer__referrer_profile__manager__manager_profile__office__owner=user)
            | Q(lead__referrer=user)
        ).exclude(lead__is_personal_contact=True).distinct()
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
            # Pokud se vytváří obchod, musela předcházet schůzka (i když nebyla explicitně zaznamenána)
            lead.communication_status = Lead.CommunicationStatus.DEAL_CREATED
            lead.meeting_scheduled = True
            lead.meeting_done = True
            if not lead.meeting_done_at:
                lead.meeting_done_at = timezone.now()
            lead.save(update_fields=["communication_status", "meeting_scheduled", "meeting_done", "meeting_done_at", "updated_at"])

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
    # Filtrování poznámek podle oprávnění
    if user.is_superuser or user.role == User.Role.ADMIN:
        # Admini vidí všechny poznámky
        notes = lead.notes.select_related("author")
    else:
        # Ostatní vidí jen veřejné + vlastní soukromé
        notes = lead.notes.filter(
            Q(is_private=False) | Q(author=user)
        ).select_related("author")

    # Filtrování historie podle oprávnění
    if user.is_superuser or user.role == User.Role.ADMIN:
        # Admini vidí všechny záznamy historie
        history = lead.history.select_related("user")
    else:
        # Ostatní vidí jen záznamy bez poznámky nebo s poznámkou, kterou mají právo vidět
        history = lead.history.filter(
            Q(note__isnull=True) |  # záznamy bez poznámky
            Q(note__is_private=False) |  # záznamy s veřejnou poznámkou
            Q(note__is_private=True, note__author=user)  # záznamy s vlastní soukromou poznámkou
        ).select_related("user")

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

    # zjistit, jestli je referrer manager nebo kancelář
    referrer = lead.referrer
    is_referrer_manager = referrer.role == User.Role.REFERRER_MANAGER
    is_referrer_office = referrer.role == User.Role.OFFICE

    # vlastní provize pro přihlášeného uživatele
    user_own_commission = deal.get_own_commission(user)

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
                description="Přidána soukromá poznámka (z detailu obchodu)." if note.is_private else "Přidána poznámka (z detailu obchodu).",
                note=note,
            )

            # Notifikace - pouze pro veřejné poznámky
            if not note.is_private:
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

        # nové proměnné pro zobrazení provizí
        "is_referrer_manager": is_referrer_manager,
        "is_referrer_office": is_referrer_office,
        "user_own_commission": user_own_commission,
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


@login_required
def user_detail(request, pk: int):
    """
    Detail uživatele - zobrazí info podle role (doporučitel, manažer, kancelář, poradce)
    """
    user: User = request.user
    viewed_user = get_object_or_404(User, pk=pk)

    # Všichni přihlášení uživatelé mohou vidět profily všech
    # Tlačítka pro úpravy jsou v šabloně zobrazena jen když user == viewed_user

    # === ČASOVÉ FILTROVÁNÍ ===
    date_filter = parse_date_filters(request)
    date_from = date_filter['date_from']
    date_to = date_filter['date_to']

    # Helper funkce pro aplikaci časového filtru
    def filter_leads_by_date(qs):
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lt=date_to + timedelta(days=1))
        return qs

    def filter_deals_by_date(qs):
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lt=date_to + timedelta(days=1))
        return qs

    # Získat profily pokud existují
    referrer_profile = getattr(viewed_user, "referrer_profile", None)
    manager_profile = getattr(viewed_user, "manager_profile", None)

    # Manažer z ReferrerProfile
    manager = None
    if referrer_profile:
        manager = referrer_profile.manager

    # Kancelář z ManagerProfile
    office = None
    if manager_profile:
        office = manager_profile.office
    elif manager:
        # Pokud má manažera, získat kancelář z něj
        manager_mp = getattr(manager, "manager_profile", None)
        if manager_mp:
            office = manager_mp.office

    # Vypočítat statistiky podle role
    team_stats = None
    office_stats = None
    advisor_stats = None
    referrer_stats = None

    if viewed_user.role == User.Role.ADVISOR:
        # Statistiky poradce
        # DŮLEŽITÉ: Vyloučit vlastní kontakty (kde referrer=advisor a is_personal_contact=True)
        leads_qs = filter_leads_by_date(Lead.objects.filter(advisor=viewed_user).exclude(
            is_personal_contact=True, referrer=viewed_user
        ))
        deals_qs = filter_deals_by_date(Deal.objects.filter(lead__advisor=viewed_user).exclude(
            lead__is_personal_contact=True, lead__referrer=viewed_user
        ))

        advisor_stats = {
            "leads_received": leads_qs.count(),
            # Domluvené schůzky: všechny kde byla NĚKDY domluvena schůzka
            "meetings_planned": leads_qs.filter(meeting_scheduled=True).count(),
            # Realizované schůzky: všechny kde schůzka proběhla
            "meetings_done": leads_qs.filter(meeting_done=True).count(),
            "deals_created": deals_qs.count(),
            "deals_completed": deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
        }

        # Přidat statistiku vlastních obchodů
        personal_deals_qs = filter_deals_by_date(Deal.objects.filter(
            lead__advisor=viewed_user,
            lead__is_personal_contact=True,
            lead__referrer=viewed_user
        ))
        advisor_stats["deals_created_personal"] = personal_deals_qs.count()
        advisor_stats["deals_completed_personal"] = personal_deals_qs.filter(status=Deal.DealStatus.DRAWN).count()

        # Statistiky jako doporučitel (pokud má ReferrerProfile)
        if referrer_profile:
            referrer_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer=viewed_user))
            referrer_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=referrer_leads_qs))

            referrer_stats = {
                "leads_sent": referrer_leads_qs.count(),
                "meetings_planned": referrer_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
                "meetings_done": referrer_leads_qs.filter(meeting_done=True).count(),
                "deals_done": referrer_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
            }

    elif viewed_user.role == User.Role.REFERRER_MANAGER:
        # Statistiky týmu (bez obchodů manažera samotného)
        managed_profiles = ReferrerProfile.objects.filter(manager=viewed_user)
        team_referrer_ids = managed_profiles.values_list("user_id", flat=True)
        team_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer_id__in=team_referrer_ids))
        team_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=team_leads_qs))

        team_stats = {
            "leads_sent": team_leads_qs.count(),
            "meetings_planned": team_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
            "meetings_done": team_leads_qs.filter(meeting_done=True).count(),
            "deals_done": team_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
        }

        # Statistiky jako doporučitel (pokud má ReferrerProfile)
        if referrer_profile:
            referrer_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer=viewed_user))
            referrer_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=referrer_leads_qs))

            referrer_stats = {
                "leads_sent": referrer_leads_qs.count(),
                "meetings_planned": referrer_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
                "meetings_done": referrer_leads_qs.filter(meeting_done=True).count(),
                "deals_done": referrer_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
            }

    elif viewed_user.role == User.Role.OFFICE:
        # Statistiky celé kanceláře (všichni pod kanceláří včetně managed referrers)
        office_referrer_profiles = ReferrerProfile.objects.filter(
            manager__manager_profile__office__owner=viewed_user
        )
        office_referrer_ids = office_referrer_profiles.values_list("user_id", flat=True)
        office_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer_id__in=office_referrer_ids))
        office_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=office_leads_qs))

        office_stats = {
            "leads_sent": office_leads_qs.count(),
            "meetings_planned": office_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
            "meetings_done": office_leads_qs.filter(meeting_done=True).count(),
            "deals_done": office_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
        }

        # Pokud kancelář funguje i jako manažer (má přiřazené doporučitele)
        managed_profiles = ReferrerProfile.objects.filter(manager=viewed_user)
        if managed_profiles.exists():
            team_referrer_ids = managed_profiles.values_list("user_id", flat=True)
            team_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer_id__in=team_referrer_ids))
            team_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=team_leads_qs))

            team_stats = {
                "leads_sent": team_leads_qs.count(),
                "meetings_planned": team_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
                "meetings_done": team_leads_qs.filter(meeting_done=True).count(),
                "deals_done": team_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
            }

        # Statistiky jako doporučitel (pokud má ReferrerProfile)
        if referrer_profile:
            referrer_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer=viewed_user))
            referrer_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=referrer_leads_qs))

            referrer_stats = {
                "leads_sent": referrer_leads_qs.count(),
                "meetings_planned": referrer_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
                "meetings_done": referrer_leads_qs.filter(meeting_done=True).count(),
                "deals_done": referrer_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
            }

    elif viewed_user.role == User.Role.REFERRER:
        # Běžný doporučitel - zobrazit jen jeho statistiky
        if referrer_profile:
            referrer_leads_qs = filter_leads_by_date(Lead.objects.filter(referrer=viewed_user))
            referrer_deals_qs = filter_deals_by_date(Deal.objects.filter(lead__in=referrer_leads_qs))

            referrer_stats = {
                "leads_sent": referrer_leads_qs.count(),
                "meetings_planned": referrer_leads_qs.filter(communication_status=Lead.CommunicationStatus.MEETING).count(),
                "meetings_done": referrer_leads_qs.filter(meeting_done=True).count(),
                "deals_done": referrer_deals_qs.filter(status=Deal.DealStatus.DRAWN).count(),
            }

    context = {
        "viewed_user": viewed_user,
        "referrer_profile": referrer_profile,
        "manager_profile": manager_profile,
        "manager": manager,
        "office": office,
        "office_stats": office_stats,
        "team_stats": team_stats,
        "advisor_stats": advisor_stats,
        "referrer_stats": referrer_stats,
        "date_filter": date_filter,
    }

    return render(request, "leads/user_detail.html", context)


@login_required
def activity_log_list(request):
    """
    Zobrazení logu aktivit - pouze pro superusery.
    Defaultně zobrazuje poslední týden, s možností filtrovat.
    """
    # Pouze superuser může vidět logy aktivit
    if not request.user.is_superuser:
        return HttpResponseForbidden("Nemáte oprávnění k zobrazení logů aktivit.")

    from .models import ActivityLog
    from datetime import datetime, timedelta

    # Získání filtrů z GET parametrů
    user_filter = request.GET.get('user', '')
    activity_type_filter = request.GET.get('activity_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Základní queryset
    activities = ActivityLog.objects.select_related('user', 'lead', 'deal').all()

    # Defaultně zobrazit poslední týden pokud nejsou nastaveny filtry
    if not date_from and not date_to:
        one_week_ago = timezone.now() - timedelta(days=7)
        activities = activities.filter(timestamp__gte=one_week_ago)
        date_from = one_week_ago.date().isoformat()
        date_to = timezone.now().date().isoformat()

    # Aplikace filtrů
    if user_filter:
        activities = activities.filter(user_id=user_filter)

    if activity_type_filter:
        activities = activities.filter(activity_type=activity_type_filter)

    if date_from:
        try:
            date_from_obj = datetime.fromisoformat(date_from)
            activities = activities.filter(timestamp__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.fromisoformat(date_to)
            # Přidat 1 den aby se zahrnul celý den
            date_to_obj = date_to_obj + timedelta(days=1)
            activities = activities.filter(timestamp__lt=date_to_obj)
        except ValueError:
            pass

    # Omezení na 500 záznamů pro výkon
    activities = activities[:500]

    # Získání všech uživatelů pro filtr
    users = User.objects.filter(activity_logs__isnull=False).distinct().order_by('last_name', 'first_name')

    # Typy aktivit pro filtr
    activity_types = ActivityLog.ActivityType.choices

    context = {
        'activities': activities,
        'users': users,
        'activity_types': activity_types,
        'current_user_filter': user_filter,
        'current_activity_type_filter': activity_type_filter,
        'current_date_from': date_from,
        'current_date_to': date_to,
        'total_count': activities.count(),
    }

    return render(request, 'leads/activity_log_list.html', context)
