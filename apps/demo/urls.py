from django.urls import path
from . import views

app_name = "demo"

urlpatterns = [
    path("", views.DemoEntryView.as_view(), name="entry"),
    path("reset/", views.DemoResetView.as_view(), name="reset"),
    path("exit/", views.DemoExitView.as_view(), name="exit"),
]
