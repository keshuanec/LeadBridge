"""
Model Helper Service for Lead Bridge CRM

This service provides helper methods for safely traversing complex model
relationships, eliminating repetitive getattr chains throughout the codebase.

Author: Refactored from leads/views.py
Date: 2026-01-21
"""

from typing import Optional, Dict, Any
from accounts.models import User, Office


class LeadHierarchyHelper:
    """
    Helper class for navigating the referrer → manager → office hierarchy.

    This eliminates complex nested getattr() chains like:
        rp = getattr(lead.referrer, "referrer_profile", None)
        manager = getattr(rp, "manager", None) if rp else None
        office = getattr(getattr(manager, "manager_profile", None), "office", None) if manager else None

    Usage:
        helper = LeadHierarchyHelper(lead)
        manager = helper.get_manager()
        office = helper.get_office()
    """

    def __init__(self, lead_or_user):
        """
        Initialize with either a Lead or User object.

        Args:
            lead_or_user: Lead object or User object (referrer)
        """
        from leads.models import Lead

        if isinstance(lead_or_user, Lead):
            self.lead = lead_or_user
            self.user = lead_or_user.referrer
        else:
            # It's a User object
            self.lead = None
            self.user = lead_or_user

    def get_referrer_profile(self):
        """
        Get ReferrerProfile for the user.

        Returns:
            ReferrerProfile object or None
        """
        return getattr(self.user, 'referrer_profile', None) if self.user else None

    def get_manager(self) -> Optional[User]:
        """
        Get manager from referrer's profile.

        Returns:
            Manager User object or None
        """
        rp = self.get_referrer_profile()
        return getattr(rp, 'manager', None) if rp else None

    def get_office(self) -> Optional[Office]:
        """
        Get office from manager's profile.

        Returns:
            Office object or None
        """
        manager = self.get_manager()
        if not manager:
            return None

        manager_profile = getattr(manager, 'manager_profile', None)
        return getattr(manager_profile, 'office', None) if manager_profile else None

    def get_hierarchy_dict(self) -> Dict[str, Any]:
        """
        Get complete hierarchy information as a dictionary.

        Returns:
            Dictionary with keys: referrer, referrer_profile, manager, office, advisor (if lead)
        """
        result = {
            'referrer': self.user,
            'referrer_profile': self.get_referrer_profile(),
            'manager': self.get_manager(),
            'office': self.get_office(),
        }

        if self.lead:
            result['advisor'] = self.lead.advisor

        return result

    @staticmethod
    def get_manager_from_referrer(referrer: User) -> Optional[User]:
        """
        Static method to get manager from a referrer User.

        Args:
            referrer: User object with role REFERRER

        Returns:
            Manager User object or None
        """
        rp = getattr(referrer, 'referrer_profile', None)
        return getattr(rp, 'manager', None) if rp else None

    @staticmethod
    def get_office_from_manager(manager: User) -> Optional[Office]:
        """
        Static method to get office from a manager User.

        Args:
            manager: User object with role REFERRER_MANAGER

        Returns:
            Office object or None
        """
        mp = getattr(manager, 'manager_profile', None)
        return getattr(mp, 'office', None) if mp else None

    @staticmethod
    def get_office_from_referrer(referrer: User) -> Optional[Office]:
        """
        Static method to get office directly from a referrer User.

        This combines get_manager_from_referrer and get_office_from_manager.

        Args:
            referrer: User object with role REFERRER

        Returns:
            Office object or None
        """
        manager = LeadHierarchyHelper.get_manager_from_referrer(referrer)
        if not manager:
            return None
        return LeadHierarchyHelper.get_office_from_manager(manager)
