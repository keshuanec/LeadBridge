from django.urls import path
from . import views

urlpatterns = [
    path("", views.my_leads, name="my_leads"),
    path('lead/new/', views.lead_create, name='lead_create'),
    path("lead/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("lead/<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("deals/", views.deals_list, name="deals_list"),
    path("referrers/", views.referrers_list, name="referrers_list"),
]