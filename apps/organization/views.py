"""apps/organization/views.py"""
import logging
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.views.generic import FormView, UpdateView, View
from django.contrib import messages

from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin
from .models import Organization
from .forms import OrganizationSetupForm, OrganizationUpdateForm

logger = logging.getLogger(__name__)

class OrganizationSetupView(BillingLoginRequiredMixin, PageTitleMixin, FormView):
    """
    Wizard view to set up the organization for the first time.
    """
    template_name = "organization/setup.html"
    form_class = OrganizationSetupForm
    page_title = "Organization Setup — Advance Billing"
    success_url = reverse_lazy("dashboard:index")

    def dispatch(self, request, *args, **kwargs):
        # If user already has an organization, redirect them to dashboard
        if hasattr(request.user, 'organization'):
            return redirect("dashboard:index")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill email with signup email
        initial["business_email"] = self.request.user.email
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pop it so it only shows once
        context['org_deleted'] = self.request.session.pop('org_deleted', False)
        return context

    def form_valid(self, form):
        organization = form.save(commit=False)
        organization.owner = self.request.user
        organization.save()
        messages.success(self.request, "Organization setup successfully!")
        return super().form_valid(form)


class OrganizationDetailView(BillingLoginRequiredMixin, PageTitleMixin, UpdateView):
    """
    View to edit an existing organization's details.
    """
    template_name = "organization/detail.html"
    form_class = OrganizationUpdateForm
    page_title = "Organization Settings — Advance Billing"
    success_url = reverse_lazy("organization:index")

    def get_object(self, queryset=None):
        return self.request.user.organization

    def form_valid(self, form):
        messages.success(self.request, "Organization details updated successfully.")
        return super().form_valid(form)


from django.http import JsonResponse

class OrganizationDeleteView(BillingLoginRequiredMixin, View):
    """
    View to delete the user's organization.
    """
    def post(self, request, *args, **kwargs):
        if hasattr(request.user, 'organization'):
            request.user.organization.delete()
            request.session['org_deleted'] = True
            
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'redirect_url': str(reverse_lazy("dashboard:index"))})
            
        messages.success(request, "Organization deleted successfully. Please set up a new one.")
        return redirect("dashboard:index")
