# Product V1 Policy

> **Guiding Principle**: The Product master stores what the item *is*, how it is *priced*, and its default *tax characteristics*. The Invoice Engine determines the actual tax treatment for each transaction.

---

## V1 Scope — What is Supported

| Feature | Notes |
|---|---|
| **Goods / Service** | Controlled by `product_type` field |
| **HSN Code** | Required for Goods. 2–8 numeric digits (CBIC HSN) |
| **SAC Code** | Required for Services. 4–6 numeric digits (CBIC SAC) |
| **Taxability Type** | Taxable / Exempt / Nil-rated / Non-GST — each has distinct legal meaning |
| **GST Rate** | From centralized `gst_config.GST_RATE_CHOICES` — configurable, never scattered literals |
| **Cess** | Conditional: Percentage or Fixed Amount per unit |
| **Reverse Charge (RCM)** | Product-level default flag |
| **Unit Price** | `DecimalField` — never floating point |
| **Price Basis** | Inclusive of GST / Exclusive of GST |
| **UQC / Unit** | Controlled list from `gst_config.UQC_CHOICES` (CBIC official codes) |
| **Invoice Snapshot** | `as_invoice_snapshot()` captures all billing attributes at creation time |
| **Organization scope** | Every product belongs to an Organization; all queries are filtered |
| **UUID URLs** | Stable public identifier; integer PK not exposed in URLs |

---

## V1 Intentional Exclusions

| Feature | Reason for Exclusion |
|---|---|
| **SKU** | Not in approved V1 scope |
| **Discount** | Belongs to invoice/invoice-line layer; products can be sold at different discounts |
| **MRP** | Legal-metrology concern, outside V1 scope |
| **Export / SEZ / LUT** | Transaction/customer-context concerns, not product attributes |
| **Composition scheme** | Seller-entity concern, not a product attribute |
| **Batch Number** | Inventory / regulatory — future sector-specific feature |
| **Expiry Date** | Inventory / regulatory — future sector-specific feature |
| **Manufacturing Date** | Inventory / regulatory — future sector-specific feature |
| **Country of Origin** | Export/regulatory — future feature |
| **Inventory / Stock tracking** | Separate subsystem, explicitly out of scope |
| **Warehouse management** | Separate subsystem, explicitly out of scope |
| **External GST/HSN APIs** | No external verification in V1 |
| **Active / Inactive status** | Products are permanent master records in V1 |
| **Product variants** | Not in approved V1 scope |
| **Customer-specific pricing** | Invoice-layer concern |

---

## Tax Architecture Boundary

```
Product
    ↓
GST Rate         ← stored as product characteristic
Taxability       ← Taxable / Exempt / Nil-rated / Non-GST
Cess             ← conditional per-product cess
RCM              ← product-level default flag
    ↓
Invoice / Tax Engine
    ↓
Supplier Location
+ Place of Supply
+ Transaction Context (intra-State vs inter-State)
    ↓
CGST + SGST/UTGST
        OR
IGST
```

**The Product module must NOT:**
- Store `cgst_rate`, `sgst_rate`, `igst_rate` as permanent fields
- Calculate CGST/SGST/IGST
- Decide whether a supply is intra-State or inter-State

The IGST Act and CGST Act distinguish intra-State and inter-State supplies based on the **supplier's location** and the **place of supply** — this is a transaction-level determination, not a product characteristic.

---

## GST Rate Configuration

GST rates are managed centrally in `apps/products/gst_config.py`:

```python
# apps/products/gst_config.py
GST_RATE_CHOICES = [
    ("0.00",  "0%"),
    ("0.25",  "0.25%"),
    ...
    ("40.00", "40%"),  # Added to IRIS IRP Tax Rate Master, September 2025
]
```

**To add a new rate:** edit `GST_RATE_CHOICES` in `gst_config.py`. No template or view changes are needed.

---

## Invoice Snapshot Contract

When a product is selected during Invoice Creation, call `product.as_invoice_snapshot()` to copy the current state into the invoice line:

```python
snapshot = product.as_invoice_snapshot()
# → {
#     "product_name": "...",
#     "gst_rate": "18.00",
#     "unit_price": "1000.00",
#     "uqc": "KGS",
#     ...
# }

# Store snapshot in InvoiceLine:
invoice_line.product_snapshot = snapshot  # JSONField or equivalent
```

**Why snapshots?**

The Product is the *current master*. Invoices are *historical documents*. Editing the product's GST rate or price after an invoice is created must not alter the already-issued invoice. The snapshot captures all billing attributes at the moment of invoice creation.

Example:

```
Product today:         GST = 18%
Invoice created:       GST snapshot = 18%   ← fixed in invoice line
Product edited:        GST = 28%
Old invoice:           still shows 18%      ← unaffected
```

---

## Multi-Tenancy

Every product belongs to one Organization via `ForeignKey(Organization)`.

- All queries use `Product.objects.filter(organization=request.user.organization)`
- Organization is never accepted from URL parameters or POST data
- Organization is derived exclusively from `request.user.organization`

---

## Delete Safety

A product referenced by historical invoice lines must not be deleted in a way that breaks those records.

When `InvoiceLine` model is introduced, set:

```python
product = models.ForeignKey(Product, on_delete=models.PROTECT)
```

`ProductDeleteView` already checks `product.invoice_lines.exists()` before allowing deletion.

---

## File Locations

| File | Purpose |
|---|---|
| `apps/products/gst_config.py` | Centralized GST rates + UQC codes |
| `apps/products/models.py` | Product model + `as_invoice_snapshot()` |
| `apps/products/forms.py` | ProductForm with full conditional validation |
| `apps/products/views.py` | All CRUD views, organization-scoped |
| `apps/products/urls.py` | UUID-based routing |
| `apps/products/tests/` | Full test suite |
| `templates/products/` | List, form, detail, confirm_delete templates |
