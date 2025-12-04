from django.urls import path

from . import views

urlpatterns = [
    path("", views.my_leads, name="my_leads"),
    path('lead/new/', views.lead_create, name='lead_create'),
    path("deals/", views.deals_list, name="deals_list"),
    path("referrers/", views.referrers_list, name="referrers_list"),
]