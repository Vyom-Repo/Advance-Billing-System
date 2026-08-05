"""apps/settings_app/urls.py"""
from django.urls import path
from . import views

app_name = "settings_app"

urlpatterns = [
    path("", views.SettingsSettingsComingSoon.as_view(), name="index"),
]
