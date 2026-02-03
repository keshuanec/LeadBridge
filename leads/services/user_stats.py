"""
User Statistics Service for Lead Bridge CRM

This service provides centralized statistics calculations for all user roles,
consolidating logic that was previously duplicated across multiple views.

Features:
- Date-based filtering support
- Personal contact exclusion for referrer statistics
- Role-specific statistics (Advisor, Referrer, Manager, Office)
- Annotated querysets for list views

Author: Refactored from leads/views.py
Date: 2026-01-21
"""

from dataclasses import dataclass
from datetime import timedelta, date
from typing import Optional, Dict
from django.db.models import Q, QuerySet, Count, Case, When, IntegerField
from accounts.models import User, Office
from leads.models import Lead, Deal


@dataclass(frozen=True)
class Stats:
    """Basic statistics data class

    Note: deals_created and deals_success count unique LEADS with deals,
    not total number of deals (one lead may have multiple deals).

    Completed deals are those with status: DRAWN, SIGNED, or SIGNED_NO_PROPERTY.
    """
    contacts: int
    meetings_planned: int
    meetings_done: int
    deals_created: int  # Number of unique leads with at least one deal
    deals_success: int  # Number of unique leads with at least one completed deal (DRAWN, SIGNED, SIGNED_NO_PROPERTY)


@dataclass(frozen=True)
class AdvisorStatsDetailed:
    """Detailed statistics for advisors including personal contacts

    Note: All deal counts represent unique LEADS with deals,
    not total number of deals (one lead may have multiple deals).

    Completed deals are those with status: DRAWN, SIGNED, or SIGNED_NO_PROPERTY.
    """
    leads_received: int
    meetings_planned: int
    meetings_done: int
    deals_created: int  # Number of unique leads with at least one deal
    deals_completed: int  # Number of unique leads with at least one completed deal (DRAWN, SIGNED, SIGNED_NO_PROPERTY)
    deals_created_personal: int  # Number of unique leads with at least one personal deal
    deals_completed_personal: int  # Number of unique leads with at least one completed personal deal (DRAWN, SIGNED, SIGNED_NO_PROPERTY)


@dataclass(frozen=True)
class ReferrerStatsDetailed:
    """Detailed statistics for referrers

    Note: deals_done counts unique LEADS with completed deals,
    not total number of deals (one lead may have multiple deals).

    Completed deals are those with status: DRAWN, SIGNED, or SIGNED_NO_PROPERTY.
    """
    leads_sent: int
    meetings_planned: int
    meetings_done: int
    deals_done: int  # Number of unique leads with at least one completed deal (DRAWN, SIGNED, SIGNED_NO_PROPERTY)


