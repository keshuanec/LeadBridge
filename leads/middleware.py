from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from leads.models import ActivityLog


def get_client_ip(request):
    """Získá IP adresu klienta z requestu"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Loguje přihlášení uživatele"""
    ActivityLog.objects.create(
        user=user,
        activity_type=ActivityLog.ActivityType.LOGIN,
        description=f"Uživatel {user.get_full_name()} se přihlásil",
        ip_address=get_client_ip(request),
        metadata={
            'username': user.username,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
        }
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Loguje odhlášení uživatele"""
    if user:  # user může být None pokud session expirovala
        ActivityLog.objects.create(
            user=user,
            activity_type=ActivityLog.ActivityType.LOGOUT,
            description=f"Uživatel {user.get_full_name()} se odhlásil",
            ip_address=get_client_ip(request),
        )
