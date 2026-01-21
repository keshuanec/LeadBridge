"""
Lead Bridge Services

This package contains service layers that encapsulate business logic
for the Lead Bridge CRM system.

Services:
- access_control: Role-based access control for leads and deals
- notifications: Email notification system
- user_stats: User statistics calculations
- filters: List view filtering and sorting
- model_helpers: Helper methods for model relationship traversal
- events: Event recording with history and notifications
"""

from .access_control import LeadAccessService
from .user_stats import UserStatsService, Stats, AdvisorStatsDetailed, ReferrerStatsDetailed
from .filters import ListFilterService
from .model_helpers import LeadHierarchyHelper
from .events import LeadEventService

__all__ = [
    'LeadAccessService',
    'UserStatsService',
    'Stats',
    'AdvisorStatsDetailed',
    'ReferrerStatsDetailed',
    'ListFilterService',
    'LeadHierarchyHelper',
    'LeadEventService',
]