class UserStatsService:
    """
    Centralized service for user statistics calculations.

    This service consolidates all statistics logic from views, eliminating
    duplication and providing a single source of truth for stats calculations.
    """

    # Deal statuses that are considered "completed" for statistics
    # Includes: signed contracts and drawn loans
    COMPLETED_DEAL_STATUSES = [
        Deal.DealStatus.DRAWN,              # Načerpáno
        Deal.DealStatus.SIGNED,             # Podepsaná smlouva
        Deal.DealStatus.SIGNED_NO_PROPERTY, # Podeps. bez nem.
    ]

    # -------------------------
    # HELPER METHODS
    # -------------------------

    @staticmethod
    def apply_date_filter(queryset: QuerySet, date_from: Optional[date] = None,
                         date_to: Optional[date] = None,
                         field_name: str = 'created_at') -> QuerySet:
        """
        Apply date range filter to a queryset.

        Args:
            queryset: The queryset to filter
            date_from: Start date (inclusive)
            date_to: End date (inclusive, adds 1 day for lt comparison)
            field_name: Name of the date field to filter on

        Returns:
            Filtered queryset

        Examples:
            >>> from datetime import date
            >>> qs = Lead.objects.all()
            >>> filtered = UserStatsService.apply_date_filter(
            ...     qs, date(2024, 1, 1), date(2024, 12, 31)
            ... )
        """
        if date_from:
            filter_kwargs = {f"{field_name}__gte": date_from}
            queryset = queryset.filter(**filter_kwargs)
        if date_to:
            # Add 1 day to include the entire end date
            filter_kwargs = {f"{field_name}__lt": date_to + timedelta(days=1)}
            queryset = queryset.filter(**filter_kwargs)
        return queryset

    @staticmethod
    def advisor_stats_to_dict(stats: AdvisorStatsDetailed) -> Dict:
        """
        Convert AdvisorStatsDetailed dataclass to dictionary for template use.

        Args:
            stats: AdvisorStatsDetailed dataclass instance

        Returns:
            Dictionary with all stat fields
        """
        return {
            "leads_received": stats.leads_received,
            "meetings_planned": stats.meetings_planned,
            "meetings_done": stats.meetings_done,
            "deals_created": stats.deals_created,
            "deals_completed": stats.deals_completed,
            "deals_created_personal": stats.deals_created_personal,
            "deals_completed_personal": stats.deals_completed_personal,
        }

    @staticmethod
    def referrer_stats_to_dict(stats: ReferrerStatsDetailed) -> Dict:
        """
        Convert ReferrerStatsDetailed dataclass to dictionary for template use.

        Args:
            stats: ReferrerStatsDetailed dataclass instance

        Returns:
            Dictionary with all stat fields
        """
        return {
            "leads_sent": stats.leads_sent,
            "meetings_planned": stats.meetings_planned,
            "meetings_done": stats.meetings_done,
            "deals_done": stats.deals_done,
        }

    @staticmethod
    def stats_to_dict(stats: Stats) -> Dict:
        """
        Convert Stats dataclass to dictionary for template use.

        Args:
            stats: Stats dataclass instance

        Returns:
            Dictionary with all stat fields mapped to referrer naming convention
        """
        return {
            "leads_sent": stats.contacts,
            "meetings_planned": stats.meetings_planned,
            "meetings_done": stats.meetings_done,
            "deals_done": stats.deals_success,
        }

    @staticmethod
    def get_team_stats(manager: User, date_from: Optional[date] = None,
                      date_to: Optional[date] = None) -> Optional[Dict]:
        """
        Calculate team statistics for a manager.

        Args:
            manager: User with REFERRER_MANAGER or OFFICE role
            date_from: Start date for filtering
            date_to: End date for filtering

        Returns:
            Dictionary with team stats or None if no team members
        """
        from accounts.models import ReferrerProfile

        managed_profiles = ReferrerProfile.objects.filter(manager=manager)
        team_referrer_ids = managed_profiles.values_list("user_id", flat=True)

        if not team_referrer_ids:
            return None

        # Build queryset for team leads with date filtering
        team_leads_qs = Lead.objects.filter(
            referrer_id__in=team_referrer_ids
        ).exclude(is_personal_contact=True)
        team_leads_qs = UserStatsService.apply_date_filter(team_leads_qs, date_from, date_to)

        # Calculate team statistics (exclude personal deals)
        team_stats_obj = UserStatsService._lead_stats(team_leads_qs, exclude_personal_deals=True)
        return UserStatsService.stats_to_dict(team_stats_obj)

    @staticmethod
    def get_office_stats(office_owner: User, date_from: Optional[date] = None,
                        date_to: Optional[date] = None) -> Optional[Dict]:
        """
        Calculate office-wide statistics for an office owner.

        Args:
            office_owner: User with OFFICE role
            date_from: Start date for filtering
            date_to: End date for filtering

        Returns:
            Dictionary with office stats or None if no office members
        """
        from accounts.models import ReferrerProfile

        # Statistiky celé kanceláře
        office_referrer_profiles = ReferrerProfile.objects.filter(
            manager__manager_profile__office__owner=office_owner
        )
        office_referrer_ids = office_referrer_profiles.values_list("user_id", flat=True)

        if not office_referrer_ids:
            return None

        office_leads_qs = Lead.objects.filter(
            referrer_id__in=office_referrer_ids
        ).exclude(is_personal_contact=True)
        office_leads_qs = UserStatsService.apply_date_filter(office_leads_qs, date_from, date_to)

        office_stats_obj = UserStatsService._lead_stats(office_leads_qs, exclude_personal_deals=True)
        return UserStatsService.stats_to_dict(office_stats_obj)

    @staticmethod
    def exclude_personal_contacts_for_referrer(queryset: QuerySet,
                                               referrer: Optional[User] = None) -> QuerySet:
        """
        Exclude personal contacts from referrer statistics.

        Personal contacts (is_personal_contact=True) should not be counted
        in referrer statistics as they don't generate commissions for referrers.

        Args:
            queryset: Lead queryset to filter
            referrer: Optional specific referrer (if None, excludes all personal contacts)

        Returns:
            Filtered queryset

        Examples:
            >>> leads = Lead.objects.filter(referrer=user)
            >>> stats_leads = UserStatsService.exclude_personal_contacts_for_referrer(leads)
        """
        if referrer:
            # Exclude only personal contacts for this specific referrer
            return queryset.exclude(is_personal_contact=True)
        else:
            # Exclude all personal contacts
            return queryset.exclude(is_personal_contact=True)

    @staticmethod
    def exclude_personal_contacts_for_advisor(queryset: QuerySet,
                                             advisor: User) -> QuerySet:
        """
        Exclude personal contacts from advisor statistics.

        For advisor statistics, we exclude leads where:
        - is_personal_contact=True AND referrer=advisor

        This means the advisor created the lead themselves as a personal contact.

        Args:
            queryset: Lead or Deal queryset to filter
            advisor: The advisor user

        Returns:
            Filtered queryset
        """
        # Check if this is a Deal queryset or Lead queryset
        if queryset.model == Deal:
            return queryset.exclude(
                lead__is_personal_contact=True,
                lead__referrer=advisor
            )
        else:  # Lead queryset
            return queryset.exclude(
                is_personal_contact=True,
                referrer=advisor
            )

    # -------------------------
    # CORE STATISTICS METHODS
    # -------------------------

    @staticmethod
    def _lead_stats(qs: QuerySet, exclude_personal_deals: bool = False) -> Stats:
        """
        Calculate basic statistics from a Lead queryset.

        Internal method used by other statistics functions.

        Args:
            qs: Lead queryset
            exclude_personal_deals: If True, exclude deals with is_personal_deal=True
                                   (used for referrer/manager/office stats)

        Returns:
            Stats dataclass with calculated values
        """
        contacts = qs.count()

        meetings_planned = qs.filter(
            meeting_scheduled=True
        ).count()

        meetings_done = qs.filter(meeting_done=True).count()

        deals_qs = Deal.objects.filter(lead__in=qs)
        if exclude_personal_deals:
            deals_qs = deals_qs.exclude(is_personal_deal=True)

        # Count unique leads with deals (one lead may have multiple deals)
        deals_created = deals_qs.values('lead').distinct().count()

        deals_success = deals_qs.filter(
            status__in=UserStatsService.COMPLETED_DEAL_STATUSES,
        ).values('lead').distinct().count()

        return Stats(
            contacts=contacts,
            meetings_planned=meetings_planned,
            meetings_done=meetings_done,
            deals_created=deals_created,
            deals_success=deals_success,
        )

    # -------------------------
    # ADVISOR STATISTICS
    # -------------------------

    @staticmethod
    def get_advisor_stats_detailed(advisor: User,
                                   date_from: Optional[date] = None,
                                   date_to: Optional[date] = None) -> AdvisorStatsDetailed:
        """
        Get detailed statistics for an advisor with date filtering.

        Calculates:
        - Leads received (excluding personal contacts where referrer=advisor)
        - Meetings planned and completed
        - Deals created and completed
        - Personal deals (where referrer=advisor and is_personal_contact=True)

        Args:
            advisor: The advisor User object
            date_from: Optional start date for filtering
            date_to: Optional end date for filtering

        Returns:
            AdvisorStatsDetailed with all calculated statistics

        Examples:
            >>> from datetime import date
            >>> stats = UserStatsService.get_advisor_stats_detailed(
            ...     advisor, date(2024, 1, 1), date(2024, 12, 31)
            ... )
            >>> print(f"Leads received: {stats.leads_received}")
        """
        # Leads statistics (exclude personal contacts where referrer=advisor)
        leads_qs = Lead.objects.filter(advisor=advisor).exclude(
            is_personal_contact=True, referrer=advisor
        )
        leads_qs = UserStatsService.apply_date_filter(leads_qs, date_from, date_to)

        leads_received = leads_qs.count()
        meetings_planned = leads_qs.filter(meeting_scheduled=True).count()
        meetings_done = leads_qs.filter(meeting_done=True).count()

        # Deals statistics (exclude personal contacts AND personal deals)
        # Count unique LEADS with deals, not total number of deals
        deals_qs = Deal.objects.filter(lead__advisor=advisor).exclude(
            Q(lead__is_personal_contact=True, lead__referrer=advisor) |
            Q(is_personal_deal=True)
        )
        deals_qs = UserStatsService.apply_date_filter(deals_qs, date_from, date_to)

        # Count unique leads (one lead may have multiple deals)
        deals_created = deals_qs.values('lead').distinct().count()
        deals_completed = deals_qs.filter(
            status__in=UserStatsService.COMPLETED_DEAL_STATUSES
        ).values('lead').distinct().count()

        # Personal deals statistics (personal contacts OR personal deals)
        # Count unique LEADS with personal deals
        personal_deals_qs = Deal.objects.filter(
            lead__advisor=advisor
        ).filter(
            Q(lead__is_personal_contact=True, lead__referrer=advisor) |
            Q(is_personal_deal=True)
        )
        personal_deals_qs = UserStatsService.apply_date_filter(
            personal_deals_qs, date_from, date_to
        )

        # Count unique leads (one lead may have multiple personal deals)
        deals_created_personal = personal_deals_qs.values('lead').distinct().count()
        deals_completed_personal = personal_deals_qs.filter(
            status__in=UserStatsService.COMPLETED_DEAL_STATUSES
        ).values('lead').distinct().count()

        return AdvisorStatsDetailed(
            leads_received=leads_received,
            meetings_planned=meetings_planned,
            meetings_done=meetings_done,
            deals_created=deals_created,
            deals_completed=deals_completed,
            deals_created_personal=deals_created_personal,
            deals_completed_personal=deals_completed_personal,
        )

    @staticmethod
    def stats_advisor(user: User) -> Stats:
        """
        Basic advisor statistics without date filtering.

        This is the legacy method maintained for backward compatibility.
        For detailed statistics with date filtering, use get_advisor_stats_detailed().

        Args:
            user: The advisor User object

        Returns:
            Basic Stats dataclass
        """
        qs = Lead.objects.filter(advisor=user)
        return UserStatsService._lead_stats(qs)

    # -------------------------
    # REFERRER STATISTICS
    # -------------------------

    @staticmethod
    def get_referrer_stats_detailed(referrer: User,
                                   date_from: Optional[date] = None,
                                   date_to: Optional[date] = None) -> ReferrerStatsDetailed:
        """
        Get detailed statistics for a referrer with date filtering.

        IMPORTANT: Excludes personal contacts (is_personal_contact=True) from all counts.

        Args:
            referrer: The referrer User object
            date_from: Optional start date for filtering
            date_to: Optional end date for filtering

        Returns:
            ReferrerStatsDetailed with all calculated statistics
        """
        # Leads statistics (exclude personal contacts)
        referrer_leads_qs = Lead.objects.filter(referrer=referrer).exclude(
            is_personal_contact=True
        )
        referrer_leads_qs = UserStatsService.apply_date_filter(
            referrer_leads_qs, date_from, date_to
        )

        leads_sent = referrer_leads_qs.count()
        meetings_planned = referrer_leads_qs.filter(meeting_scheduled=True).count()
        meetings_done = referrer_leads_qs.filter(meeting_done=True).count()

        # Deals statistics (exclude personal contacts and personal deals)
        referrer_deals_qs = Deal.objects.filter(lead__in=referrer_leads_qs).exclude(is_personal_deal=True)
        referrer_deals_qs = UserStatsService.apply_date_filter(
            referrer_deals_qs, date_from, date_to
        )

        # Count unique leads with completed deals (one lead may have multiple deals)
        deals_done = referrer_deals_qs.filter(
            status__in=UserStatsService.COMPLETED_DEAL_STATUSES
        ).values('lead').distinct().count()

        return ReferrerStatsDetailed(
            leads_sent=leads_sent,
            meetings_planned=meetings_planned,
            meetings_done=meetings_done,
            deals_done=deals_done,
        )

    @staticmethod
    def stats_referrer_personal(user: User) -> Stats:
        """
        Basic referrer statistics without date filtering.

        This is the legacy method maintained for backward compatibility.
        IMPORTANT: Excludes personal contacts from counts.

        Args:
            user: The referrer User object

        Returns:
            Basic Stats dataclass
        """
        qs = Lead.objects.filter(referrer=user).exclude(is_personal_contact=True)
        return UserStatsService._lead_stats(qs, exclude_personal_deals=True)

    # -------------------------
    # MANAGER STATISTICS
    # -------------------------

    @staticmethod
    def stats_manager(user: User) -> Dict[str, Stats]:
        """
        Manager statistics (personal + team).

        Calculates separate statistics for:
        - personal_referrer: Manager's own leads as a referrer
        - team: Leads from subordinate referrers (excluding manager's own)

        IMPORTANT: Excludes personal contacts from all counts.

        Args:
            user: The manager User object

        Returns:
            Dictionary with 'personal_referrer' and 'team' Stats
        """
        personal_qs = Lead.objects.filter(referrer=user).exclude(
            is_personal_contact=True
        )

        team_qs = Lead.objects.filter(
            referrer__referrer_profile__manager=user
        ).exclude(referrer=user).exclude(is_personal_contact=True)

        return {
            "personal_referrer": UserStatsService._lead_stats(personal_qs, exclude_personal_deals=True),
            "team": UserStatsService._lead_stats(team_qs, exclude_personal_deals=True),
        }

    # -------------------------
    # OFFICE STATISTICS
    # -------------------------

    @staticmethod
    def stats_office_user(user: User) -> Dict[str, Stats]:
        """
        Office owner statistics (personal + team).

        Calculates separate statistics for:
        - personal_referrer: Office owner's own leads as a referrer
        - team: All leads from the office (excluding owner's own)

        IMPORTANT: Excludes personal contacts from all counts.

        Args:
            user: The office owner User object

        Returns:
            Dictionary with 'personal_referrer' and 'team' Stats
        """
        personal_qs = Lead.objects.filter(referrer=user).exclude(
            is_personal_contact=True
        )

        offices = Office.objects.filter(owner=user)

        team_qs = Lead.objects.filter(
            referrer__referrer_profile__manager__manager_profile__office__in=offices
        ).exclude(referrer=user).exclude(is_personal_contact=True)

        return {
            "personal_referrer": UserStatsService._lead_stats(personal_qs, exclude_personal_deals=True),
            "team": UserStatsService._lead_stats(team_qs, exclude_personal_deals=True),
        }

    # -------------------------
    # ANNOTATED QUERYSETS FOR LIST VIEWS
    # -------------------------

    @staticmethod
    def get_advisors_with_stats(date_from: Optional[date] = None,
                               date_to: Optional[date] = None) -> QuerySet:
        """
        Get advisors queryset with annotated statistics.

        Returns a queryset of Users with role=ADVISOR, annotated with:
        - leads_received: Number of leads assigned to advisor (excluding personal contacts)
        - meetings_planned: Number of leads with meetings scheduled
        - meetings_done: Number of leads with meetings completed
        - deals_created: Number of unique leads with at least one deal
        - deals_completed: Number of unique leads with at least one completed deal

        Note: deals_created and deals_completed count unique LEADS with deals,
        not total number of deals (one lead may have multiple deals).
        This ensures consistency with meetings counts.

        Args:
            date_from: Optional start date for filtering
            date_to: Optional end date for filtering

        Returns:
            QuerySet of User objects with annotations

        Examples:
            >>> advisors = UserStatsService.get_advisors_with_stats()
            >>> for advisor in advisors:
            ...     print(f"{advisor.get_full_name()}: {advisor.leads_received} leads")
        """
        from django.db.models import F, Subquery, OuterRef as OuterRefDjango

        # For advisors, we need to exclude personal contacts where referrer=advisor
        # We'll use Subquery to properly handle this complex filter

        # Build lead subquery that excludes personal contacts where referrer=advisor
        lead_subquery = Lead.objects.filter(
            advisor=OuterRefDjango('pk')
        ).exclude(
            is_personal_contact=True,
            referrer=F('advisor')  # exclude when referrer equals advisor
        )

        # Apply date filters if provided
        if date_from:
            lead_subquery = lead_subquery.filter(created_at__gte=date_from)
        if date_to:
            lead_subquery = lead_subquery.filter(created_at__lt=date_to + timedelta(days=1))

        # Build deal subquery that excludes personal contacts AND personal deals
        deal_subquery = Deal.objects.filter(
            lead__advisor=OuterRefDjango('pk')
        ).exclude(
            Q(lead__is_personal_contact=True, lead__referrer=F('lead__advisor')) |
            Q(is_personal_deal=True)
        )

        if date_from:
            deal_subquery = deal_subquery.filter(created_at__gte=date_from)
        if date_to:
            deal_subquery = deal_subquery.filter(created_at__lt=date_to + timedelta(days=1))

        return User.objects.filter(role=User.Role.ADVISOR).annotate(
            leads_received=Subquery(
                lead_subquery.values('advisor').annotate(count=Count('id')).values('count')[:1]
            ),
            meetings_planned=Subquery(
                lead_subquery.filter(meeting_scheduled=True).values('advisor').annotate(count=Count('id')).values('count')[:1]
            ),
            meetings_done=Subquery(
                lead_subquery.filter(meeting_done=True).values('advisor').annotate(count=Count('id')).values('count')[:1]
            ),
            deals_created=Subquery(
                deal_subquery.values('lead__advisor').annotate(count=Count('lead', distinct=True)).values('count')[:1]
            ),
            deals_completed=Subquery(
                deal_subquery.filter(status__in=UserStatsService.COMPLETED_DEAL_STATUSES).values('lead__advisor').annotate(count=Count('lead', distinct=True)).values('count')[:1]
            ),
        ).order_by('last_name', 'first_name')

    @staticmethod
    def get_referrers_with_stats(date_from: Optional[date] = None,
                                date_to: Optional[date] = None) -> QuerySet:
        """
        Get referrers queryset with annotated statistics.

        Returns a queryset of Users with role=REFERRER, annotated with:
        - leads_sent: Number of leads sent (excluding personal contacts)
        - meetings_planned: Number of leads with meetings scheduled
        - meetings_done: Number of leads with meetings completed
        - deals_done: Number of completed deals (status: DRAWN, SIGNED, or SIGNED_NO_PROPERTY)

        IMPORTANT: All counts exclude personal contacts (is_personal_contact=True).

        Args:
            date_from: Optional start date for filtering
            date_to: Optional end date for filtering

        Returns:
            QuerySet of User objects with annotations
        """
        from django.db.models import Subquery, OuterRef as OuterRefDjango

        # For referrers, simply exclude personal contacts
        lead_subquery = Lead.objects.filter(
            referrer=OuterRefDjango('pk'),
            is_personal_contact=False
        )

        # Apply date filters if provided
        if date_from:
            lead_subquery = lead_subquery.filter(created_at__gte=date_from)
        if date_to:
            lead_subquery = lead_subquery.filter(created_at__lt=date_to + timedelta(days=1))

        # Build deal subquery (exclude personal contacts)
        deal_subquery = Deal.objects.filter(
            lead__referrer=OuterRefDjango('pk'),
            lead__is_personal_contact=False
        )

        if date_from:
            deal_subquery = deal_subquery.filter(created_at__gte=date_from)
        if date_to:
            deal_subquery = deal_subquery.filter(created_at__lt=date_to + timedelta(days=1))

        return User.objects.filter(role=User.Role.REFERRER).annotate(
            leads_sent=Subquery(
                lead_subquery.values('referrer').annotate(count=Count('id')).values('count')[:1]
            ),
            meetings_planned=Subquery(
                lead_subquery.filter(meeting_scheduled=True).values('referrer').annotate(count=Count('id')).values('count')[:1]
            ),
            meetings_done=Subquery(
                lead_subquery.filter(meeting_done=True).values('referrer').annotate(count=Count('id')).values('count')[:1]
            ),
            deals_done=Subquery(
                deal_subquery.filter(status__in=UserStatsService.COMPLETED_DEAL_STATUSES).values('lead__referrer').annotate(count=Count('id')).values('count')[:1]
            ),
        ).order_by('last_name', 'first_name')
