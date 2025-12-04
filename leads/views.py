from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponseForbidden
from accounts.models import ReferrerProfile


from .models import Lead
from .forms import LeadForm

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


    return render(request, "leads/lead_form.html", context)

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
