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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bank_accounts'] = self.request.user.organization.bank_accounts.all().order_by('-is_default', '-created_at')
        from .forms import BankAccountForm
        context['bank_form'] = BankAccountForm()
        return context

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

from .models import BankAccount
from .forms import BankAccountForm

class BankAccountCreateView(BillingLoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        org = request.user.organization
        form = BankAccountForm(request.POST)
        if form.is_valid():
            bank_account = form.save(commit=False)
            bank_account.organization = org
            
            # If it's the first account, make it default
            if not org.bank_accounts.exists():
                bank_account.is_default = True
            else:
                bank_account.is_default = False
                
            bank_account.save()
            messages.success(request, "Bank account added successfully.")
        else:
            messages.error(request, "Error adding bank account. Please check the details.")
            
        return redirect("organization:index")

class BankAccountUpdateView(BillingLoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        org = request.user.organization
        bank_account = org.bank_accounts.filter(pk=pk).first()
        if not bank_account:
            messages.error(request, "Bank account not found.")
            return redirect("organization:index")
            
        form = BankAccountForm(request.POST, instance=bank_account)
        if form.is_valid():
            form.save()
            messages.success(request, "Bank account updated successfully.")
        else:
            messages.error(request, "Error updating bank account.")
            
        return redirect("organization:index")

class BankAccountDeleteView(BillingLoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        org = request.user.organization
        bank_account = org.bank_accounts.filter(pk=pk).first()
        if bank_account:
            was_default = bank_account.is_default
            bank_account.delete()
            messages.success(request, "Bank account deleted.")
            
            # If we deleted the default account, make the first remaining account default
            if was_default:
                first_remaining = org.bank_accounts.first()
                if first_remaining:
                    first_remaining.is_default = True
                    first_remaining.save()
        else:
            messages.error(request, "Bank account not found.")
            
        return redirect("organization:index")

class BankAccountDefaultView(BillingLoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        org = request.user.organization
        bank_account = org.bank_accounts.filter(pk=pk).first()
        if bank_account:
            # Remove default from others
            org.bank_accounts.update(is_default=False)
            # Set this as default
            bank_account.is_default = True
            bank_account.save()
            messages.success(request, f"{bank_account.bank_name} set as default.")
        
        return redirect("organization:index")

from django.template.loader import render_to_string
from django.http import HttpResponse

class OrganizationLetterheadPreviewView(BillingLoginRequiredMixin, View):
    """
    Returns an inline PDF for the letterhead safe area preview.
    Uses the saved letterhead but allows overriding offsets via GET parameters.
    Uses the unified InvoicePreviewService rendering pipeline with automatic fallback.
    """
    def get(self, request, *args, **kwargs):
        from apps.invoices.services.invoice_preview_service import InvoicePreviewService
        from apps.invoices.services.bill_serializer import serialize_bill_for_render
        from apps.common.services.sample_data_service import SampleDataService
        from apps.common.services.organization_service import OrganizationService
        from apps.common.services.layout_engine import PrintableFrameBuilder
        from apps.settings_app.models import DocumentPreference

        header_offset = request.GET.get('header', None)
        footer_offset = request.GET.get('footer', None)

        try:
            doc_pref = DocumentPreference.objects.get(user=request.user)
            template_slug = doc_pref.template_name
        except DocumentPreference.DoesNotExist:
            template_slug = "compact_template"

        request_overrides = {"print_on_letterhead": True}
        config = InvoicePreviewService.resolve_render_config(
            template_slug=template_slug,
            user=request.user,
            request_overrides=request_overrides,
        )

        org_data = OrganizationService.get_company_assets(request.user)
        if org_data:
            org_obj = org_data["organization"]
            if header_offset is not None:
                org_obj.letterhead_header_offset = int(header_offset)
            if footer_offset is not None:
                org_obj.letterhead_footer_offset = int(footer_offset)
            company = {
                "name":    org_data["business_name"],
                "address": f"{org_data['address_line_1']} {org_data['address_line_2']}".strip(),
                "city":    org_data["city"],
                "state":   org_data["state"],
                "gstin":   org_data["gstin"],
                "email":   org_data["email"],
                "phone":   org_data["phone"],
            }
            if org_data["default_bank"]:
                company["bank_name"] = org_data["default_bank"].bank_name
                company["acc_no"]    = org_data["default_bank"].account_number
                company["ifsc"]      = org_data["default_bank"].ifsc_code
        else:
            org_obj = None
            company = SampleDataService.sample_company()

        invoice  = SampleDataService.sample_invoice(request.user)
        customer = SampleDataService.sample_customer()
        items    = SampleDataService.sample_items()

        bill_data    = serialize_bill_for_render(invoice, customer, items, company, org_obj)
        layout_frame = PrintableFrameBuilder.build_frame(org_obj, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=bill_data,
            config=config,
            template_file_path=f"pdf/{template_slug}.html",
            layout_frame=layout_frame,
            org=org_obj,
        )

        return HttpResponse(pdf_bytes, content_type='application/pdf')

