from dataclasses import dataclass
from accounts.models import User, Office
from leads.models import Lead, Deal


@dataclass(frozen=True)
class Stats:
    contacts: int
    meetings_planned: int
    meetings_done: int
    deals_created: int
    deals_success: int


def _lead_stats(qs) -> Stats:
    """
    qs = queryset Leadů pro danou roli
    """
    contacts = qs.count()

    meetings_planned = qs.filter(
        communication_status=Lead.CommunicationStatus.MEETING
    ).count()

    meetings_done = qs.filter(meeting_done=True).count()

    deals_created = Deal.objects.filter(lead__in=qs).count()

    deals_success = Deal.objects.filter(
        lead__in=qs,
        status=Deal.DealStatus.DRAWN,  # "Načerpáno" = úspěšně dokončeno
    ).count()

    return Stats(
        contacts=contacts,
        meetings_planned=meetings_planned,
        meetings_done=meetings_done,
        deals_created=deals_created,
        deals_success=deals_success,
    )


# -------------------------
# ZÁKLADNÍ ROLE
# -------------------------

def stats_referrer_personal(user: User) -> Stats:
    """
    Osobní statistika jako doporučitel (referrer=user)
    """
    qs = Lead.objects.filter(referrer=user)
    return _lead_stats(qs)


def stats_advisor(user: User) -> Stats:
    """
    Osobní statistika poradce (advisor=user)
    """
    qs = Lead.objects.filter(advisor=user)
    return _lead_stats(qs)


# -------------------------
# MANAŽER: osobní vs tým
# -------------------------

def stats_manager(user: User) -> dict:
    """
    Manažer má dvojí statistiku:
    - personal_referrer: jeho vlastní leady jako doporučitel
    - team: leady jeho podřízených doporučitelů (bez jeho vlastních leadů)
    """
    personal_qs = Lead.objects.filter(referrer=user)

    team_qs = Lead.objects.filter(
        referrer__referrer_profile__manager=user
    ).exclude(referrer=user)

    return {
        "personal_referrer": _lead_stats(personal_qs),
        "team": _lead_stats(team_qs),
    }


# -------------------------
# OFFICE: osobní vs tým
# -------------------------

def stats_office_user(user: User) -> dict:
    """
    Office uživatel (owner kanceláře) má dvojí statistiku:
    - personal_referrer: jeho vlastní leady jako doporučitel
    - team: všechny leady kanceláře (bez jeho vlastních leadů)
    """
    personal_qs = Lead.objects.filter(referrer=user)

    offices = Office.objects.filter(owner=user)

    team_qs = Lead.objects.filter(
        referrer__referrer_profile__manager__manager_profile__office__in=offices
    ).exclude(referrer=user)

    return {
        "personal_referrer": _lead_stats(personal_qs),
        "team": _lead_stats(team_qs),
    }
