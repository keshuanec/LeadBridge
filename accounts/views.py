from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def user_settings(request):
    user = request.user
    return render(request, "accounts/user_settings.html", {"user": user})
