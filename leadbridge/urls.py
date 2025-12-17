from django.contrib import admin
from django.urls import path, include
from leads import views  # 👈 DŮLEŽITÉ

urlpatterns = [
    path("admin/", admin.site.urls),

    path("accounts/", include("django.contrib.auth.urls")),  # login/logout
    path("account/", include("accounts.urls")),              # user settings

    # DOMOVSKÁ STRÁNKA
    path("", views.overview, name="overview"),

    # LEADS A DALŠÍ FUNKCE
    path("leads/", include("leads.urls")),
]
