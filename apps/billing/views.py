"""apps/billing/views.py — Invoice Application Layer Views (Phase 09)"""
import json
import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from apps.billing.forms import InvoiceForm, make_invoice_line_formset
from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.billing.services.calculation_engine import (
    validate_invoice,
    calculate_invoice,
    finalize_invoice,
)
from apps.billing.services.lifecycle import (
    cancel_invoice,
    delete_invoice,
    prepare_invoice_snapshots,
    populate_line_snapshot,
    resolve_place_of_supply,
)
from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product


# ---------------------------------------------------------------------------
# Organization Mixin
# ---------------------------------------------------------------------------

class InvoiceOrganizationMixin(BillingLoginRequiredMixin):
    """
    Ensures all invoice operations are strictly scoped to the logged-in user's Organization.
    Follows the exact same pattern as CustomerOrganizationMixin.
    """

    def get_organization(self) -> Organization | None:
        return getattr(self.request.user, "organization", None)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        org = self.get_organization()
        if not org:
            messages.warning(request, "Please set up your organization before managing invoices.")
            return redirect("organization:index")
        return super().dispatch(request, *args, **kwargs)

    def get_org_invoice(self, uuid):
        """Return an Invoice that belongs to the current organization, or 404."""
        org = self.get_organization()
        return get_object_or_404(Invoice, uuid=uuid, organization=org)


# ---------------------------------------------------------------------------
# Invoice List
# ---------------------------------------------------------------------------

