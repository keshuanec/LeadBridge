from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from leads import views  # 👈 DŮLEŽITÉ
from accounts.import_view import import_users_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin/import-users/", import_users_view, name="import_users_view"),  # One-time import

    path("accounts/", include("django.contrib.auth.urls")),  # login/logout
    path("account/", include("accounts.urls")),              # user settings

    # DOMOVSKÁ STRÁNKA
    path("", views.overview, name="overview"),

    # LEADS A DALŠÍ FUNKCE
    path("leads/", include("leads.urls")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
