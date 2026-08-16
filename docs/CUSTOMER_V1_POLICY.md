# Customer Module V1 — Internal Product & Compliance Policy

**Document Status**: Approved Production Policy  
**Module Version**: V1.0  
**Application**: Advance Billing SaaS  

---

## 1. Executive Summary & Purpose

The **Customer Creation Module V1** captures the minimum reliable customer master data required for Advance Billing's current invoice workflow. It maintains a clean, GST-aware, organization-scoped customer record while keeping the customer module decoupled from transaction-specific tax and shipping decisions.

> **Guiding Principle**:  
> *Capture reliable customer facts once, keep the customer record simple, and let the invoice layer handle transaction-specific billing, shipping, and tax decisions.*

---

## 2. Core V1 Data Specifications

### 2.1 Customer Types
- **`Business`**: Companies, firms, corporations, partnerships, or organizations.
- **`Individual`**: Individual buyers, professionals, or retail consumers.

### 2.2 GST Registration Statuses
- **`GST Registered`**:
  - Customer holds a 15-character Indian GSTIN.
  - Required Field Label: **Legal Registered Name** (per Rule 46 invoice requirements).
  - Required Field: **GSTIN** (Must pass local 15-character format, state code, and Modulo-36 checksum validation).
- **`GST Unregistered`**:
  - Unregistered business or individual consumer.
  - Required Field Label: **Customer Name**.
  - GSTIN field is omitted/cleared.

### 2.3 Local GSTIN Format Validation
- **Local Validation Only**: Validation checks string length (15 characters), character regex (`^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$`), valid state code (01–38/97), and Modulo-36 checksum calculation.
- **No External GST APIs**: System MUST explicitly state `"Valid GSTIN format"` or `"Invalid GSTIN format"`. System MUST NEVER claim `"Government Verified"`, `"GSTIN Verified"`, or `"GST Portal Verified"` without real external API verification.

### 2.4 Structured Billing Address
- **Address Line 1**: Required street address or building details.
- **Address Line 2**: Optional apartment or landmark.
- **City**: Required city or town.
- **State**: Required state name (derived centrally from state selection or GSTIN prefix).
- **State Code**: Required 2-digit Indian GST state code (auto-derived and locked to State).
- **PIN Code**: Required 6 numeric digits for India.
- **Country**: Default `"India"`.

---

## 3. Multi-Tenancy & Security Rules

1. **Organization Scoping**:
   - Every `Customer` record belongs strictly to one `Organization` (`organization_id`).
   - Cross-organization visibility, editing, or deletion is strictly forbidden.
2. **Duplicate Customer Protection**:
   - For `GST Registered` customers, duplicate GSTINs within the same organization are prevented via database conditional constraint (`UniqueConstraint(fields=["organization", "gstin"], condition=Q(gst_status="registered") & ~Q(gstin=""))`).
   - The same GSTIN MAY exist in different organizations (supporting multi-tenant operations).
3. **Protected Deletion**:
   - If a customer is referenced by existing invoices, hard deletion is blocked to preserve historical billing integrity.

---

## 4. Explicit Exclusions from V1

To prevent scope creep and maintain architectural cleanliness, the following features are **EXCLUDED from Customer V1**:

- **Email & Phone fields on Customer model** (Kept out of V1 customer master)
- **Shipping / Delivery Address** (Collected at Invoice Creation per transaction)
- **Place of Supply State** (Determined during Invoice Creation per transaction)
- **Payment Terms & Credit Days** (Configured at Invoice Creation)
- **Tax Calculation Engine** (CGST/SGST/IGST logic belongs to invoice engine)
- **Special GST Categories**: Composition, SEZ, Export, UIN, Deemed Export, Reverse Charge
- **External GST Portal Verification API**
- **Customer Portal, Ledger, Credit Limits, KYC Documents, Attachments**

---

## 5. Revision & Change Management

Any future extension to the Customer master schema (e.g. V2 shipping addresses or international billing) MUST be reviewed against this policy document before implementation.
