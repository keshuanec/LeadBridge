"""
Služba pro odesílání emailových notifikací uživatelům.
"""
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from accounts.models import User


def get_notification_recipients(lead, event_type, deal=None, exclude_user=None):
    """
    Určí, kdo má dostat notifikaci podle typu události.

    Args:
        lead: Lead instance
        event_type: typ události ('lead_change' nebo 'commission_change')
        deal: Deal instance (volitelné, pro události týkající se obchodů)
        exclude_user: User, který akci provedl (nedostane notifikaci)

    Returns:
        list: seznam User objektů, kteří mají dostat notifikaci

    Logika příjemců:
    - lead_change: makléř + poradce (manažer a kancelář NE)
    - commission_change: makléř + poradce + manažer + kancelář
    """
    recipients = []

    # Získání souvisejících uživatelů
    referrer = lead.referrer
    advisor = lead.advisor

    # Manažer a kancelář
    rp = getattr(referrer, "referrer_profile", None)
    manager = getattr(rp, "manager", None) if rp else None
    manager_profile = getattr(manager, "manager_profile", None) if manager else None
    office = getattr(manager_profile, "office", None) if manager_profile else None
    office_owner = getattr(office, "owner", None) if office else None

    # Makléř a poradce dostanou všechny notifikace
    if referrer and referrer != exclude_user:
        recipients.append(referrer)
    if advisor and advisor != exclude_user:
        recipients.append(advisor)

    # Manažer a kancelář dostanou JEN notifikace o provizích
    if event_type == 'commission_change':
        if manager and manager != exclude_user:
            recipients.append(manager)
        if office_owner and office_owner != exclude_user:
            recipients.append(office_owner)

    # Odstranit duplicity a None hodnoty
    recipients = [r for r in recipients if r and r.email]
    return list(set(recipients))


def send_notification_email(recipients, subject, message, html_message=None):
    """
    Odešle notifikační email příjemcům.

    Args:
        recipients: list User objektů
        subject: předmět emailu
        message: textová verze zprávy
        html_message: HTML verze zprávy (volitelné)
    """
    if not recipients:
        return

    recipient_emails = [user.email for user in recipients if user.email]

    if not recipient_emails:
        return

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@leadbridge.cz',
            recipient_list=recipient_emails,
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        # Logování chyby (v produkci byste měli použít proper logging)
        print(f"Chyba při odesílání emailu: {e}")


def notify_lead_created(lead, created_by):
    """Notifikace při vytvoření nového leadu"""
    recipients = get_notification_recipients(
        lead,
        event_type='lead_change',
        exclude_user=created_by
    )

    subject = f"Nový lead: {lead.client_name}"
    message = f"""
Byl vytvořen nový lead.

Klient: {lead.client_name}
Telefon: {lead.client_phone or '—'}
Email: {lead.client_email or '—'}
Doporučitel: {lead.referrer}
Poradce: {lead.advisor or '—'}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_lead_updated(lead, updated_by, changes_description=None):
    """Notifikace při aktualizaci leadu"""
    recipients = get_notification_recipients(
        lead,
        event_type='lead_change',
        exclude_user=updated_by
    )

    subject = f"Lead aktualizován: {lead.client_name}"
    message = f"""
Lead byl aktualizován.

Klient: {lead.client_name}
Aktualizoval: {updated_by}
{f'Změny: {changes_description}' if changes_description else ''}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_note_added(lead, note, added_by):
    """Notifikace při přidání poznámky"""
    recipients = get_notification_recipients(
        lead,
        event_type='lead_change',
        exclude_user=added_by
    )

    subject = f"Nová poznámka: {lead.client_name}"
    message = f"""
Byla přidána nová poznámka k leadu.

Klient: {lead.client_name}
Autor poznámky: {added_by}
Poznámka: {note.text}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_meeting_scheduled(lead, scheduled_by):
    """Notifikace při naplánování schůzky"""
    recipients = get_notification_recipients(
        lead,
        event_type='lead_change',
        exclude_user=scheduled_by
    )

    subject = f"Schůzka naplánována: {lead.client_name}"
    message = f"""
Byla naplánována schůzka.

Klient: {lead.client_name}
Datum a čas: {lead.meeting_at.strftime('%d.%m.%Y %H:%M') if lead.meeting_at else '—'}
Poznámka: {lead.meeting_note or '—'}
Naplánoval: {scheduled_by}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_meeting_completed(lead, completed_by, next_action):
    """Notifikace po proběhnutí schůzky"""
    recipients = get_notification_recipients(
        lead,
        event_type='lead_change',
        exclude_user=completed_by
    )

    subject = f"Schůzka proběhla: {lead.client_name}"
    message = f"""
Schůzka byla označena jako proběhlá.

Klient: {lead.client_name}
Další krok: {next_action}
Označil: {completed_by}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_deal_created(deal, lead, created_by):
    """Notifikace při vytvoření obchodu"""
    recipients = get_notification_recipients(
        lead,
        event_type='lead_change',
        deal=deal,
        exclude_user=created_by
    )

    subject = f"Založen obchod: {deal.client_name}"
    message = f"""
Byl založen nový obchod!

Klient: {deal.client_name}
Výše úvěru: {deal.loan_amount:,} Kč
Banka: {deal.get_bank_display()}
Založil: {created_by}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_deal_updated(deal, updated_by, changes_description=None):
    """Notifikace při aktualizaci obchodu"""
    recipients = get_notification_recipients(
        deal.lead,
        event_type='lead_change',
        deal=deal,
        exclude_user=updated_by
    )

    subject = f"Obchod aktualizován: {deal.client_name}"
    message = f"""
Obchod byl aktualizován.

Klient: {deal.client_name}
Aktualizoval: {updated_by}
{f'Změny: {changes_description}' if changes_description else ''}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_commission_ready(deal, marked_by):
    """Notifikace při označení provize jako připravené k vyplacení"""
    recipients = get_notification_recipients(
        deal.lead,
        event_type='commission_change',  # Toto pošle i manažerovi a kanceláři
        deal=deal,
        exclude_user=marked_by
    )

    subject = f"Provize připravena: {deal.client_name}"
    message = f"""
Provize je připravena k vyplacení.

Klient: {deal.client_name}
Výše úvěru: {deal.loan_amount:,} Kč
Provize celkem: {deal.calculated_commission_total:,} Kč

Označil: {marked_by}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)


def notify_commission_paid(deal, recipient_type, marked_by):
    """Notifikace při vyplacení provize konkrétnímu uživateli"""
    recipients = get_notification_recipients(
        deal.lead,
        event_type='commission_change',  # Toto pošle i manažerovi a kanceláři
        deal=deal,
        exclude_user=marked_by
    )

    recipient_names = {
        'referrer': 'makléři',
        'manager': 'manažerovi',
        'office': 'kanceláři',
    }

    subject = f"Provize vyplacena {recipient_names.get(recipient_type, '')}: {deal.client_name}"
    message = f"""
Provize byla vyplacena {recipient_names.get(recipient_type, '')}.

Klient: {deal.client_name}
Označil: {marked_by}

Pro zobrazení detailu otevřete aplikaci LeadBridge.
"""

    send_notification_email(recipients, subject, message)