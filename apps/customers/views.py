"""
apps/customers/views.py — Customer Views
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin
from apps.organization.models import Organization
from .models import Customer
from .forms import CustomerForm


class CustomerOrganizationMixin(BillingLoginRequiredMixin):
    """
    Mixin ensuring all customer operations are strictly scoped
    to the logged-in user's Organization.
    """
    def get_organization(self) -> Organization | None:
        return getattr(self.request.user, "organization", None)

    def get_queryset(self):
        org = self.get_organization()
        if not org:
            return Customer.objects.none()
        return Customer.objects.filter(organization=org)

    def dispatch(self, request, *args, **kwargs):
        org = self.get_organization()
        if not org:
            messages.warning(request, "Please set up your organization before managing customers.")
            return redirect("organization:index")
        return super().dispatch(request, *args, **kwargs)


class CustomerListView(CustomerOrganizationMixin, PageTitleMixin, ListView):
    model = Customer
    template_name = "customers/list.html"
    context_object_name = "customers"
    page_title = "Customers — Advance Billing"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(name__icontains=query) | Q(gstin__icontains=query) | Q(billing_city__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["total_count"] = self.get_queryset().count()
        return context


class CustomerCreateView(CustomerOrganizationMixin, PageTitleMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/form.html"
    page_title = "Create Customer — Advance Billing"
    success_url = reverse_lazy("customers:index")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.get_organization()
        return kwargs

    def form_valid(self, form):
        form.instance.organization = self.get_organization()
        messages.success(self.request, f"Customer '{form.instance.name}' created successfully.")
        return super().form_valid(form)


class CustomerDetailView(CustomerOrganizationMixin, PageTitleMixin, DetailView):
    pk_url_kwarg = None
    lookup_field = "uuid"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    template_name = "customers/detail.html"
    context_object_name = "customer"

    def get_page_title(self) -> str:
        customer = self.get_object()
        return f"{customer.name} — Customers — Advance Billing"


class CustomerUpdateView(CustomerOrganizationMixin, PageTitleMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/form.html"
    context_object_name = "customer"
    pk_url_kwarg = None
    lookup_field = "uuid"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    success_url = reverse_lazy("customers:index")

    def get_page_title(self) -> str:
        customer = self.get_object()
        return f"Edit {customer.name} — Advance Billing"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.get_organization()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Customer '{form.instance.name}' updated successfully.")
        return super().form_valid(form)


class CustomerDeleteView(CustomerOrganizationMixin, PageTitleMixin, DeleteView):
    model = Customer
    template_name = "customers/confirm_delete.html"
    context_object_name = "customer"
    pk_url_kwarg = None
    lookup_field = "uuid"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    success_url = reverse_lazy("customers:index")
    page_title = "Delete Customer — Advance Billing"

    def post(self, request, *args, **kwargs):
        customer = self.get_object()

        # Check if customer has dependent invoice records
        if hasattr(customer, "invoices") and customer.invoices.exists():
            messages.error(request, f"Cannot delete customer '{customer.name}' because they have associated invoice records.")
            return redirect("customers:detail", uuid=customer.uuid)

        messages.success(request, f"Customer '{customer.name}' deleted successfully.")
        return super().post(request, *args, **kwargs)