class InvoiceListView(InvoiceOrganizationMixin, PageTitleMixin, ListView):
    model = Invoice
    template_name = "billing/list.html"
    context_object_name = "invoices"
    page_title = "Invoices — Advance Billing"
    paginate_by = 25

    def get_queryset(self):
        org = self.get_organization()
        qs = Invoice.objects.filter(organization=org).select_related("customer")
        status_filter = self.request.GET.get("status", "").strip()
        if status_filter in InvoiceStatus.values:
            qs = qs.filter(status=status_filter)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                invoice_number__icontains=query
            ) | qs.filter(
                customer_name_snapshot__icontains=query
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["status_filter"] = self.request.GET.get("status", "")
        context["InvoiceStatus"] = InvoiceStatus
        context["total_count"] = self.get_queryset().count()
        return context


# ---------------------------------------------------------------------------
# Invoice Create
# ---------------------------------------------------------------------------

class InvoiceCreateView(InvoiceOrganizationMixin, PageTitleMixin, View):
    template_name = "billing/form.html"
    page_title = "Create Invoice — Advance Billing"

    def _get_org_default_note(self, org):
        """Return the organization's configured default note, or empty string."""
        try:
            pref = org.owner.invoice_preference
            return pref.default_notes or ""
        except Exception:
            return ""

    def _get_context(self, form, formset, org, state_token=""):
        from apps.organization.services import LocalGSTValidator
        import json
        org_note = self._get_org_default_note(org)
        return {
            "form": form,
            "formset": formset,
            "page_title": self.page_title,
            "is_create": True,
            "InvoiceStatus": InvoiceStatus,
            "state_token": state_token,
            "org_default_note_json": json.dumps(org_note),
            "state_code_names": LocalGSTValidator.STATE_CODES,
        }

    def get(self, request):
        org = self.get_organization()
        FormSet = make_invoice_line_formset(org, extra=1)
        state_token = request.GET.get("invoice_state", "")
        new_customer_id = request.GET.get("new_customer", "")
        new_product_id = request.GET.get("new_product", "")
        line_index = request.GET.get("line_index", "")

        # --- Restore stashed state if returning from customer/product creation ---
        if state_token:
            stash = request.session.get("invoice_create_states", {})
            saved = stash.get(state_token)
            if saved:
                # One-time use: remove from session
                stash.pop(state_token)
                request.session["invoice_create_states"] = stash
                request.session.modified = True

                # Re-inject into POST-like dict so form renders correctly
                from django.http import QueryDict
                qd = QueryDict(mutable=True)
                saved_state = saved.get("state", {})
                for k, v in saved_state.items():
                    if isinstance(v, list):
                        qd.setlist(k, v)
                    else:
                        qd[k] = v

                # Auto-select new customer if just created
                if new_customer_id:
                    qd["customer"] = new_customer_id

                form = InvoiceForm(qd, organization=org)
                formset = FormSet(qd, prefix="lines")

                # Auto-select new product in the right line or first empty line
                if new_product_id:
                    li = None
                    if line_index != "":
                        try:
                            li = int(line_index)
                        except (ValueError, TypeError):
                            pass
                    else:
                        # Find first empty line
                        total_forms = int(qd.get("lines-TOTAL_FORMS", 0))
                        for i in range(total_forms):
                            if not qd.get(f"lines-{i}-product") and qd.get(f"lines-{i}-DELETE") != "on":
                                li = i
                                break
                    
                    if li is not None:
                        key = f"lines-{li}-product"
                        qd[key] = new_product_id
                        form = InvoiceForm(qd, organization=org)
                        formset = FormSet(qd, prefix="lines")

                return render(request, self.template_name, self._get_context(form, formset, org, state_token=""))

        form = InvoiceForm(organization=org, initial={"invoice_date": datetime.date.today()})
        formset = FormSet(prefix="lines")
        return render(request, self.template_name, self._get_context(form, formset, org))

    def post(self, request):
        org = self.get_organization()
        form = InvoiceForm(request.POST, organization=org)
        FormSet = make_invoice_line_formset(org, extra=0)
        formset = FormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            # --- Backend validation: customer required ---
            prospective_invoice = form.save(commit=False)
            if not prospective_invoice.customer:
                form.add_error("customer", "A customer is required to create an invoice.")
                return render(request, self.template_name, self._get_context(form, formset, org))

            # --- Backend validation: at least one valid line required ---
            active_line_forms = [
                f for f in formset.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE", False)
                and f.cleaned_data.get("product")
            ]
            if not active_line_forms:
                messages.error(request, "At least one line item with a product is required.")
                return render(request, self.template_name, self._get_context(form, formset, org))

            invoice = prospective_invoice
            invoice.organization = org
            invoice.status = InvoiceStatus.DRAFT
            # Snapshot placeholders — will be finalized on Issue
            invoice.customer_name_snapshot = invoice.customer.name
            invoice.customer_gstin_snapshot = invoice.customer.gstin or ""
            invoice.customer_billing_address_snapshot = invoice.customer.full_billing_address
            invoice.customer_state_code_snapshot = invoice.customer.billing_state_code
            # Derive Place of Supply from shipping address (canonical state code).
            # shipping_state now holds a 2-digit code submitted from the state dropdown.
            try:
                invoice.place_of_supply = resolve_place_of_supply(
                    shipping_same_as_billing=invoice.shipping_same_as_billing,
                    shipping_state_code=invoice.shipping_state,
                    customer=invoice.customer,
                )
            except ValidationError as e:
                messages.error(request, str(e))
                return render(request, self.template_name, self._get_context(form, formset, org))
            invoice.save()

            formset.instance = invoice
            lines = formset.save(commit=False)
            position = 1
            for line in lines:
                line.invoice = invoice
                line.position = position
                position += 1
                # Populate snapshot fields from product master before first save.
                # finalize_invoice() will re-freeze authoritative snapshots at Issue time.
                if line.product:
                    populate_line_snapshot(line)
                line.save()
            for deleted in formset.deleted_objects:
                deleted.delete()

            # Calculate and store authoritative totals for the draft invoice
            try:
                from apps.billing.services.calculation_engine import calculate_invoice
                calculate_invoice(invoice, list(invoice.lines.all()))
                invoice.save()
            except Exception as e:
                import logging
                logging.error(f"Failed to calculate totals for draft invoice: {e}")

            # Trigger persistent notification for draft invoice creation
            try:
                from apps.common.models import NotificationCategory  # noqa: PLC0415
                from apps.common.services.notification_service import NotificationService  # noqa: PLC0415
                NotificationService.create(
                    user=request.user,
                    organization=org,
                    category=NotificationCategory.BILLING,
                    event_type="invoice_created",
                    title="Draft Invoice Created",
                    message=f"Draft invoice {invoice.invoice_number or 'Draft'} created for {invoice.customer_name_snapshot or 'customer'}.",
                    entity_type="invoice",
                    entity_id=str(invoice.uuid),
                    request=request,
                )
            except Exception as e:
                import logging
                logging.error(f"Failed to create invoice_created notification: {e}")

            messages.success(request, "Draft invoice created successfully.")
            return redirect("billing:detail", uuid=invoice.uuid)

        return render(request, self.template_name, self._get_context(form, formset, org))


# ---------------------------------------------------------------------------
# Invoice Detail
# ---------------------------------------------------------------------------

class InvoiceDetailView(InvoiceOrganizationMixin, PageTitleMixin, View):
    template_name = "billing/detail.html"

    def get_page_title(self) -> str:
        return "Invoice Detail — Advance Billing"

    def get(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        lines = invoice.lines.all().select_related("product")
        context = {
            "invoice": invoice,
            "lines": lines,
            "page_title": f"Invoice {invoice.invoice_number or 'Draft'} — Advance Billing",
            "InvoiceStatus": InvoiceStatus,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Invoice Edit (Draft only)
# ---------------------------------------------------------------------------

class InvoiceEditView(InvoiceOrganizationMixin, PageTitleMixin, View):
    template_name = "billing/form.html"

    def _get_page_title(self, invoice):
        return f"Edit Invoice — Advance Billing"

    def _get_context(self, form, formset, invoice):
        from apps.organization.services import LocalGSTValidator
        return {
            "form": form,
            "formset": formset,
            "invoice": invoice,
            "page_title": self._get_page_title(invoice),
            "is_create": False,
            "InvoiceStatus": InvoiceStatus,
            "state_code_names": LocalGSTValidator.STATE_CODES,
            "org_default_note_json": "null",
        }

    def get(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        if invoice.status != InvoiceStatus.DRAFT:
            messages.error(request, "Only draft invoices can be edited.")
            return redirect("billing:detail", uuid=invoice.uuid)

        org = self.get_organization()
        form = InvoiceForm(instance=invoice, organization=org)
        FormSet = make_invoice_line_formset(org, extra=0)
        formset = FormSet(instance=invoice, prefix="lines")
        return render(request, self.template_name, self._get_context(form, formset, invoice))

    def post(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        if invoice.status != InvoiceStatus.DRAFT:
            messages.error(request, "Only draft invoices can be edited.")
            return redirect("billing:detail", uuid=invoice.uuid)

        org = self.get_organization()
        form = InvoiceForm(request.POST, instance=invoice, organization=org)
        FormSet = make_invoice_line_formset(org, extra=0)
        formset = FormSet(request.POST, instance=invoice, prefix="lines")

        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            # Update customer snapshot fields for display convenience (non-final)
            if invoice.customer:
                invoice.customer_name_snapshot = invoice.customer.name
                invoice.customer_gstin_snapshot = invoice.customer.gstin or ""
                invoice.customer_billing_address_snapshot = invoice.customer.full_billing_address
                invoice.customer_state_code_snapshot = invoice.customer.billing_state_code
            # Re-derive Place of Supply from shipping address on each edit
            if invoice.customer:
                try:
                    invoice.place_of_supply = resolve_place_of_supply(
                        shipping_same_as_billing=invoice.shipping_same_as_billing,
                        shipping_state_code=invoice.shipping_state,
                        customer=invoice.customer,
                    )
                except ValidationError as e:
                    messages.error(request, str(e))
                    return render(request, self.template_name, self._get_context(form, formset, invoice))
            invoice.save()

            formset.instance = invoice
            lines = formset.save(commit=False)

            # Re-assign positions to all active lines
            existing_lines = list(invoice.lines.all().order_by("position"))
            position_counter = max((l.position for l in existing_lines), default=0)

            for line in lines:
                if not line.position:
                    position_counter += 1
                    line.position = position_counter
                line.invoice = invoice
                # Populate snapshots for new lines (existing lines already have them)
                if not line.pk and line.product:
                    populate_line_snapshot(line)
                line.save()
            for deleted in formset.deleted_objects:
                deleted.delete()

            # Calculate and store authoritative totals for the draft invoice
            try:
                from apps.billing.services.calculation_engine import calculate_invoice
                calculate_invoice(invoice, list(invoice.lines.all()))
                invoice.save()
            except Exception as e:
                import logging
                logging.error(f"Failed to calculate totals for draft invoice edit: {e}")

            messages.success(request, "Draft invoice updated successfully.")
            return redirect("billing:detail", uuid=invoice.uuid)

        return render(request, self.template_name, self._get_context(form, formset, invoice))


# ---------------------------------------------------------------------------
# Invoice Delete (Draft only)
# ---------------------------------------------------------------------------

class InvoiceDeleteView(InvoiceOrganizationMixin, PageTitleMixin, View):
    template_name = "billing/confirm_delete.html"
    page_title = "Delete Invoice — Advance Billing"

    def get(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        if invoice.status != InvoiceStatus.DRAFT:
            messages.error(request, "Only draft invoices can be deleted.")
            return redirect("billing:detail", uuid=invoice.uuid)
        return render(request, self.template_name, {
            "invoice": invoice,
            "page_title": self.page_title,
            "InvoiceStatus": InvoiceStatus,
        })

    def post(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        try:
            delete_invoice(invoice)
            messages.success(request, "Draft invoice deleted successfully.")
            return redirect("billing:index")
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect("billing:detail", uuid=invoice.uuid)


# ---------------------------------------------------------------------------
# Invoice Issue (Phase 08 finalization pipeline)
# ---------------------------------------------------------------------------

class InvoiceIssueView(InvoiceOrganizationMixin, View):
    """
    POST-only. Calls the Phase 08 finalize_invoice() pipeline:
        Validate → Snapshot → Calculate → Persist → Phase 03 issue_invoice()
    Must NOT bypass finalize_invoice() with a direct lifecycle call.
    """

    def post(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        try:
            issued = finalize_invoice(invoice)
            try:
                from apps.common.models import NotificationCategory  # noqa: PLC0415
                from apps.common.services.notification_service import NotificationService  # noqa: PLC0415
                NotificationService.create(
                    user=request.user,
                    organization=issued.organization,
                    category=NotificationCategory.BILLING,
                    event_type="invoice_issued",
                    title="Invoice Issued",
                    message=f"Invoice {issued.invoice_number} issued successfully.",
                    entity_type="invoice",
                    entity_id=str(issued.uuid),
                    request=request,
                )
            except Exception as ne:
                import logging
                logging.error(f"Failed to trigger invoice_issued notification: {ne}")

            messages.success(
                request,
                f"Invoice {issued.invoice_number} issued successfully."
            )
            return redirect("billing:detail", uuid=issued.uuid)
        except ValidationError as e:
            # Show all validation errors clearly
            error_list = e.messages if hasattr(e, "messages") else [str(e)]
            for err in error_list:
                messages.error(request, err)
            return redirect("billing:detail", uuid=invoice.uuid)
        except Exception as e:
            messages.error(request, f"Failed to issue invoice: {e}")
            return redirect("billing:detail", uuid=invoice.uuid)


# ---------------------------------------------------------------------------
# Invoice Cancel (Issued only)
# ---------------------------------------------------------------------------

class InvoiceCancelView(InvoiceOrganizationMixin, View):
    """
    POST-only. Calls the Phase 03 cancel_invoice() service.
    Cancelled invoices remain for historical retention.
    """

    def post(self, request, uuid):
        invoice = self.get_org_invoice(uuid)
        try:
            cancel_invoice(invoice)
            try:
                from apps.common.models import NotificationCategory  # noqa: PLC0415
                from apps.common.services.notification_service import NotificationService  # noqa: PLC0415
                NotificationService.create(
                    user=request.user,
                    organization=invoice.organization,
                    category=NotificationCategory.BILLING,
                    event_type="invoice_cancelled",
                    title="Invoice Cancelled",
                    message=f"Invoice {invoice.invoice_number} has been cancelled.",
                    entity_type="invoice",
                    entity_id=str(invoice.uuid),
                    request=request,
                )
            except Exception as ne:
                import logging
                logging.error(f"Failed to trigger invoice_cancelled notification: {ne}")

            messages.success(request, f"Invoice {invoice.invoice_number} cancelled.")
            return redirect("billing:detail", uuid=invoice.uuid)
        except ValidationError as e:
            error_list = e.messages if hasattr(e, "messages") else [str(e)]
            for err in error_list:
                messages.error(request, err)
            return redirect("billing:detail", uuid=invoice.uuid)


# ---------------------------------------------------------------------------
# Invoice Mail (On-demand email delivery to Organization Owner)
# ---------------------------------------------------------------------------

@method_decorator(ratelimit(key="user_or_ip", rate="10/m", block=False), name="post")
class InvoiceMailView(InvoiceOrganizationMixin, View):
    """
    POST-only. On-demand email delivery of invoice copy to the Organization Owner.
    Validates organization scoping, owner email, renders PDF, and emails owner.
    """

    def post(self, request, uuid):
        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.post,
                key="user_or_ip",
                rate="10/m",
                custom_message="Rate limit exceeded. Please wait before making more email requests.",
            )

        invoice = self.get_org_invoice(uuid)
        
        from apps.billing.services.invoice_email_service import InvoiceEmailService, EmailTrigger
        from django.urls import reverse

        try:
            success, msg = InvoiceEmailService.send_invoice_email(
                invoice,
                trigger=EmailTrigger.MANUAL,
                user=request.user
            )
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Error during manual invoice mailing to owner: %s", str(e), exc_info=True)
            messages.error(request, "Failed to send invoice email to the organization owner. Please try again.")

        return redirect(request.META.get("HTTP_REFERER") or reverse("billing:detail", kwargs={"uuid": invoice.uuid}))


# ---------------------------------------------------------------------------
# Invoice Preview (Phase 10 entry point stub)
# ---------------------------------------------------------------------------

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from apps.billing.services.pdf_resource_guard import PDFCapacityExceededError

@method_decorator(ratelimit(key="user_or_ip", rate="15/m", block=False), name="get")
class InvoicePreviewView(InvoiceOrganizationMixin, View):
    """
    Entry point for Phase 10 PDF/letterhead integration.
    Generates and returns the PDF document inline or as an attachment.
    """

    def get(self, request, uuid):
        from django.http import HttpResponse, Http404
        from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts
        from apps.invoices.services.bill_serializer import serialize_bill_for_render
        from apps.invoices.services.invoice_preview_service import InvoicePreviewService
        from apps.common.services.layout_engine import PrintableFrameBuilder

        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.get,
                key="user_or_ip",
                rate="15/m",
                custom_message="Rate limit exceeded. Please wait before making more PDF requests.",
            )

        invoice = self.get_org_invoice(uuid)
        
        try:
            pdf_bytes = InvoicePreviewService.render_invoice_to_pdf(
                invoice=invoice,
                user=request.user
            )
        except PDFCapacityExceededError:
            return HttpResponse(
                "PDF rendering capacity is temporarily busy. Please try again in a moment.",
                status=503,
                content_type="text/plain",
            )
        
        if not pdf_bytes:
            raise Http404("Could not generate PDF.")
            
        # 7. Construct HTTP response
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"Invoice_{invoice.invoice_number or 'Draft'}.pdf"
        
        if request.GET.get('download') == '1':
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
        else:
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            
        return response


# ---------------------------------------------------------------------------
# Draft Calculation Preview (AJAX)
# Returns display-only calculated totals from the Phase 08 engine.
# These are NOT persisted. The backend remains authoritative on Issue.
# ---------------------------------------------------------------------------


class InvoicePreviewFormCalculationView(InvoiceOrganizationMixin, View):
    """
    POST JSON endpoint: receives full form state, builds in-memory objects, 
    runs the Phase 08 calculation engine, and returns display-only totals.
    """
    def post(self, request):
        org = self.get_organization()
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            return JsonResponse({"error": "Invalid request"}, status=400)
            
        form_state = data.get("state", {})
        
        # Build in-memory invoice
        invoice = Invoice(organization=org)
        
        # Resolve customer if provided
        customer_id = form_state.get("customer")
        if customer_id:
            try:
                invoice.customer = Customer.objects.get(id=customer_id, organization=org)
                invoice.customer_name_snapshot = invoice.customer.name
                invoice.customer_gstin_snapshot = invoice.customer.gstin or ""
                invoice.customer_billing_address_snapshot = invoice.customer.full_billing_address
                invoice.customer_state_code_snapshot = invoice.customer.billing_state_code
            except Customer.DoesNotExist:
                pass
                
        invoice.shipping_same_as_billing = form_state.get("shipping_same_as_billing") == "on"
        invoice.shipping_state = form_state.get("shipping_state", "")
        
        # Try to resolve Place of Supply
        try:
            from apps.billing.services.lifecycle import resolve_place_of_supply
            if invoice.customer:
                invoice.place_of_supply = resolve_place_of_supply(
                    shipping_same_as_billing=invoice.shipping_same_as_billing,
                    shipping_state_code=invoice.shipping_state,
                    customer=invoice.customer
                )
        except Exception as e:
            print("Exception resolving POS:", e)
            pass
            
        # Fallback for place_of_supply if frontend provides it explicitly
        if not invoice.place_of_supply and form_state.get("place_of_supply"):
            invoice.place_of_supply = form_state.get("place_of_supply")
            
        if not invoice.place_of_supply:
            return _zero_totals_response()
            
        # Build in-memory lines
        lines = []
        try:
            total_forms = int(form_state.get("lines-TOTAL_FORMS", 0))
        except ValueError:
            total_forms = 0
            
        from decimal import Decimal
        position = 1
        for i in range(total_forms):
            # Skip deleted rows
            if form_state.get(f"lines-{i}-DELETE") == "on":
                continue
                
            product_id = form_state.get(f"lines-{i}-product")
            if not product_id:
                continue
                
            try:
                product = Product.objects.get(id=product_id, organization=org)
            except Product.DoesNotExist:
                continue
                
            line = InvoiceLine(
                invoice=invoice,
                product=product,
                position=position,
                description=form_state.get(f"lines-{i}-description", ""),
                discount_type=form_state.get(f"lines-{i}-discount_type", "none")
            )
            
            try:
                line.quantity = Decimal(str(form_state.get(f"lines-{i}-quantity", 1)))
            except Exception:
                line.quantity = Decimal("1.000")
                
            try:
                line.unit_price = Decimal(str(form_state.get(f"lines-{i}-unit_price", 0)))
            except Exception:
                line.unit_price = Decimal("0.00")
                
            if line.discount_type != "none":
                try:
                    line.discount_value = Decimal(str(form_state.get(f"lines-{i}-discount_value", 0)))
                except Exception:
                    line.discount_value = Decimal("0.00")
            else:
                line.discount_value = Decimal("0.00")
                
            # Snapshot
            from apps.billing.services.lifecycle import populate_line_snapshot
            populate_line_snapshot(line)
            
            lines.append(line)
            position += 1
            
        if not lines:
            return _zero_totals_response()
            
        try:
            from apps.billing.services.calculation_engine import calculate_invoice
            calculate_invoice(invoice, lines)
        except Exception as e:
            import logging
            logging.error(f"Calculation failed: {e}", exc_info=True)
            return JsonResponse({"error": "Calculation failed", "details": str(e)}, status=400)
            
        return JsonResponse({
            "subtotal": str(invoice.subtotal),
            "discount_total": str(invoice.discount_total),
            "taxable_amount": str(invoice.taxable_amount),
            "cgst_total": str(invoice.cgst_total),
            "sgst_total": str(invoice.sgst_total),
            "igst_total": str(invoice.igst_total),
            "cess_total": str(invoice.cess_total),
            "round_off": str(invoice.round_off),
            "grand_total": str(invoice.grand_total),
            "place_of_supply": invoice.place_of_supply,
        })

class InvoicePreviewCalculationView(InvoiceOrganizationMixin, View):
    """
    POST JSON endpoint: receives form data, runs the Phase 08 calculation engine
    in-memory (no persistence), and returns display-only totals for the Draft form.

    This gives users immediate feedback on subtotal, GST, and grand total
    WITHOUT making those values authoritative — finalize_invoice() on Issue is authoritative.
    """

    def post(self, request, uuid=None):
        org = self.get_organization()
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            return JsonResponse({"error": "Invalid request"}, status=400)

        # We need an invoice to run the engine. If uuid given, use it.
        # Otherwise return zeros (new invoice not yet saved).
        if uuid:
            try:
                invoice = Invoice.objects.get(uuid=uuid, organization=org)
            except Invoice.DoesNotExist:
                return JsonResponse({"error": "Not found"}, status=404)

            if invoice.status != InvoiceStatus.DRAFT:
                return JsonResponse({"error": "Not a draft invoice"}, status=400)

            # Read current lines from DB (not from POST — let the engine use saved state)
            lines = list(invoice.lines.all())
            if not lines:
                return _zero_totals_response()

            place_of_supply = data.get("place_of_supply") or invoice.place_of_supply
            if not place_of_supply:
                return _zero_totals_response()

            # Temporarily set POS for in-memory calculation
            invoice.place_of_supply = place_of_supply

            try:
                # Prepare snapshots in memory without DB save
                from apps.billing.services.lifecycle import prepare_invoice_snapshots
                prepared_lines = prepare_invoice_snapshots(invoice, lines)
            except ValidationError:
                return _zero_totals_response()

            try:
                # Calculate in memory — do NOT call finalize_invoice()
                from apps.billing.services.calculation_engine import calculate_invoice
                calculate_invoice(invoice, prepared_lines)
            except Exception:
                return _zero_totals_response()

            return JsonResponse({
                "subtotal": str(invoice.subtotal),
                "discount_total": str(invoice.discount_total),
                "taxable_amount": str(invoice.taxable_amount),
                "cgst_total": str(invoice.cgst_total),
                "sgst_total": str(invoice.sgst_total),
                "igst_total": str(invoice.igst_total),
                "cess_total": str(invoice.cess_total),
                "round_off": str(invoice.round_off),
                "grand_total": str(invoice.grand_total),
            })

        return _zero_totals_response()


def _zero_totals_response():
    zero = "0.00"
    return JsonResponse({
        "subtotal": zero, "discount_total": zero, "taxable_amount": zero,
        "cgst_total": zero, "sgst_total": zero, "igst_total": zero,
        "cess_total": zero, "round_off": zero, "grand_total": zero,
    })


# ---------------------------------------------------------------------------
# Customer Search API (organization-scoped)
# ---------------------------------------------------------------------------

class CustomerSearchAPIView(InvoiceOrganizationMixin, View):
    """
    GET /invoices/api/customers/?q=...
    Returns organization-scoped customer list as JSON for customer selection UI.
    """

    def get(self, request):
        org = self.get_organization()
        q = request.GET.get("q", "").strip()
        qs = Customer.objects.filter(organization=org)
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=q) | Q(gstin__icontains=q))
        qs = qs[:20]
        data = [
            {
                "id": str(c.id),
                "name": c.name,
                "gstin": c.gstin or "",
                "billing_state_code": c.billing_state_code or "",
                "billing_state": getattr(c, "billing_state", ""),
                "billing_city": getattr(c, "billing_city", ""),
                "billing_address_line_1": getattr(c, "billing_address_line_1", ""),
                "billing_pin_code": getattr(c, "billing_pin_code", ""),
                "full_billing_address": c.full_billing_address if hasattr(c, "full_billing_address") else "",
            }
            for c in qs
        ]
        return JsonResponse({"results": data})


class CustomerDetailAPIView(InvoiceOrganizationMixin, View):
    """
    GET /invoices/api/customers/<pk>/
    Returns full customer detail for populating Bill To panel.
    """

    def get(self, request, pk):
        org = self.get_organization()
        try:
            c = Customer.objects.get(id=pk, organization=org)
        except Customer.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse({
            "id": str(c.id),
            "name": c.name,
            "gstin": c.gstin or "",
            "billing_state_code": c.billing_state_code or "",
            "billing_state": getattr(c, "billing_state", ""),
            "billing_city": getattr(c, "billing_city", ""),
            "billing_address_line_1": getattr(c, "billing_address_line_1", ""),
            "billing_pin_code": getattr(c, "billing_pin_code", ""),
            "full_billing_address": c.full_billing_address if hasattr(c, "full_billing_address") else "",
        })


# ---------------------------------------------------------------------------
# Product Search API (organization-scoped)
# ---------------------------------------------------------------------------

class ProductSearchAPIView(InvoiceOrganizationMixin, View):
    """
    GET /invoices/api/products/?q=...
    Returns organization-scoped product list as JSON for product selection in line items.
    """

    def get(self, request):
        org = self.get_organization()
        q = request.GET.get("q", "").strip()
        qs = Product.objects.filter(organization=org)
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=q) | Q(hsn_code__icontains=q))
        qs = qs[:20]
        data = [
            {
                "id": str(p.id),
                "name": p.name,
                "description": getattr(p, "description", "") or "",
                "unit_price": str(p.unit_price),
                "gst_rate": str(p.gst_rate),
                "taxability_type": p.taxability_type,
                "price_basis": p.price_basis,
                "uqc": getattr(p, "uqc", ""),
                "hsn_code": getattr(p, "hsn_code", "") or getattr(p, "sac_code", "") or "",
            }
            for p in qs
        ]
        return JsonResponse({"results": data})


class ProductDetailAPIView(InvoiceOrganizationMixin, View):
    """
    GET /invoices/api/products/<id>/
    Returns product details as JSON.
    """
    def get(self, request, pk):
        org = self.get_organization()
        product = get_object_or_404(Product, pk=pk, organization=org)
        return JsonResponse({
            "id": str(product.id),
            "name": product.name,
            "description": getattr(product, "description", "") or "",
            "unit_price": str(product.unit_price),
            "gst_rate": str(product.gst_rate),
            "taxability_type": product.taxability_type,
            "price_basis": product.price_basis,
            "uqc": getattr(product, "uqc", ""),
            "hsn_code": getattr(product, "hsn_code", "") or getattr(product, "sac_code", "") or "",
        })


# ---------------------------------------------------------------------------
# Invoice Session State Stash (for Customer + / Product + return flow)
# ---------------------------------------------------------------------------

class InvoiceSessionStashView(InvoiceOrganizationMixin, View):
    """
    POST JSON endpoint: stores invoice form state under a unique token in the
    user's session so that after creating a customer/product and returning to
    the invoice, all previously entered data can be restored.

    Uses a dict keyed by token, not a single key, so multiple tabs work safely.

    Request body: { "token": "<unique>", "state": { form fields... }, "line_index": <int|null> }
    Response:     { "ok": true, "token": "<token>" }

    Session structure:
        request.session["invoice_create_states"] = {
            "<token>": {
                "state": {...},        # form field values
                "line_index": <int>,   # which line launched the product creator
            },
            ...
        }
    """

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            return JsonResponse({"error": "Invalid request"}, status=400)

        token = body.get("token", "").strip()
        state = body.get("state", {})
        line_index = body.get("line_index")

        if not token or not isinstance(state, dict):
            return JsonResponse({"error": "Missing token or state"}, status=400)

        stash = request.session.get("invoice_create_states", {})

        # Evict oldest entries if stash grows too large (prevent session bloat)
        MAX_STASH = 50
        if len(stash) >= MAX_STASH:
            oldest_key = next(iter(stash))
            stash.pop(oldest_key)

        stash[token] = {"state": state, "line_index": line_index}
        request.session["invoice_create_states"] = stash
        request.session.modified = True

        return JsonResponse({"ok": True, "token": token})

