"""
Access Control Service for Lead Bridge CRM

This service provides centralized role-based access control (RBAC) for Leads and Deals.
It consolidates queryset filtering logic that was previously duplicated across multiple views.

Author: Refactored from leads/views.py
Date: 2026-01-21
"""

from django.db.models import Q, QuerySet
from django.contrib.auth import get_user_model
from typing import Set, Dict

User = get_user_model()


class LeadAccessService:
    """
    Centralized service for Lead and Deal access control.

    This service provides role-based queryset filtering to ensure users
    only see data they're authorized to access based on their role:
    - ADMIN/Superuser: All records
    - ADVISOR: Assigned leads + subordinate referrers' leads (if has_admin_access)
    - REFERRER: Only their own leads
    - REFERRER_MANAGER: Team leads + own leads (excluding personal contacts)
    - OFFICE: Office hierarchy leads (excluding personal contacts)
    """

    @staticmethod
    def get_leads_queryset(user, base_qs=None) -> QuerySet:
        """
        Returns filtered Lead queryset based on user role.

        Args:
            user: The User object requesting access
            base_qs: Optional base queryset to filter (defaults to Lead.objects.all())

        Returns:
            QuerySet[Lead]: Filtered queryset containing only accessible leads

        Examples:
            >>> from leads.services.access_control import LeadAccessService
            >>> leads = LeadAccessService.get_leads_queryset(request.user)
            >>> my_leads = leads.filter(communication_status='NEW')
        """
        from leads.models import Lead

        if base_qs is None:
            base_qs = Lead.objects.all()

        # ADMIN and Superuser: Full access
        if user.is_superuser or user.role == User.Role.ADMIN:
            return base_qs

        # ADVISOR: Assigned leads + subordinate referrers' leads (if has_admin_access)
        elif user.role == User.Role.ADVISOR:
            if user.has_admin_access:
                # Admin advisors see:
                # 1. Their own assigned leads
                # 2. Leads from subordinate referrers
                # 3. Personal contacts of subordinate advisors
                return base_qs.filter(
                    Q(advisor=user) |
                    Q(referrer__referrer_profile__advisors=user) |
                    Q(is_personal_contact=True, advisor__referrer_profile__advisors=user)
                ).distinct()
            else:
                # Regular advisors see only their assigned leads (including personal contacts)
                return base_qs.filter(advisor=user)

        # REFERRER: Only their own leads
        elif user.role == User.Role.REFERRER:
            return base_qs.filter(referrer=user)

        # REFERRER_MANAGER: Team leads + own leads (exclude personal contacts)
        elif user.role == User.Role.REFERRER_MANAGER:
            return base_qs.filter(
                Q(referrer__referrer_profile__manager=user) | Q(referrer=user)
            ).exclude(is_personal_contact=True).distinct()

        # OFFICE: Office hierarchy leads (exclude personal contacts)
        elif user.role == User.Role.OFFICE:
            return base_qs.filter(
                Q(referrer__referrer_profile__manager__manager_profile__office__owner=user) |
                Q(referrer=user)
            ).exclude(is_personal_contact=True).distinct()

        # Default: No access
        return Lead.objects.none()

    @staticmethod
    def get_deals_queryset(user, base_qs=None) -> QuerySet:
        """
        Returns filtered Deal queryset based on user role.

        Access is determined via the related Lead, so this method filters
        deals by applying lead-based access rules.

        Args:
            user: The User object requesting access
            base_qs: Optional base queryset to filter (defaults to Deal.objects.all())

        Returns:
            QuerySet[Deal]: Filtered queryset containing only accessible deals

        Examples:
            >>> from leads.services.access_control import LeadAccessService
            >>> deals = LeadAccessService.get_deals_queryset(request.user)
            >>> active_deals = deals.filter(status='PREPARATION')
        """
        from leads.models import Deal

        if base_qs is None:
            base_qs = Deal.objects.all()

        # ADMIN and Superuser: Full access
        if user.is_superuser or user.role == User.Role.ADMIN:
            return base_qs

        # ADVISOR: Deals from assigned leads + subordinate referrers
        elif user.role == User.Role.ADVISOR:
            if user.has_admin_access:
                return base_qs.filter(
                    Q(lead__advisor=user) |
                    Q(lead__referrer__referrer_profile__advisors=user) |
                    Q(lead__is_personal_contact=True, lead__advisor__referrer_profile__advisors=user)
                ).distinct()
            else:
                return base_qs.filter(lead__advisor=user)

        # REFERRER: Deals from their own leads (exclude personal deals)
        elif user.role == User.Role.REFERRER:
            return base_qs.filter(lead__referrer=user).exclude(is_personal_deal=True)

        # REFERRER_MANAGER: Team deals + own deals (exclude personal contacts and personal deals)
        elif user.role == User.Role.REFERRER_MANAGER:
            return base_qs.filter(
                Q(lead__referrer__referrer_profile__manager=user) | Q(lead__referrer=user)
            ).exclude(
                Q(lead__is_personal_contact=True) | Q(is_personal_deal=True)
            ).distinct()

        # OFFICE: Office hierarchy deals (exclude personal contacts and personal deals)
        elif user.role == User.Role.OFFICE:
            return base_qs.filter(
                Q(lead__referrer__referrer_profile__manager__manager_profile__office__owner=user) |
                Q(lead__referrer=user)
            ).exclude(
                Q(lead__is_personal_contact=True) | Q(is_personal_deal=True)
            ).distinct()

        # Default: No access
        from leads.models import Deal
        return Deal.objects.none()

    @staticmethod
    def apply_select_related(queryset, entity_type='lead') -> QuerySet:
        """
        Apply standard select_related optimization for Lead or Deal querysets.

        This reduces database queries by pre-fetching related objects that are
        commonly accessed together (referrer, advisor, manager, office).

        Args:
            queryset: The queryset to optimize
            entity_type: Either 'lead' or 'deal' to determine field paths

        Returns:
            QuerySet: Optimized queryset with select_related applied

        Examples:
            >>> leads = Lead.objects.filter(...)
            >>> optimized = LeadAccessService.apply_select_related(leads, 'lead')
        """
        if entity_type == 'lead':
            return queryset.select_related(
                'referrer',
                'advisor',
                'referrer__referrer_profile__manager',
                'referrer__referrer_profile__manager__manager_profile__office',
            )
        elif entity_type == 'deal':
            return queryset.select_related(
                'lead',
                'lead__referrer',
                'lead__advisor',
                'lead__referrer__referrer_profile__manager',
                'lead__referrer__referrer_profile__manager__manager_profile__office',
            )
        else:
            return queryset

    @staticmethod
    def get_allowed_filters(user, context='leads') -> Set[str]:
        """
        Returns allowed filter keys for user role and context.

        Different roles have access to different filter options:
        - REFERRER: status, advisor (if multiple advisors exist)
        - REFERRER_MANAGER: status, referrer, advisor
        - OFFICE: status, referrer, manager, advisor
        - ADVISOR: status, referrer, manager, office
        - ADMIN: all filters

        Args:
            user: The User object
            context: Either 'leads' or 'deals' (currently both use same filters)

        Returns:
            Set[str]: Set of allowed filter keys

        Examples:
            >>> allowed = LeadAccessService.get_allowed_filters(request.user, 'leads')
            >>> if 'manager' in allowed:
            ...     # Show manager filter in UI
        """
        # Filter permissions by role
        allowed_filters_map = {
            User.Role.REFERRER: {"status", "advisor"},
            User.Role.REFERRER_MANAGER: {"status", "referrer", "advisor"},
            User.Role.OFFICE: {"status", "referrer", "manager", "advisor"},
            User.Role.ADVISOR: {"status", "referrer", "manager", "office"},
        }

        # Admin and Superuser get all filters
        if user.is_superuser or user.role == User.Role.ADMIN:
            return {"status", "referrer", "advisor", "manager", "office"}

        return allowed_filters_map.get(user.role, set())

    @staticmethod
    def get_column_visibility(user, view_type='leads') -> Dict[str, bool]:
        """
        Calculate which columns to show based on user role.

        This determines table column visibility in list views (leads, deals).
        Different roles see different hierarchical information.

        Args:
            user: The User object
            view_type: Either 'leads' or 'deals'

        Returns:
            Dict[str, bool]: Dictionary with column visibility flags

        Examples:
            >>> visibility = LeadAccessService.get_column_visibility(request.user, 'leads')
            >>> if visibility['show_manager']:
            ...     # Render manager column in template
        """
        is_admin_like = user.is_superuser or user.role == User.Role.ADMIN

        return {
            'show_referrer': is_admin_like or user.role in (
                User.Role.REFERRER_MANAGER,
                User.Role.OFFICE,
                User.Role.ADVISOR
            ),
            'show_advisor': is_admin_like or user.role in (
                User.Role.REFERRER,
                User.Role.REFERRER_MANAGER,
                User.Role.OFFICE
            ),
            'show_manager': is_admin_like or user.role in (
                User.Role.OFFICE,
                User.Role.ADVISOR
            ),
            'show_office': is_admin_like or user.role in (
                User.Role.ADVISOR,
            ),
        }

    @staticmethod
    def can_schedule_meeting(user, lead) -> bool:
        """
        Check if user can schedule meetings for a lead.

        Only advisors and admins can schedule meetings.

        Args:
            user: The User object
            lead: The Lead object

        Returns:
            bool: True if user can schedule meetings
        """
        return user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]

    @staticmethod
    def can_create_deal(user, lead) -> bool:
        """
        Check if user can create deals from a lead.

        Only advisors and admins can create deals.

        Args:
            user: The User object
            lead: The Lead object

        Returns:
            bool: True if user can create deals
        """
        return user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]

    @staticmethod
    def can_manage_commission(user, deal) -> bool:
        """
        Check if user can manage commission status for a deal.

        Only advisors and admins can mark commissions as ready or paid.

        Args:
            user: The User object
            deal: The Deal object

        Returns:
            bool: True if user can manage commissions
        """
        return user.is_superuser or user.role in [User.Role.ADMIN, User.Role.ADVISOR]

    @staticmethod
    def can_schedule_callback(user, lead) -> bool:
        """
        Check if user can schedule a callback for a lead.

        Multiple roles can schedule callbacks:
        - Advisors can always schedule callbacks for their leads
        - Referrers can schedule if they're the lead owner
        - Managers can schedule for team leads
        - Office owners can schedule for office leads
        - Admins can schedule for any lead

        Args:
            user: The User object
            lead: The Lead object

        Returns:
            bool: True if user can schedule callbacks
        """
        # Admins and advisors can always schedule
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True

        if user.role == User.Role.ADVISOR:
            return lead.advisor == user

        # Referrers can schedule for their own leads
        if user.role == User.Role.REFERRER:
            return lead.referrer == user

        # Managers can schedule for team leads
        if user.role == User.Role.REFERRER_MANAGER:
            rp = getattr(lead.referrer, 'referrer_profile', None)
            manager = getattr(rp, 'manager', None) if rp else None
            return manager == user or lead.referrer == user

        # Office owners can schedule for office leads
        if user.role == User.Role.OFFICE:
            rp = getattr(lead.referrer, 'referrer_profile', None)
            manager = getattr(rp, 'manager', None) if rp else None
            office = getattr(getattr(manager, 'manager_profile', None), 'office', None) if manager else None
            office_owner = getattr(office, 'owner', None) if office else None
            return office_owner == user or lead.referrer == user

        return False

    @staticmethod
    def can_edit_lead(user, lead) -> bool:
        """
        Check if user can edit a lead.

        This is determined by the get_leads_queryset filtering - if a user
        can see a lead, they can edit it.

        Args:
            user: The User object
            lead: The Lead object

        Returns:
            bool: True if user can edit the lead
        """
        # Use the queryset filtering as the source of truth
        accessible_leads = LeadAccessService.get_leads_queryset(user)
        return accessible_leads.filter(pk=lead.pk).exists()

    @staticmethod
    def can_view_lead(user, lead) -> bool:
        """
        Check if user can view a lead.

        Same as can_edit_lead - viewing and editing permissions are identical.

        Args:
            user: The User object
            lead: The Lead object

        Returns:
            bool: True if user can view the lead
        """
        return LeadAccessService.can_edit_lead(user, lead)
