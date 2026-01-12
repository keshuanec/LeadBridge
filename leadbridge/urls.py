from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from leads import views  # 👈 DŮLEŽITÉ

urlpatterns = [
    path("admin/", admin.site.urls),

    path("accounts/", include("django.contrib.auth.urls")),  # login/logout
    path("account/", include("accounts.urls")),              # user settings

    # LANDING PAGE (pro nepřihlášené uživatele)
    path("", views.landing_page, name="landing_page"),

    # PŘEHLED (domovská stránka pro přihlášené)
    path("overview/", views.overview, name="overview"),

    # LEADS A DALŠÍ FUNKCE
    path("leads/", include("leads.urls")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
