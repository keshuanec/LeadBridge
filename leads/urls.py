from django.urls import path
from . import views

urlpatterns = [
    path("", views.my_leads, name="my_leads"),
    path("new/", views.lead_create, name="lead_create"),
    path("<int:pk>/", views.lead_detail, name="lead_detail"),
    path("<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("<int:pk>/meeting/", views.lead_schedule_meeting, name="lead_schedule_meeting"),
    path("<int:pk>/meeting/completed/", views.lead_meeting_completed, name="lead_meeting_completed"),
    path("<int:pk>/meeting/cancelled/", views.lead_meeting_cancelled, name="lead_meeting_cancelled"),
    path("deals/", views.deals_list, name="deals_list"),
    path("deals/<int:pk>/", views.deal_detail, name="deal_detail"),
    path("deals/<int:pk>/edit/", views.deal_edit, name="deal_edit"),
    path("deals/<int:pk>/commission/ready/", views.deal_commission_ready, name="deal_commission_ready"),
    path("deals/<int:pk>/commission/paid/<str:part>/", views.deal_commission_paid, name="deal_commission_paid"),
    path("referrers/", views.referrers_list, name="referrers_list"),
    path("referrers/<int:pk>/", views.referrer_detail, name="referrer_detail"),
    path("advisors/", views.advisors_list, name="advisors_list"),
    path("advisors/<int:pk>/", views.advisor_detail, name="advisor_detail"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("<int:pk>/deal/new/", views.deal_create_from_lead, name="deal_create_from_lead"),

]
