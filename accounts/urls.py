from django.urls import path
from . import views

urlpatterns = [
    path("settings/", views.user_settings, name="user_settings"),
    path("settings/edit/", views.edit_profile, name="edit_profile"),
    path("settings/password/", views.change_password, name="change_password"),
    # TODO: Branding system - zakomentováno pro budoucí použití
    # path("settings/branding/", views.branding_settings, name="branding_settings"),
]
