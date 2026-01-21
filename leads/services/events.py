"""
Lead Event Service for Lead Bridge CRM

This service encapsulates the always-paired pattern of creating history records
and sending notifications. This eliminates repetitive code throughout views.py
where LeadHistory.objects.create() is always followed by notifications.notify_*().

Author: Refactored from leads/views.py
Date: 2026-01-21
"""

from typing import Optional
from django.utils import timezone
from accounts.models import User
from ..models import Lead, Deal, LeadNote, LeadHistory
from . import notifications


class LeadEventService:
    """
    Service for recording lead/deal events with history and notifications.

    This service combines history logging and notification sending into single
    method calls, reducing code duplication and ensuring consistency.
    """

    @staticmethod
    def record_lead_created(lead: Lead, user: User) -> None:
        """
        Record lead creation event.

        Args:
            lead: The newly created Lead
            user: User who created the lead
        """
        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.CREATED,
            user=user,
            description="Lead založen.",
        )

        notifications.notify_lead_created(lead, created_by=user)

    @staticmethod
    def record_lead_updated(
        lead: Lead,
        user: User,
        changes_description: str,
        status_changed: bool = False
    ) -> None:
        """
        Record lead update event.

        Args:
            lead: The updated Lead
            user: User who updated the lead
            changes_description: Description of what changed
            status_changed: Whether the communication_status changed
        """
        LeadHistory.objects.create(
            lead=lead,
            event_type=(
                LeadHistory.EventType.STATUS_CHANGED
                if status_changed
                else LeadHistory.EventType.UPDATED
            ),
            user=user,
            description=changes_description,
        )

        notifications.notify_lead_updated(
            lead,
            updated_by=user,
            changes_description=changes_description
        )

    @staticmethod
    def record_note_added(
        lead: Lead,
        note: LeadNote,
        user: User,
        context: str = ""
    ) -> None:
        """
        Record note addition event.

        Args:
            lead: The Lead the note was added to
            note: The LeadNote that was created
            user: User who added the note
            context: Optional context (e.g., "z detailu obchodu")
        """
        description = f"Přidána soukromá poznámka{context}." if note.is_private else f"Přidána poznámka{context}."

        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.NOTE_ADDED,
            user=user,
            description=description,
            note=note,
        )

        # Notifikace - pouze pro veřejné poznámky
        if not note.is_private:
            notifications.notify_note_added(lead, note, added_by=user)

    @staticmethod
    def record_meeting_scheduled(
        lead: Lead,
        user: User,
        meeting_datetime: timezone.datetime,
        meeting_note: Optional[str] = None
    ) -> None:
        """
        Record meeting scheduling event.

        Args:
            lead: The Lead for which meeting was scheduled
            user: User who scheduled the meeting
            meeting_datetime: When the meeting is scheduled
            meeting_note: Optional note about the meeting
        """
        when = timezone.localtime(meeting_datetime).strftime("%d.%m.%Y %H:%M")

        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.MEETING_SCHEDULED,
            user=user,
            description=f"Domluvena schůzka na {when}.",
        )

        # pokud chceš mít poznámku i v seznamu poznámek
        if meeting_note:
            note = LeadNote.objects.create(
                lead=lead,
                author=user,
                text=f"Schůzka: {meeting_note}",
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.NOTE_ADDED,
                user=user,
                description="Přidána poznámka ke schůzce.",
                note=note,
            )

        notifications.notify_meeting_scheduled(lead, scheduled_by=user)

    @staticmethod
    def record_meeting_completed(
        lead: Lead,
        user: User,
        next_action_label: str,
        result_note: Optional[str] = None
    ) -> None:
        """
        Record meeting completion event.

        Args:
            lead: The Lead for which meeting was completed
            user: User who marked meeting as completed
            next_action_label: Label describing next action
            result_note: Optional note about meeting result
        """
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

        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.STATUS_CHANGED,
            user=user,
            description=f"Schůzka proběhla. Další krok: {next_action_label}",
        )

        notifications.notify_meeting_completed(
            lead,
            completed_by=user,
            next_action=next_action_label
        )

    @staticmethod
    def record_meeting_cancelled(
        lead: Lead,
        user: User,
        cancel_note: Optional[str] = None
    ) -> None:
        """
        Record meeting cancellation event.

        Args:
            lead: The Lead for which meeting was cancelled
            user: User who cancelled the meeting
            cancel_note: Optional note about cancellation reason
        """
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

        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.STATUS_CHANGED,
            user=user,
            description="Schůzka zrušena, lead označen jako neúspěšný.",
        )

    @staticmethod
    def record_callback_scheduled(
        lead: Lead,
        user: User,
        callback_date,
        callback_note: Optional[str] = None
    ) -> None:
        """
        Record callback scheduling event.

        Args:
            lead: The Lead for which callback was scheduled
            user: User who scheduled the callback
            callback_date: Date when callback is scheduled
            callback_note: Optional note about callback
        """
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

    @staticmethod
    def record_deal_created(deal: Deal, lead: Lead, user: User) -> None:
        """
        Record deal creation event.

        Args:
            deal: The newly created Deal
            lead: The Lead from which deal was created
            user: User who created the deal
        """
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

        notifications.notify_deal_created(deal, lead, created_by=user)

    @staticmethod
    def record_deal_updated(
        deal: Deal,
        user: User,
        changes_description: str,
        extra_note: Optional[str] = None
    ) -> None:
        """
        Record deal update event.

        Args:
            deal: The updated Deal
            user: User who updated the deal
            changes_description: Description of what changed
            extra_note: Optional extra note about the changes
        """
        lead = deal.lead

        # Zpracování extra poznámky
        if extra_note:
            note = LeadNote.objects.create(
                lead=lead,
                author=user,
                text=extra_note,
            )
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.NOTE_ADDED,
                user=user,
                description="Přidána poznámka ke změně obchodu.",
                note=note,
            )

        # Historie změn
        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.UPDATED,
            user=user,
            description=changes_description,
        )

        notifications.notify_deal_updated(
            deal,
            updated_by=user,
            changes_description=changes_description
        )

    @staticmethod
    def record_commission_ready(deal: Deal, user: User) -> None:
        """
        Record commission ready event.

        Args:
            deal: The Deal with commission ready
            user: User who marked commission as ready
        """
        LeadHistory.objects.create(
            lead=deal.lead,
            event_type=LeadHistory.EventType.UPDATED,
            user=user,
            description="Provize nastavena na: připravená k vyplacení.",
        )

        notifications.notify_commission_ready(deal, marked_by=user)

    @staticmethod
    def record_commission_paid(
        deal: Deal,
        user: User,
        recipient_type: str,
        changes_description: str,
        all_commissions_paid: bool = False
    ) -> None:
        """
        Record commission payment event.

        Args:
            deal: The Deal with commission paid
            user: User who marked commission as paid
            recipient_type: Type of recipient ('referrer', 'manager', 'office')
            changes_description: Description of what was paid
            all_commissions_paid: Whether all relevant commissions are now paid
        """
        lead = deal.lead

        LeadHistory.objects.create(
            lead=lead,
            event_type=LeadHistory.EventType.UPDATED,
            user=user,
            description=changes_description,
        )

        notifications.notify_commission_paid(
            deal,
            recipient_type=recipient_type,
            marked_by=user
        )

        # pokud jsou vyplacené všechny relevantní části, přepni lead na "Provize vyplacena"
        if all_commissions_paid:
            LeadHistory.objects.create(
                lead=lead,
                event_type=LeadHistory.EventType.STATUS_CHANGED,
                user=user,
                description="Změněn stav leadu: → Provize vyplacena",
            )
