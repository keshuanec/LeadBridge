"""
List Filter and Sort Service for Lead Bridge CRM

This service consolidates filtering and sorting logic that was duplicated
across multiple list views (my_leads, deals_list).

Author: Refactored from leads/views.py
Date: 2026-01-21
"""

from typing import Dict, Set, Optional
from urllib.parse import urlencode
from django.db.models import QuerySet, Q, Case, When, IntegerField
from accounts.models import User, Office
from leads.models import Lead, Deal


class ListFilterService:
    """
    Centralized service for list view filtering and sorting.

    Handles:
    - Reading filter parameters from request
    - Applying filters to queryset
    - Getting filter options (dropdown values)
    - Applying sorting
    - Generating query string for pagination/sorting links
    """

    def __init__(self, user: User, request, context: str = 'leads'):
        """
        Initialize the filter service.

        Args:
            user: The User making the request
            request: Django request object
            context: Either 'leads' or 'deals'
        """
        self.user = user
        self.request = request
        self.context = context

    def get_filter_params(self) -> Dict[str, str]:
        """
        Read filter parameters from request.GET.

        Returns:
            Dictionary of filter parameter names and values
        """
        params = {
            'status': self.request.GET.get('status') or '',
            'referrer': self.request.GET.get('referrer') or '',
            'advisor': self.request.GET.get('advisor') or '',
            'manager': self.request.GET.get('manager') or '',
            'office': self.request.GET.get('office') or '',
        }

        # Deals have additional commission filter
        if self.context == 'deals':
            params['commission'] = self.request.GET.get('commission') or ''

        return params

    def get_allowed_filters(self, base_queryset: Optional[QuerySet] = None) -> Set[str]:
        """
        Get allowed filters based on user role and context.

        Args:
            base_queryset: Optional base queryset for special cases (e.g., referrer with multiple advisors)

        Returns:
            Set of allowed filter names
        """
        from .access_control import LeadAccessService

        allowed = LeadAccessService.get_allowed_filters(self.user, self.context)

        # Deals context: add commission filter for all roles
        if self.context == 'deals':
            if self.user.is_superuser or self.user.role in [
                User.Role.ADMIN,
                User.Role.REFERRER,
                User.Role.REFERRER_MANAGER,
                User.Role.OFFICE,
                User.Role.ADVISOR
            ]:
                allowed.add('commission')

        # Special case: referrers with single advisor don't need advisor filter
        if self.context == 'leads' and self.user.role == User.Role.REFERRER and base_queryset:
            advisor_ids = (
                base_queryset.exclude(advisor__isnull=True)
                .values_list('advisor_id', flat=True)
                .distinct()
            )
            if advisor_ids.count() <= 1:
                allowed.discard('advisor')

        return allowed

    def apply_filters(self, queryset: QuerySet, allowed: Set[str], filter_params: Dict[str, str]) -> QuerySet:
        """
        Apply all filters to the queryset based on allowed filters and params.

        Args:
            queryset: The queryset to filter
            allowed: Set of allowed filter names
            filter_params: Dictionary of filter values from request

        Returns:
            Filtered queryset
        """
        qs = queryset

        # Determine field prefix based on context
        prefix = 'lead__' if self.context == 'deals' else ''

        # Status filter
        if 'status' in allowed and filter_params.get('status'):
            if self.context == 'leads':
                qs = qs.filter(communication_status=filter_params['status'])
            else:  # deals
                qs = qs.filter(status=filter_params['status'])

        # Commission filter (deals only)
        if self.context == 'deals' and 'commission' in allowed and filter_params.get('commission'):
            qs = qs.filter(commission_status=filter_params['commission'])

        # Referrer filter
        if 'referrer' in allowed and filter_params.get('referrer'):
            qs = qs.filter(**{f'{prefix}referrer_id': filter_params['referrer']})

        # Advisor filter
        if 'advisor' in allowed and filter_params.get('advisor'):
            qs = qs.filter(**{f'{prefix}advisor_id': filter_params['advisor']})

        # Manager filter (with __none__ support)
        if 'manager' in allowed and filter_params.get('manager'):
            if filter_params['manager'] == '__none__':
                qs = qs.filter(
                    Q(**{f'{prefix}referrer__referrer_profile__manager__isnull': True}) |
                    Q(**{f'{prefix}referrer__referrer_profile__isnull': True})
                )
            else:
                qs = qs.filter(**{f'{prefix}referrer__referrer_profile__manager_id': filter_params['manager']})

        # Office filter (with __none__ support)
        if 'office' in allowed and filter_params.get('office'):
            if filter_params['office'] == '__none__':
                qs = qs.filter(
                    Q(**{f'{prefix}referrer__referrer_profile__manager__manager_profile__office__isnull': True}) |
                    Q(**{f'{prefix}referrer__referrer_profile__manager__isnull': True}) |
                    Q(**{f'{prefix}referrer__referrer_profile__isnull': True})
                )
            else:
                qs = qs.filter(**{
                    f'{prefix}referrer__referrer_profile__manager__manager_profile__office_id': filter_params['office']
                })

        return qs

    def get_sort_mapping(self) -> Dict[str, list]:
        """
        Get sort field mapping for the current context.

        Returns:
            Dictionary mapping sort keys to list of field names
        """
        if self.context == 'leads':
            return {
                'client': ['client_name'],
                'referrer': ['referrer__last_name', 'referrer__first_name', 'referrer__username'],
                'advisor': ['advisor__last_name', 'advisor__first_name', 'advisor__username'],
                'manager': [
                    'referrer__referrer_profile__manager__last_name',
                    'referrer__referrer_profile__manager__first_name',
                    'referrer__referrer_profile__manager__username',
                ],
                'office': [
                    'referrer__referrer_profile__manager__manager_profile__office__name',
                ],
                'comm_status': ['communication_status'],
                'commission': ['commission_status'],
                'created_at': ['created_at'],
            }
        else:  # deals
            return {
                'client': ['lead__client_name'],
                'referrer': ['lead__referrer__last_name', 'lead__referrer__first_name'],
                'advisor': ['lead__advisor__last_name', 'lead__advisor__first_name'],
                'manager': [
                    'lead__referrer__referrer_profile__manager__last_name',
                    'lead__referrer__referrer_profile__manager__first_name',
                ],
                'office': [
                    'lead__referrer__referrer_profile__manager__manager_profile__office__name',
                ],
                'status': ['status'],
                'commission': ['commission_status'],
                'loan_amount': ['loan_amount'],
                'created_at': ['created_at'],
            }

    def apply_sorting(self, queryset: QuerySet) -> tuple[QuerySet, str, str]:
        """
        Apply sorting to the queryset based on request parameters.

        For deals, also adds status_priority annotation for category-based sorting.

        Returns:
            Tuple of (sorted_queryset, sort_key, direction)
        """
        sort = self.request.GET.get('sort') or 'created_at'
        direction = self.request.GET.get('dir') or 'desc'

        sort_mapping = self.get_sort_mapping()

        # Validate sort and direction
        if sort not in sort_mapping:
            sort = 'created_at'
        if direction not in ['asc', 'desc']:
            direction = 'desc'

        # For deals, add status_priority annotation for category-based sorting
        if self.context == 'deals':
            queryset = queryset.annotate(
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

        # Build order_by fields
        order_fields = sort_mapping[sort]

        if direction == 'desc':
            order_fields = ['-' + f for f in order_fields]

        # For deals, prepend status_priority to ordering
        if self.context == 'deals':
            queryset = queryset.order_by('status_priority', *order_fields)
        else:
            queryset = queryset.order_by(*order_fields)

        return queryset, sort, direction

    def get_filter_options(self, base_queryset: QuerySet, allowed: Set[str]) -> Dict[str, QuerySet]:
        """
        Get available options for filter dropdowns.

        Options are always derived from the base queryset (before any filters are applied)
        to show all possible values, not just filtered ones.

        Args:
            base_queryset: Unfiltered queryset to extract options from
            allowed: Set of allowed filter names

        Returns:
            Dictionary of option querysets for each filter
        """
        prefix = 'lead__' if self.context == 'deals' else ''

        options = {
            'referrer_options': User.objects.none(),
            'advisor_options': User.objects.none(),
            'manager_options': User.objects.none(),
            'office_options': User.objects.none(),
        }

        if 'referrer' in allowed:
            ref_ids = base_queryset.values_list(f'{prefix}referrer_id', flat=True).distinct()
            options['referrer_options'] = User.objects.filter(id__in=ref_ids)

        if 'advisor' in allowed:
            adv_ids = base_queryset.values_list(f'{prefix}advisor_id', flat=True).distinct()
            options['advisor_options'] = User.objects.filter(id__in=[x for x in adv_ids if x])

        if 'manager' in allowed:
            mgr_ids = base_queryset.values_list(
                f'{prefix}referrer__referrer_profile__manager_id',
                flat=True
            ).distinct()
            options['manager_options'] = User.objects.filter(id__in=[x for x in mgr_ids if x])

        if 'office' in allowed:
            off_ids = base_queryset.values_list(
                f'{prefix}referrer__referrer_profile__manager__manager_profile__office_id',
                flat=True
            ).distinct()
            options['office_options'] = Office.objects.filter(id__in=[x for x in off_ids if x])

        # Add status choices
        if self.context == 'leads':
            options['status_choices'] = Lead.CommunicationStatus.choices
        else:  # deals
            options['status_choices'] = Deal.DealStatus.choices
            options['commission_choices'] = Deal.CommissionStatus.choices

        return options

    def build_query_string_keep(self, allowed: Set[str], filter_params: Dict[str, str]) -> str:
        """
        Build query string to preserve filters when sorting/paginating.

        Args:
            allowed: Set of allowed filter names
            filter_params: Current filter parameter values

        Returns:
            URL-encoded query string (without leading ?)
        """
        keep_params = {}

        if 'status' in allowed and filter_params.get('status'):
            keep_params['status'] = filter_params['status']

        if self.context == 'deals' and 'commission' in allowed and filter_params.get('commission'):
            keep_params['commission'] = filter_params['commission']

        if 'referrer' in allowed and filter_params.get('referrer'):
            keep_params['referrer'] = filter_params['referrer']

        if 'advisor' in allowed and filter_params.get('advisor'):
            keep_params['advisor'] = filter_params['advisor']

        if 'manager' in allowed and filter_params.get('manager'):
            keep_params['manager'] = filter_params['manager']

        if 'office' in allowed and filter_params.get('office'):
            keep_params['office'] = filter_params['office']

        return urlencode(keep_params)

    def process_deals_for_template(self, deals_qs: QuerySet) -> list:
        """
        Post-process deals queryset to add helper attributes for template rendering.

        This extracts manager/office information and sets user-specific commission status.

        Args:
            deals_qs: Queryset of Deal objects

        Returns:
            List of Deal objects with added helper attributes
        """
        deals = []

        for d in deals_qs:
            rp = getattr(d.lead.referrer, 'referrer_profile', None)
            manager = getattr(rp, 'manager', None) if rp else None
            office = getattr(getattr(manager, 'manager_profile', None), 'office', None) if manager else None

            d.referrer_name = str(d.lead.referrer)
            d.referrer_id = d.lead.referrer.pk if d.lead.referrer else None
            d.manager_name = str(manager) if manager else None
            d.manager_id = manager.pk if manager else None
            d.office_name = office.name if office else None
            d.office_owner_id = office.owner.pk if office and office.owner else None
            d.advisor_name = str(d.lead.advisor) if d.lead.advisor else None
            d.advisor_id = d.lead.advisor.pk if d.lead.advisor else None

            # Helper pro kontrolu vyplacení provizí relevantních pro aktuálního uživatele
            if self.user.role == User.Role.REFERRER:
                # Doporučitel sleduje jen svou provizi
                d.user_commissions_paid = d.paid_referrer
            elif self.user.role == User.Role.REFERRER_MANAGER:
                # Manažer sleduje provizi makléře + svou
                d.user_commissions_paid = d.paid_referrer and (not manager or d.paid_manager)
            elif self.user.role == User.Role.OFFICE:
                # Kancelář sleduje všechny tři (makléř + manažer + kancelář)
                d.user_commissions_paid = d.all_commissions_paid
            else:
                # Admin/Advisor vidí všechny
                d.user_commissions_paid = d.all_commissions_paid

            deals.append(d)

        return deals
