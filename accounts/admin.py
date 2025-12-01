from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, ReferrerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("LeadBridge role", {"fields": ("role",)}),
    )

    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")


@admin.register(ReferrerProfile)
class ReferrerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "manager")
    list_filter = ("manager",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    filter_horizontal = ("advisors",)


