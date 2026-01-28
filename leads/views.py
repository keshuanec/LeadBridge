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
from .services.access_control import LeadAccessService
from .services.user_stats import UserStatsService
from .services.filters import ListFilterService
from .services.model_helpers import LeadHierarchyHelper
from .services.events import LeadEventService
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

    # Get leads queryset filtered by user role
    leads_qs = LeadAccessService.get_leads_queryset(user)

    # --- base queryset (na options do filtrů) ---
    base_leads_qs = leads_qs

    # Apply select_related optimization
    leads_qs = LeadAccessService.apply_select_related(leads_qs, 'lead')

    # Initialize filter service
    filter_service = ListFilterService(user, request, context='leads')

    # Get allowed filters (with special handling for referrers with single advisor)
    allowed = filter_service.get_allowed_filters(base_queryset=base_leads_qs)

    # Get filter parameters from request
    filter_params = filter_service.get_filter_params()

    # Apply filters to queryset
    leads_qs = filter_service.apply_filters(leads_qs, allowed, filter_params)

    # Apply sorting
    leads_qs, sort, direction = filter_service.apply_sorting(leads_qs)

    # Get filter options for dropdowns
    filter_options = filter_service.get_filter_options(base_leads_qs, allowed)

    # Build query string for preserving filters
    qs_keep = filter_service.build_query_string_keep(allowed, filter_params)

    # Get column visibility from service
    column_visibility = LeadAccessService.get_column_visibility(user, 'leads')

    # Special case: referrers with single advisor don't see advisor column
    referrer_has_multiple_advisors = 'advisor' in allowed and user.role == User.Role.REFERRER
    show_advisor_col = (
        column_visibility['show_advisor']
        or referrer_has_multiple_advisors
    )

    can_create_leads = user.role in [User.Role.REFERRER, User.Role.ADVISOR, User.Role.OFFICE]

    # Process leads for template (add helper attributes like last_note_text)
    leads = filter_service.process_leads_for_template(leads_qs)

    context = {
        "leads": leads,
        "can_create_leads": can_create_leads,
        "current_sort": sort,
        "current_dir": direction,

        # filtry
        "allowed": allowed,
        **filter_options,  # status_choices, referrer_options, advisor_options, etc.

        "current_status": filter_params['status'],
        "current_referrer": filter_params['referrer'],
        "current_advisor": filter_params['advisor'],
        "current_manager": filter_params['manager'],
        "current_office": filter_params['office'],

        "show_referrer_col": column_visibility['show_referrer'],
        "show_manager_col": column_visibility['show_manager'],
        "show_office_col": column_visibility['show_office'],
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

            # Zalogujeme vytvoření leadu a odešleme notifikaci
            LeadEventService.record_lead_created(lead, user)

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

    # Use LeadAccessService for permission checks
    can_schedule_meeting = LeadAccessService.can_schedule_meeting(user, lead)
    can_create_deal = LeadAccessService.can_create_deal(user, lead)
    can_schedule_callback = LeadAccessService.can_schedule_callback(user, lead)

    # Filtrování dealů podle oprávnění
    deals = lead.deals.all()
    if user.role == User.Role.REFERRER:
        # Referrer nevidí personal deals
        deals = deals.exclude(is_personal_deal=True)
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manager nevidí personal deals
        deals = deals.exclude(is_personal_deal=True)
    elif user.role == User.Role.OFFICE:
        # Office nevidí personal deals
        deals = deals.exclude(is_personal_deal=True)
    # ADVISOR a ADMIN vidí všechny dealy

    if request.method == "POST":
        # Přidání poznámky
        note_form = LeadNoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.lead = lead
            note.author = user
            note.save()

            # Zalogujeme přidání poznámky a odešleme notifikaci (pokud veřejná)
            LeadEventService.record_note_added(lead, note, user)

            return redirect("lead_detail", pk=lead.pk)
    else:
        note_form = LeadNoteForm()

    context = {
        "lead": lead,
        "deals": deals,
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
                        description="Přidána poznámka ke změně stavu.",
                        note=note,
                    )

                # Zalogujeme změnu leadu a odešleme notifikaci
                LeadEventService.record_lead_updated(
                    updated_lead,
                    user,
                    "; ".join(changes),
                    status_changed=status_changed
                )

            return redirect("lead_detail", pk=updated_lead.pk)
    else:
        form = LeadForm(user=user, instance=lead)

    return render(request, "leads/lead_form.html", {"form": form, "lead": lead, "is_edit": True})


@login_required
def deals_list(request):
    user: User = request.user

    # Get deals queryset filtered by user role
    qs = LeadAccessService.get_deals_queryset(user)

    # Apply select_related optimization for deals
    qs = LeadAccessService.apply_select_related(qs, 'deal')

    # --- base queryset (na options do filtrů) ---
    base_deals_qs = qs

    # Initialize filter service
    filter_service = ListFilterService(user, request, context='deals')

    # Get allowed filters (includes commission for deals)
    allowed = filter_service.get_allowed_filters()

    # Get filter parameters from request
    filter_params = filter_service.get_filter_params()

    # Apply filters to queryset
    qs = filter_service.apply_filters(qs, allowed, filter_params)

    # Apply sorting (includes status_priority annotation for deals)
    qs, sort, direction = filter_service.apply_sorting(qs)

    # Get filter options for dropdowns
    filter_options = filter_service.get_filter_options(base_deals_qs, allowed)

    # Build query string for preserving filters
    qs_keep = filter_service.build_query_string_keep(allowed, filter_params)

    # Get column visibility from service
    column_visibility = LeadAccessService.get_column_visibility(user, 'deals')

    # Process deals for template (add helper attributes)
    deals = filter_service.process_deals_for_template(qs)

    context = {
        "deals": deals,
        "current_sort": sort,
        "current_dir": direction,

        # filtry
        "allowed": allowed,
        **filter_options,  # status_choices, commission_choices, referrer_options, etc.

        "current_status": filter_params['status'],
        "current_commission": filter_params.get('commission', ''),
        "current_referrer": filter_params['referrer'],
        "current_advisor": filter_params['advisor'],
        "current_manager": filter_params['manager'],
        "current_office": filter_params['office'],

        "show_referrer_col": column_visibility['show_referrer'],
        "show_manager_col": column_visibility['show_manager'],
        "show_office_col": column_visibility['show_office'],
        "show_advisor_col": column_visibility['show_advisor'],

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

    # Get referrers with annotated statistics using UserStatsService
    queryset = UserStatsService.get_referrers_with_stats(date_from, date_to)

    # Select related ReferrerProfile and related fields for template access
    queryset = queryset.select_related(
        'referrer_profile',
        'referrer_profile__manager',
        'referrer_profile__manager__manager_profile__office'
    ).prefetch_related('referrer_profile__advisors')

    # Poradce vidí jen „svoje" doporučitele
    if user.role == User.Role.ADVISOR and not user.is_superuser:
        queryset = queryset.filter(referrer_profile__advisors=user)

    # Manažer vidí svoje doporučitele
    if user.role == User.Role.REFERRER_MANAGER and not user.is_superuser:
        queryset = queryset.filter(referrer_profile__manager=user)

    # Kancelář vidí doporučitele pod svými manažery
    if user.role == User.Role.OFFICE and not user.is_superuser:
        queryset = queryset.filter(referrer_profile__manager__manager_profile__office__owner=user)

    # === FILTRY ===
    current_manager = request.GET.get("manager", "")
    current_office = request.GET.get("office", "")

    if current_manager:
        if current_manager == "__none__":
            queryset = queryset.filter(referrer_profile__manager__isnull=True)
        else:
            queryset = queryset.filter(referrer_profile__manager_id=current_manager)

    if current_office:
        if current_office == "__none__":
            queryset = queryset.filter(referrer_profile__manager__manager_profile__office__isnull=True)
        else:
            queryset = queryset.filter(referrer_profile__manager__manager_profile__office_id=current_office)

    # === ŘAZENÍ ===
    current_sort = request.GET.get("sort", "referrer")
    current_dir = request.GET.get("dir", "asc")

    sort_mapping = {
        "referrer": "last_name" if current_dir == "asc" else "-last_name",
        "manager": "referrer_profile__manager__last_name" if current_dir == "asc" else "-referrer_profile__manager__last_name",
        "office": "referrer_profile__manager__manager_profile__office__name" if current_dir == "asc" else "-referrer_profile__manager__manager_profile__office__name",
        "leads": "leads_sent" if current_dir == "asc" else "-leads_sent",
        "meetings_planned": "meetings_planned" if current_dir == "asc" else "-meetings_planned",
        "meetings_done": "meetings_done" if current_dir == "asc" else "-meetings_done",
        "deals": "deals_done" if current_dir == "asc" else "-deals_done",
    }

    order_by = sort_mapping.get(current_sort, "last_name")
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
        "referrers": queryset,
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

    # Get advisors with annotated statistics using UserStatsService
    queryset = UserStatsService.get_advisors_with_stats(date_from, date_to)

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

    # Get advisor statistics using UserStatsService
    advisor_stats_obj = UserStatsService.get_advisor_stats_detailed(
        advisor, date_from, date_to
    )

    # Convert to dictionary for template compatibility
    advisor_stats = {
        "leads_received": advisor_stats_obj.leads_received,
        "meetings_planned": advisor_stats_obj.meetings_planned,
        "meetings_done": advisor_stats_obj.meetings_done,
        "deals_created": advisor_stats_obj.deals_created,
        "deals_completed": advisor_stats_obj.deals_completed,
        "deals_created_personal": advisor_stats_obj.deals_created_personal,
        "deals_completed_personal": advisor_stats_obj.deals_completed_personal,
    }

    # If advisor also has ReferrerProfile, calculate referrer statistics
    referrer_stats = None
    referrer_profile = getattr(advisor, "referrer_profile", None)
    if referrer_profile:
        referrer_stats_obj = UserStatsService.get_referrer_stats_detailed(
            advisor, date_from, date_to
        )
        referrer_stats = {
            "leads_sent": referrer_stats_obj.leads_sent,
            "meetings_planned": referrer_stats_obj.meetings_planned,
            "meetings_done": referrer_stats_obj.meetings_done,
            "deals_done": referrer_stats_obj.deals_done,
        }

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

            # Zalogujeme naplánování schůzky a odešleme notifikaci
            LeadEventService.record_meeting_scheduled(
                lead,
                user,
                lead.meeting_at,
                lead.meeting_note
            )

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

            # historie a notifikace
            action_labels = {
                "SEARCHING_PROPERTY": "Hledá nemovitost",
                "WAITING_FOR_CLIENT": "Čekání na klienta",
                "FAILED": "Neúspěšný",
                "CREATE_DEAL": "Založit obchod",
            }
            action_label = action_labels.get(next_action, next_action)

            # Zalogujeme dokončení schůzky a odešleme notifikaci
            LeadEventService.record_meeting_completed(
                lead,
                user,
                action_label,
                result_note
            )

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

        # Zalogujeme zrušení schůzky
        LeadEventService.record_meeting_cancelled(lead, user, cancel_note)

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
        helper = LeadHierarchyHelper(lead)
        office = helper.get_office()
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

            # Zalogujeme odložení hovoru
            callback_note = form.cleaned_data.get("callback_note", "").strip()
            callback_date = form.cleaned_data["callback_scheduled_date"]

            LeadEventService.record_callback_scheduled(
                lead,
                user,
                callback_date,
                callback_note
            )

            return redirect("lead_detail", pk=lead.pk)
    else:
        form = CallbackScheduleForm(instance=lead)

    return render(request, "leads/callback_schedule_form.html", {"lead": lead, "form": form})


@login_required
def overview(request):
    user: User = request.user

    # Get leads queryset filtered by user role
    leads_qs = LeadAccessService.get_leads_queryset(user)
    leads_qs = LeadAccessService.apply_select_related(leads_qs, 'lead')

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

    # Get deals queryset filtered by user role
    deals_qs = LeadAccessService.get_deals_queryset(user)
    deals_qs = LeadAccessService.apply_select_related(deals_qs, 'deal')

    deals = (
        deals_qs.exclude(status=Deal.DealStatus.DRAWN)
        .order_by("-created_at")[:20]
    )

    # Get column visibility from service
    column_visibility = LeadAccessService.get_column_visibility(user, 'leads')
    show_referrer = column_visibility['show_referrer']
    show_advisor = column_visibility['show_advisor']
    show_manager = column_visibility['show_manager']
    show_office = column_visibility['show_office']

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

    # Žádná kontrola - vždy povolit vytvoření dalšího dealu
    # (UI zobrazí počet existujících dealů)

    if request.method == "POST":
        form = DealCreateForm(request.POST, lead=lead)
        if form.is_valid():
            deal = form.save(commit=False)
            deal.lead = lead

            # kopie klienta z leadu (protože pole jsou disabled)
            deal.client_first_name = lead.client_first_name
            deal.client_last_name = lead.client_last_name
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

            # Zalogujeme vytvoření obchodu a odešleme notifikaci
            LeadEventService.record_deal_created(deal, lead, user)

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
    helper = LeadHierarchyHelper(lead)
    manager = helper.get_manager()
    office = helper.get_office()

    has_manager = manager is not None
    has_office = office is not None

    # zjistit, jestli je referrer manager nebo kancelář
    referrer = lead.referrer
    is_referrer_manager = referrer.role == User.Role.REFERRER_MANAGER
    is_referrer_office = referrer.role == User.Role.OFFICE

    # vlastní provize pro přihlášeného uživatele
    user_own_commission = deal.get_own_commission(user)

    # Filtrování ostatních dealů podle oprávnění
    other_deals = lead.deals.exclude(pk=deal.pk)
    if user.role == User.Role.REFERRER:
        # Referrer nevidí personal deals
        other_deals = other_deals.exclude(is_personal_deal=True)
    elif user.role == User.Role.REFERRER_MANAGER:
        # Manager nevidí personal deals
        other_deals = other_deals.exclude(is_personal_deal=True)
    elif user.role == User.Role.OFFICE:
        # Office nevidí personal deals
        other_deals = other_deals.exclude(is_personal_deal=True)
    # ADVISOR a ADMIN vidí všechny dealy

    # přidání poznámky (LeadNote)
    if request.method == "POST":
        note_form = LeadNoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.lead = lead
            note.author = user
            note.save()

            # Zalogujeme přidání poznámky a odešleme notifikaci (pokud veřejná)
            LeadEventService.record_note_added(lead, note, user, context=" (z detailu obchodu)")

            return redirect("deal_detail", pk=deal.pk)
    else:
        note_form = LeadNoteForm()

    context = {
        "deal": deal,
        "lead": lead,
        "other_deals": other_deals,
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

        # Zalogujeme změnu stavu provize a odešleme notifikaci
        LeadEventService.record_commission_ready(deal, user)

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

    helper = LeadHierarchyHelper(lead)
    manager = helper.get_manager()
    office = helper.get_office()

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

        # pokud chceš: když jsou vyplacené všechny relevantní části, přepni lead na "Provize vyplacena"
        all_paid = deal.paid_referrer and (deal.paid_manager or not has_manager) and (deal.paid_office or not has_office)
        if all_paid:
            lead.communication_status = Lead.CommunicationStatus.COMMISSION_PAID
            lead.save(update_fields=["communication_status", "updated_at"])

        # Zalogujeme vyplacení provize a odešleme notifikaci
        LeadEventService.record_commission_paid(
            deal,
            user,
            part,
            "; ".join(changes),
            all_paid
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
            lead.client_first_name = updated.client_first_name
            lead.client_last_name = updated.client_last_name
            lead.client_phone = updated.client_phone
            lead.client_email = updated.client_email
            lead.save(update_fields=["client_first_name", "client_last_name", "client_phone", "client_email", "updated_at"])

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
                # Zpracování extra poznámky
                extra_note = form.cleaned_data.get("extra_note")

                # Zalogujeme změnu obchodu a odešleme notifikaci
                LeadEventService.record_deal_updated(
                    deal,
                    user,
                    "; ".join(changes),
                    extra_note
                )

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

    # Získat profily pokud existují
    referrer_profile = getattr(viewed_user, "referrer_profile", None)
    manager_profile = getattr(viewed_user, "manager_profile", None)

    # Use LeadHierarchyHelper for getting manager and office
    helper = LeadHierarchyHelper(viewed_user)
    manager = helper.get_manager()

    # Kancelář z ManagerProfile (pokud je viewed_user manažer) nebo z referrer's managera
    if manager_profile:
        office = manager_profile.office
    else:
        office = helper.get_office()

    # Vypočítat statistiky podle role pomocí UserStatsService
    team_stats = None
    office_stats = None
    advisor_stats = None
    referrer_stats = None

    if viewed_user.role == User.Role.ADVISOR:
        # Get advisor statistics using UserStatsService
        advisor_stats_obj = UserStatsService.get_advisor_stats_detailed(
            viewed_user, date_from, date_to
        )
        advisor_stats = UserStatsService.advisor_stats_to_dict(advisor_stats_obj)

        # Statistiky jako doporučitel (pokud má ReferrerProfile)
        if referrer_profile:
            referrer_stats_obj = UserStatsService.get_referrer_stats_detailed(
                viewed_user, date_from, date_to
            )
            referrer_stats = UserStatsService.referrer_stats_to_dict(referrer_stats_obj)

    elif viewed_user.role == User.Role.REFERRER_MANAGER:
        # Team statistics
        team_stats = UserStatsService.get_team_stats(viewed_user, date_from, date_to)

        # Personal referrer statistics (pokud má ReferrerProfile)
        if referrer_profile:
            referrer_stats_obj = UserStatsService.get_referrer_stats_detailed(
                viewed_user, date_from, date_to
            )
            referrer_stats = UserStatsService.referrer_stats_to_dict(referrer_stats_obj)

    elif viewed_user.role == User.Role.OFFICE:
        # Statistiky celé kanceláře
        office_stats = UserStatsService.get_office_stats(viewed_user, date_from, date_to)

        # Team statistics (pokud kancelář funguje i jako manažer)
        team_stats = UserStatsService.get_team_stats(viewed_user, date_from, date_to)

        # Personal referrer statistics (pokud má ReferrerProfile)
        if referrer_profile:
            referrer_stats_obj = UserStatsService.get_referrer_stats_detailed(
                viewed_user, date_from, date_to
            )
            referrer_stats = UserStatsService.referrer_stats_to_dict(referrer_stats_obj)

    elif viewed_user.role == User.Role.REFERRER:
        # Běžný doporučitel - zobrazit všechny jeho statistiky (včetně personal contacts)
        if referrer_profile:
            # Note: For REFERRER role, we want to include personal contacts in their stats
            referrer_leads_qs = Lead.objects.filter(referrer=viewed_user)
            referrer_leads_qs = UserStatsService.apply_date_filter(referrer_leads_qs, date_from, date_to)

            referrer_stats_obj = UserStatsService._lead_stats(referrer_leads_qs)
            referrer_stats = UserStatsService.stats_to_dict(referrer_stats_obj)

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
