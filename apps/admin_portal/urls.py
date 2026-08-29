from django.urls import path
from . import views

app_name = "admin_portal"

urlpatterns = [
    path("login/", views.AdminLoginView.as_view(), name="login"),
    path("logout/", views.AdminLogoutView.as_view(), name="logout"),
    path("", views.AdminDashboardView.as_view(), name="dashboard"),
    path("requests/<int:pk>/approve/", views.AdminApproveRequestView.as_view(), name="approve_request"),
    path("requests/<int:pk>/reject/", views.AdminRejectRequestView.as_view(), name="reject_request"),
    path("diagnostics/smtp/", views.SmtpDiagnosticView.as_view(), name="smtp_diagnostic"),
]
