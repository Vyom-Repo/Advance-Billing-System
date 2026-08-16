# Invoice Module V1 — Internal Product & Compliance Policy

**Document Status**: Approved Production Policy  
**Module Version**: V1.0  
**Application**: Advance Billing SaaS  

---

## 1. Executive Summary & Purpose

The **Invoice Module V1** is the authoritative billing, calculation, validation, and historical retention engine for Advance Billing. It produces deterministic, GST-compliant tax invoices, enforces multi-tenant organization isolation, snapshots master record attributes at issuance time to guarantee historical immutability, and integrates directly with the production PDF/Letterhead printing pipeline.

> **Guiding Principle**:  
> *Customer stores who the customer is. Product stores what is being sold and its default tax characteristics. Invoice stores what actually occurred in this transaction. The backend calculation engine is authoritative, preserving immutable historical transactions regardless of post-issuance master data mutations.*

---

## 2. Core V1 Functionality & Architecture

The Invoice architecture follows a strict, layered single-direction flow:

```text
Customer / Product Masters
        ↓
Invoice / InvoiceLine Transaction Inputs
        ↓
Pricing Engine (Gross, Discounts, Net Transaction Value)
        ↓
GST Tax Engine (CGST/SGST vs IGST, Cess, Taxability)
        ↓
Calculation & Validation Engine (Aggregation, Round-Off)
        ↓
Lifecycle / Numbering / Lock (Draft → Issued → Cancelled)
        ↓
Invoice Application Layer (CRUD, Formsets, AJAX Preview)
        ↓
PDF Adapter (ORM → Canonical bill_data serialization)
        ↓
Existing PDF / Letterhead Printing Pipeline (WeasyPrint)
```

---

## 3. Supported V1 Features

### 3.1 Customer & Product Master Integration
- **Customer Integration**: Organization-scoped recipient selection. Bill To address auto-populated from customer master.
- **Product Integration**: Organization-scoped product selection. Default pricing, taxability, GST rate, HSN/SAC, UQC, and Cess characteristics snapshotted onto line items.

### 3.2 Invoice Lines & Itemization
- **Multi-Line Formsets**: Dynamically managed line items via Django `inlineformset_factory` with client-side row insertion/removal.
- **Quantity**: 3 decimal places of precision (`DecimalField(max_digits=10, decimal_places=3)`).
- **Unit Price**: 2 decimal places of precision (`DecimalField(max_digits=12, decimal_places=2)`).

### 3.3 Pricing & Discount Engine
- **Discount Types**: `None`, `Percentage` (`0.00%` to `100.00%`), or `Fixed Amount` (capped at gross line value).
- **Price Bases**: 
  - `Exclusive`: Unit price is pre-tax; GST and Cess are calculated and added to the taxable base.
  - `Inclusive`: Unit price contains GST; backward decomposition extracts the exact taxable base without double-counting tax.
- **Arithmetic Precision**: Standardized to `ROUND_HALF_UP` on all currency values using Python `Decimal`. Floating-point arithmetic is strictly banned.

### 3.4 GST Tax Engine & Routing
- **Taxability Classifications**:
  - `Taxable`: Evaluates GST rate, CGST/SGST/UTGST or IGST routing, and applicable Cess.
  - `Exempt`: 0% tax, excluded from tax calculation.
  - `Nil-rated`: 0% tax rate.
  - `Non-GST`: Out of GST scope (e.g. specified petroleum products, alcohol).
- **Place of Supply (POS) Routing**:
  - `Intra-State` (`Supplier State Code == Place of Supply`): Exactly split 50/50 into CGST and SGST/UTGST.
  - `Inter-State` (`Supplier State Code != Place of Supply`): Entire tax mapped to IGST.
- **Cess Handling**: Percentage-based or fixed-amount-per-unit Cess calculation.
- **Reverse Charge Mechanism (RCM)**: RCM attribute captured at line snapshot for reporting.

### 3.5 Calculation, Aggregation & Round-Off
- **Authoritative Backend**: UI summary panels show preview calculations only; final totals are calculated and persisted by the backend calculation engine during issuance inside an atomic transaction.
- **Invoice Totals**: Subtotal, Discount Total, Taxable Amount, CGST Total, SGST Total, IGST Total, Cess Total, Round-off, and Grand Total.
- **Round-Off**: Quantized to the nearest integer (`ROUND_HALF_UP`), with the exact delta stored in `round_off`.

