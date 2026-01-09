"""
Context processors pro globální dostupnost dat v šablonách.
"""
from accounts.models import BrandingSettings, User


def branding(request):
    """
    Načte nastavení brandingu pro aktuálního uživatele.

    Logika:
    - Pokud je uživatel poradce s admin přístupem a má vlastní branding, použije se jeho
    - Pokud je uživatel podřízený (referrer, advisor bez admin), najde se nadřízený advisor
      s admin přístupem a použije se jeho branding
    - Jinak se použijí defaultní hodnoty
    """
    if not request.user.is_authenticated:
        return {
            'branding': None,
            'navbar_color': '#1F6F7A',
            'navbar_text_color': '#FFFFFF',
            'custom_logo': None,
        }

    user = request.user
    branding_settings = None

    # 1. Pokud je uživatel advisor s admin přístupem, zkusit načíst jeho branding
    if user.role == User.Role.ADVISOR and user.has_admin_access:
        try:
            branding_settings = user.branding_settings
        except BrandingSettings.DoesNotExist:
            pass

    # 2. Pokud je uživatel referrer, najít jeho manažera/kancelář a pak advisora s admin přístupem
    elif user.role in [User.Role.REFERRER, User.Role.REFERRER_MANAGER, User.Role.OFFICE]:
        # Najít advisora s admin přístupem v hierarchii
        # Referreři mají přiřazené advisors přes ReferrerProfile
        try:
            referrer_profile = user.referrer_profile
            # Najít mezi přiřazenými poradci toho s admin přístupem
            admin_advisor = referrer_profile.advisors.filter(
                role=User.Role.ADVISOR,
                has_admin_access=True
            ).first()

            if admin_advisor:
                try:
                    branding_settings = admin_advisor.branding_settings
                except BrandingSettings.DoesNotExist:
                    pass
        except Exception:
            pass

    # 3. Pokud je uživatel advisor bez admin přístupu, najít advisora s admin přístupem
    elif user.role == User.Role.ADVISOR and not user.has_admin_access:
        # Najít advisora s admin přístupem, který má tohoto uživatele jako referrera
        # nebo zkusit najít přes referrers, kteří mají tohoto advisora
        try:
            # Najít referrera, který má tohoto advisora v advisors a zároveň najít admin advisora
            from accounts.models import ReferrerProfile
            profiles = ReferrerProfile.objects.filter(advisors=user)

            for profile in profiles:
                admin_advisors = profile.advisors.filter(
                    role=User.Role.ADVISOR,
                    has_admin_access=True
                )
                if admin_advisors.exists():
                    admin_advisor = admin_advisors.first()
                    try:
                        branding_settings = admin_advisor.branding_settings
                        break
                    except BrandingSettings.DoesNotExist:
                        continue
        except Exception:
            pass

    # Vrátit hodnoty
    if branding_settings:
        return {
            'branding': branding_settings,
            'navbar_color': branding_settings.navbar_color,
            'navbar_text_color': branding_settings.navbar_text_color,
            'custom_logo': branding_settings.logo.url if branding_settings.logo else None,
        }
    else:
        return {
            'branding': None,
            'navbar_color': '#1F6F7A',
            'navbar_text_color': '#FFFFFF',
            'custom_logo': None,
        }
