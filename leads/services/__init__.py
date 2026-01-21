"""
Lead Bridge Services

This package contains service layers that encapsulate business logic
for the Lead Bridge CRM system.

Services:
- access_control: Role-based access control for leads and deals
- notifications: Email notification system
- user_stats: User statistics calculations
- filters: List view filtering and sorting
"""

from .access_control import LeadAccessService
from .user_stats import UserStatsService, Stats, AdvisorStatsDetailed, ReferrerStatsDetailed
from .filters import ListFilterService

__all__ = [
    'LeadAccessService',
    'UserStatsService',
    'Stats',
    'AdvisorStatsDetailed',
    'ReferrerStatsDetailed',
    'ListFilterService',
]
