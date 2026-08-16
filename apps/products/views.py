"""
apps/products/views.py — Product Views

All views are strictly organization-scoped.
The organization is always derived from request.user.organization;
it is never accepted from URL parameters or POST data.
"""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin
from apps.organization.models import Organization
from .models import Product
from .forms import ProductForm


class ProductOrganizationMixin(BillingLoginRequiredMixin):
    """
    Mixin ensuring all product operations are strictly scoped
    to the logged-in user's Organization.

    Mirrors CustomerOrganizationMixin from apps/customers/views.py.
    """

    def get_organization(self) -> Organization | None:
        return getattr(self.request.user, "organization", None)

    def get_queryset(self):
        org = self.get_organization()
        if not org:
            return Product.objects.none()
        return Product.objects.filter(organization=org)

    def dispatch(self, request, *args, **kwargs):
        org = self.get_organization()
        if not org:
            messages.warning(
                request,
                "Please set up your organization before managing products.",
            )
            return redirect("organization:index")
        return super().dispatch(request, *args, **kwargs)


class ProductListView(ProductOrganizationMixin, PageTitleMixin, ListView):
    model = Product
    template_name = "products/list.html"
    context_object_name = "products"
    page_title = "Products & Services — Advance Billing"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        type_filter = self.request.GET.get("type", "").strip()

        if query:
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(hsn_code__icontains=query)
                | Q(sac_code__icontains=query)
            )
        if type_filter in ("goods", "service"):
            qs = qs.filter(product_type=type_filter)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["type_filter"] = self.request.GET.get("type", "").strip()
        context["total_count"] = self.get_queryset().count()
        return context


class ProductCreateView(ProductOrganizationMixin, PageTitleMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "products/form.html"
    page_title = "Create Product — Advance Billing"
    success_url = reverse_lazy("products:index")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.get_organization()
        return kwargs

    def form_valid(self, form):
        form.instance.organization = self.get_organization()
        messages.success(
            self.request,
            f"Product '{form.instance.name}' created successfully.",
        )
        return super().form_valid(form)


class ProductDetailView(ProductOrganizationMixin, PageTitleMixin, DetailView):
    pk_url_kwarg = None
    lookup_field = "uuid"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    template_name = "products/detail.html"
    context_object_name = "product"

    def get_page_title(self) -> str:
        product = self.get_object()
        return f"{product.name} — Products — Advance Billing"


class ProductUpdateView(ProductOrganizationMixin, PageTitleMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "products/form.html"
    context_object_name = "product"
    pk_url_kwarg = None
    lookup_field = "uuid"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    success_url = reverse_lazy("products:index")

    def get_page_title(self) -> str:
        product = self.get_object()
        return f"Edit {product.name} — Advance Billing"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.get_organization()
        return kwargs

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Product '{form.instance.name}' updated successfully.",
        )
        return super().form_valid(form)


class ProductDeleteView(ProductOrganizationMixin, PageTitleMixin, DeleteView):
    model = Product
    template_name = "products/confirm_delete.html"
    context_object_name = "product"
    pk_url_kwarg = None
    lookup_field = "uuid"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    success_url = reverse_lazy("products:index")
    page_title = "Delete Product — Advance Billing"

    def post(self, request, *args, **kwargs):
        product = self.get_object()

        # Protect historical invoice records.
        # When an InvoiceLine model is introduced, it should set
        # product = ForeignKey(Product, on_delete=models.PROTECT).
        # Until then, guard via the reverse accessor if it exists.
        if hasattr(product, "invoice_lines") and product.invoice_lines.exists():
            messages.error(
                request,
                f"Cannot delete '{product.name}' because it is referenced by "
                "existing invoice records. Edit the product instead.",
            )
            return redirect("products:detail", uuid=product.uuid)

        messages.success(
            request,
            f"Product '{product.name}' deleted successfully.",
        )
        return super().post(request, *args, **kwargs)
