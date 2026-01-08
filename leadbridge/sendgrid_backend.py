"""
Custom email backend using SendGrid Python API instead of SMTP.
This avoids timeout issues with SMTP connections.
"""
import logging
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)


class SendGridBackend(BaseEmailBackend):
    """
    SendGrid API backend for Django email.
    Uses SendGrid Python SDK instead of SMTP for faster, more reliable delivery.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'SENDGRID_API_KEY', None)
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("SENDGRID_API_KEY not found in settings")
            logger.warning("SENDGRID_API_KEY not configured")

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of email
        messages sent.
        """
        if not email_messages:
            return 0

        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("SENDGRID_API_KEY not configured")
            return 0

        sg_client = SendGridAPIClient(self.api_key)
        num_sent = 0

        for message in email_messages:
            try:
                # Build SendGrid email
                from_email = Email(message.from_email)
                to_emails = [To(email) for email in message.to]

                # Get plain text body
                plain_text = message.body

                # Check for HTML content in alternatives
                html_content = None
                if hasattr(message, 'alternatives') and message.alternatives:
                    for alternative in message.alternatives:
                        if alternative[1] == 'text/html':
                            html_content = alternative[0]
                            break

                # Create Mail object with both plain text and HTML
                mail = Mail(
                    from_email=from_email,
                    to_emails=to_emails,
                    subject=message.subject,
                    plain_text_content=plain_text,
                    html_content=html_content
                )

                # Send email
                response = sg_client.send(mail)

                if response.status_code in (200, 201, 202):
                    num_sent += 1
                    logger.info(
                        f"Email sent successfully via SendGrid API: "
                        f"subject='{message.subject}', to={message.to}, "
                        f"status_code={response.status_code}"
                    )
                else:
                    logger.error(
                        f"SendGrid API returned non-success status: "
                        f"status_code={response.status_code}, body={response.body}"
                    )
                    if not self.fail_silently:
                        raise Exception(f"SendGrid API error: {response.status_code}")

            except Exception as e:
                logger.error(f"Error sending email via SendGrid API: {e}", exc_info=True)
                if not self.fail_silently:
                    raise

        return num_sent
