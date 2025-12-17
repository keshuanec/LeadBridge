from django.urls import path
from . import views

urlpatterns = [
    path("", views.my_leads, name="my_leads"),
    path("new/", views.lead_create, name="lead_create"),
    path("<int:pk>/", views.lead_detail, name="lead_detail"),
    path("<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("<int:pk>/meeting/", views.lead_schedule_meeting, name="lead_schedule_meeting"),
    path("deals/", views.deals_list, name="deals_list"),
    path("referrers/", views.referrers_list, name="referrers_list"),
    path("<int:pk>/deal/new/", views.deal_create_from_lead, name="deal_create_from_lead"),
]