### 3.6 Lifecycle, Numbering & Immutability
- **Three-Stage Lifecycle**:
  - `Draft`: Fully editable, lines can be added/removed, draft can be deleted. Summary is non-authoritative until issuance.
  - `Issued`: Locked and immutable. Assigned a unique, sequential invoice number. Cannot be edited, deleted, re-issued, or moved back to draft.
  - `Cancelled`: Historically retained document. Cannot be edited, deleted, or re-issued. Retains invoice number and original financial totals.
- **Atomic Auto-Numbering**: Scoped per organization via row-level locking (`select_for_update`) on `InvoicePreference`. Formats include prefix, financial year toggle, and zero-padded sequence numbers.
- **Unique Constraint**: Database `UniqueConstraint` on `(organization, invoice_number)` where `invoice_number != ""`.

### 3.7 Historical Snapshots & Immutability
- **Customer Snapshots**: `customer_name_snapshot`, `customer_gstin_snapshot`, `customer_billing_address_snapshot`, `customer_state_code_snapshot`.
- **Product Snapshots**: `product_name_snapshot`, `product_type_snapshot`, `hsn_sac_snapshot`, `taxability_type_snapshot`, `gst_rate_snapshot`, `cess_applicable_snapshot`, `cess_type_snapshot`, `cess_rate_snapshot`, `reverse_charge_snapshot`, `price_basis_snapshot`, `uqc_snapshot`.
- **Master Record Deletion Safety**: ForeignKey relationships between `Invoice → Customer` and `InvoiceLine → Product` utilize `on_delete=models.SET_NULL`. Deleting a customer or product master record sets the FK to `NULL` but leaves the historical invoice, lines, and snapshots completely intact.

### 3.8 PDF & Company Letterhead Integration
- **Zero Calculation Adapter**: `InvoicePDFAdapter` transforms ORM snapshots into flat dictionaries consumed by the existing `serialize_bill_for_render()`.
- **Document Preferences**: Honors user document settings (`print_on_letterhead`, margin geometry, header/footer toggles, logo visibility).
- **Disposition Support**: Supports inline viewing in the browser and direct file download via `?download=1`.

### 3.9 Multi-Tenant Security & Organization Isolation
- **Tenant Boundary**: Every view enforces `InvoiceOrganizationMixin`, validating user authentication and organization resolution.
- **Query Scoping**: All database operations filter strictly by `organization=current_user_org`. Direct UUID manipulation across tenants returns HTTP 404.
- **Form Scoping**: Customer and product dropdowns and POST handlers reject cross-tenant foreign keys.
- **JSON APIs**: Customer search/detail and product search endpoints are strictly organization-gated.

---

## 4. Explicit V1 Exclusions

The following features are intentionally **OUT OF SCOPE** for Invoice Module V1:

1. **Payment Gateways & Collections**: No online payment capture (Razorpay, Stripe), automated payment links, or automatic settlement reconciliation.
2. **Accounting Ledger & Double-Entry Bookkeeping**: No general ledger, chart of accounts, debit/credit journal vouchers, or trial balance.
3. **Inventory Management**: No stock decrementing, warehouse tracking, batch numbering, serial tracking, or low-stock alerts.
4. **E-Invoicing & E-Way Bill Integration**: No direct NIC / IRP API integrations for IRN generation, QR code signing, or E-Way bills.
5. **Recurring Billing & Subscriptions**: No automatic recurring invoice scheduler or dunning management.
6. **Multi-Currency Conversion**: Invoices are fixed in default INR currency.
7. **Complex Role-Based Access Control (RBAC)**: Multi-tenancy is based on a single organization owner model without granular role/permission hierarchies.
8. **Shipping / Logistics Carrier APIs**: No third-party courier integration or tracking number synchronization.

---

## 5. Summary Compliance Table

| Requirement | Implementation Status | Policy Compliance |
|---|---|---|
| Tenant Scoping | `organization_id` foreign key on all billing tables | 100% Verified |
| GST Tax Routing | Place of Supply vs Supplier State Code | 100% Verified |
| Precision Arithmetic | `Decimal` with `ROUND_HALF_UP` | 100% Verified (0 floats) |
| Historical Snapshots | Full Customer & Line snapshot persistence | 100% Verified |
| Deletion Safety | `SET_NULL` foreign keys | 100% Verified |
| Lifecycle Locking | `Draft` → `Issued` → `Cancelled` | 100% Verified |
| PDF Pipeline | Preserved Phase 01 WeasyPrint pipeline | 100% Verified |
