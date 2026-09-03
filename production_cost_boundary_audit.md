# Production Cost Boundary & OCI Deployment Audit — Advance Billing

**Audit Date**: August 27, 2026  
**Application**: Advance Billing (GST Billing & Invoicing System)  
**Target Environment**: Oracle Cloud Infrastructure (OCI)  
**Audit Scope**: Read-Only Production Cost Boundary, Resource Control & Scaling Audit  
**Audit Verdict**: **NEEDS COST CONTROLS**

---

## 1. Actual Deployment Architecture

| Component | Repository Implementation / Configuration |
| :--- | :--- |
| **Framework Version** | Django `5.1.4` (Python `3.12+`) |
| **WSGI Server** | Gunicorn `23.0.0` |
| **Deployment Discrepancy** | `Procfile`: `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 60`<br>`render.yaml`: `gunicorn core.wsgi:application` *(Defaults to 1 sync worker, 1 thread if deployed via render.yaml)* |
| **Worker Recycling** | **NONE** (`max-requests` and `max-requests-jitter` are omitted) |
| **Process Memory Caps** | **NONE** (No OS-level process memory limits or `--limit-request-line` settings) |
| **Background Processing** | In-process daemon threads (`threading.Thread` in `InvoiceEmailService.send_invoice_email_async`). **No Celery, Redis, RQ, or external queue infrastructure present.** |
| **Scheduled Tasks** | Management commands (`run_weekly_backups`, `cleanup_notifications`). No repository-defined crontab or systemd timers. |
| **Database Engine** | Production: PostgreSQL (`psycopg2-binary 2.9.10`, `dj-database-url 2.3.0`, `conn_max_age=600`, `conn_health_checks=True`). Dev: SQLite (`db.sqlite3`). |
| **Media / Asset Storage** | Production: Cloudinary (`cloudinary 1.42.1`, `django-cloudinary-storage 0.3.0`). Dev: Local file system (`MEDIA_ROOT = BASE_DIR / "media"`). |
| **PDF Generation Engine** | `WeasyPrint 63.0` (Synchronous C-extension rendering via Cairo/Pango/Fontconfig). Also invoked inside background threads when emailing invoices. |
| **Email Delivery** | Brevo via Django SMTP (`django.core.mail.backends.smtp.EmailBackend`). |
| **Logging Configuration** | Django standard logging to `logs/advance_billing.log` and `logs/errors.log` via `RotatingFileHandler` (10 MB max, 5 backups) and Console `StreamHandler`. |
| **OCI Configuration** | *OCI-side configuration could not be verified from the available repository.* |

---

## 2. Resource Boundary Map

| Resource Category | Resource Type | Current Application Boundary | Boundary Status | Max Bound / Cap |
| :--- | :--- | :--- | :--- | :--- |
| **Compute** | CPU Cores | Bounded by Gunicorn worker/thread count | **BOUNDED** | 4 Workers × 2 Threads = 8 Concurrency Slots (Procfile) |
| **Compute** | Worker Processes | Static Gunicorn pool | **BOUNDED** | 4 Workers (Procfile) or 1 Worker (render.yaml) |
| **Compute** | Background Threads | Spawns un-bounded daemon threads on invoice issue | **UNBOUNDED** | **UNBOUNDED** (No thread pool cap or semaphore) |
| **Compute** | Process RAM | No memory limit per worker process | **UNBOUNDED** | **UNBOUNDED** (Accumulates until OS OOM killer) |
| **Database** | Connections | `conn_max_age=600`, `close_old_connections()` in threads | **BOUNDED** | Workers + Active Threads (Theoretical: 8 + N threads) |
| **Database** | Query Execution Time | PostgreSQL statement timeout (Not set in Django) | **UNBOUNDED** | **UNBOUNDED** (Controlled only by Gunicorn 60s timeout) |
| **Database** | QuerySet Load (Exports) | In-memory unpaginated QuerySet fetch | **UNBOUNDED** | **UNBOUNDED** (Loads all org DB records into RAM) |
| **Database** | Storage Footprint | Invoice & line item table growth | **BUSINESS GROWTH** | Bounded by business transaction volume |
| **Database** | Log Table Growth | `OrganizationBackupLog` & `DataManagementAuditLog` | **UNBOUNDED** | **UNBOUNDED** (No retention cleanup task) |
| **Storage** | Uploaded Images | `logo`, `signature`, `letterhead`, `qr_code` | **UNBOUNDED** | **UNBOUNDED** (No max file size or pixel limits) |
| **Storage** | Uploaded Backups | `SettingsExcelImportRestoreView` (.xlsx upload) | **UNBOUNDED** | **UNBOUNDED** (No upload file size cap) |
| **Storage** | Generated PDFs | Rendered to in-memory bytes | **BOUNDED** | Zero disk storage footprint |
| **Storage** | Application Logs | `RotatingFileHandler` (10 MB × 5 backups × 2 files) | **BOUNDED** | Hard cap at **100 MB total** local disk usage |
| **Network** | Outbound Email API | Brevo SMTP dispatch | **UNBOUNDED** | **UNBOUNDED** (No per-user rate or quota caps) |
| **Network** | Outbound Media API | Cloudinary upload API | **UNBOUNDED** | **UNBOUNDED** (No upload rate limits) |
| **App Operations** | PDF Render Concurrency | Synchronous WSGI + Asynchronous threads | **UNBOUNDED** | **UNBOUNDED** (No concurrency semaphore or queue) |
| **App Operations** | Export Concurrency | Full DB fetch into RAM per download request | **UNBOUNDED** | **UNBOUNDED** (No rate limiting on export endpoints) |

---

## 3. Single-User Cost Boundary Analysis

| User Operation | CPU-Intensive Ops / Request | DB Queries / Request | Memory Payload Profile | Max Emails / API Calls | Execution Duration Limit | Rate Limited? | Concurrency Limited? | Input Size Limited? | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Invoice Creation** | Low | ~5–10 DB writes | Small (~50 KB) | 1 Notification creation | < 200 ms | **NO** | **NO** | **NO** (Unbounded lines) | **POTENTIALLY UNBOUNDED** |
| **Invoice Issue** | High (WeasyPrint in thread) | ~10 DB writes + thread DB fetch | Medium (50 MB in background thread) | 1 Brevo SMTP Email | 1–5 sec (Background) | **NO** | **NO** | **NO** | **POTENTIALLY UNBOUNDED** |
| **PDF Preview / Download** | High (Synchronous WeasyPrint) | ~5 DB queries | High (50–200 MB RAM per render) | 0 | 1–10 sec | **NO** | **NO** | **NO** (Unbounded lines) | **POTENTIALLY UNBOUNDED** |
| **AJAX Design Preview** | High (Synchronous WeasyPrint) | ~5 DB queries | High (50–200 MB RAM per render) | 0 | 1–5 sec | **NO** | **NO** | **NO** | **POTENTIALLY UNBOUNDED** |
| **Data Export ZIP** | Medium | Queries entire org database | Very High (Full DB in RAM + ZIP BytesIO) | 0 | 5–30 sec | **NO** | **NO** | **NO** | **POTENTIALLY UNBOUNDED** |
| **Excel Export** | Medium | Queries entire org database | Very High (Full DB in RAM + openpyxl) | 0 | 5–30 sec | **NO** | **NO** | **NO** | **POTENTIALLY UNBOUNDED** |
| **Instant Backup Email** | High (Dual format + Email) | Queries entire org database | Very High (Dual format in RAM < 15MB) | 1 Brevo SMTP Email (Dual attachments) | 5–30 sec | **NO** | **NO** | **NO** | **POTENTIALLY UNBOUNDED** |
| **Image Upload** | Low (Pillow processing) | ~2 DB writes | High (Unrestricted image decompress) | 1 Cloudinary upload | 1–5 sec | **NO** | **NO** | **NO** (No file size cap) | **POTENTIALLY UNBOUNDED** |
| **Password Reset** | Low | ~2 DB queries | Small (< 10 KB) | 1 Brevo SMTP Email | < 500 ms | **NO** | **NO** | **YES** (Email string) | **POTENTIALLY UNBOUNDED** |
| **Login / Auth** | Medium (PBKDF2 hash) | ~2 DB queries | Small (< 10 KB) | 0 | < 200 ms | **NO** | **NO** | **YES** | **POTENTIALLY UNBOUNDED** |
| **Customer / Product Search**| Low | 1 DB query | Small (`[:20]` cap) | 0 | < 50 ms | **NO** | **NO** | **YES** (`[:20]` capped) | **BOUNDED** |
| **Invoice List View** | Low | 2 DB queries | Small (`paginate_by = 25`) | 0 | < 100 ms | **NO** | **NO** | **YES** (Paginated) | **BOUNDED** |

---

## 4. Single-Organization Cost Boundary

```
[Single Organization Scope]
       │
       ├──► Active Business Data (Invoices, Customers, Products, Lines)
       │        └──► Expected Business Growth (Paginated UI views; safe in daily ops)
       │        └──► OPERATIONAL RISK: Export/Backup services fetch 100% of rows into RAM
       │
       ├──► User-Generated Assets (Logos, Signatures, Letterheads)
       │        └──► OPERATIONAL RISK: No file size or dimension caps per upload
       │
       ├──► System Audit Logs (OrganizationBackupLog, DataManagementAuditLog)
       │        └──► UNBOUNDED GROWTH: Accumulates indefinitely with zero retention cleanup
       │
       └──► Notifications (Notification)
                └──► BOUNDED: Enforces inline retention cleanup (Max 300 per user)
```

---

## 5. Concurrent User Cost Boundary

* **Scenario A: 10 users generate PDFs simultaneously**  
  * **Behavior**: 8 requests occupy all available Gunicorn worker threads (Procfile config). 2 requests queue or time out. CPU usage spikes to 100% across all instance cores. RAM usage increases by ~1–2 GB. **REQUIRES LOAD TEST**.
* **Scenario B: 50 users generate PDFs simultaneously**  
  * **Behavior**: Severe worker saturation. 8 active worker threads execute WeasyPrint; 42 requests wait in socket backlog or fail with HTTP 504 Gateway Timeout. High risk of worker process memory exhaustion causing Gunicorn SIGKILL worker restarts. **REQUIRES LOAD TEST**.
* **Scenario C: 100 invoice emails triggered rapidly**  
  * **Behavior**: 100 background daemon threads spawn concurrently within the WSGI process. Each thread attempts WeasyPrint PDF compilation and SMTP connection simultaneously, causing CPU saturation, thread context switching overhead, and potential DB connection pool exhaustion. **REQUIRES LOAD TEST**.
* **Scenario D: 10 users export large datasets simultaneously**  
  * **Behavior**: 10 concurrent requests execute unpaginated QuerySet fetches into RAM. Memory consumption spikes by 10 × Full DB RAM Payload (potentially multiple gigabytes), inducing OS memory pressure and OOM killer invocation. **REQUIRES LOAD TEST**.
* **Scenario E: Multiple organizations run backups simultaneously**  
  * **Behavior**: Database Read IOPS spike significantly. Concurrent openpyxl workbook compilations saturate CPU cores and RAM. **REQUIRES LOAD TEST**.
* **Scenario F: Many users upload large images simultaneously**  
  * **Behavior**: Synchronous Pillow image decoding and Cloudinary API uploads consume memory and network bandwidth. **REQUIRES LOAD TEST**.

---

## 6. Worker / Thread Cost Boundary

| Execution Path | Spawning Mechanism | Max Simultaneous Executions | Concurrency Cap | Queue / Semaphore Cap | Concurrency Risk Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`send_invoice_email_async`** | `threading.Thread(target=worker, daemon=True)` | **UNBOUNDED** | **NONE** | **NONE** | **UNBOUNDED CONCURRENCY — PRODUCTION RISK** |
| **PDF Previews & Downloads** | Synchronous Gunicorn Worker Threads | Bounded by Gunicorn Threads (8) | Procfile Workers (4×2) | Socket Backlog | **BOUNDED BY GUNICORN (DoS Risk)** |
| **Data Exports / Backups** | Synchronous Gunicorn Worker Threads | Bounded by Gunicorn Threads (8) | Procfile Workers (4×2) | Socket Backlog | **BOUNDED BY GUNICORN (RAM Spike Risk)** |
| **`run_weekly_backups`** | Management Command (External CLI) | 1 Process per Cron invocation | **NONE** | **NONE** | **BOUNDED BY CRON FREQUENCY** |

---

## 7. PDF Cost Boundary

* **Authentication Required**: YES for invoice detail PDF; NO for letterhead preview endpoint if session is active.
* **Rate Limiting**: **NONE**.
* **Concurrency Control**: **NONE**.
* **PDF Caching**: **NONE** (Rendered from scratch on every request).
* **Maximum Line Items**: **UNBOUNDED** (No line item ceiling enforced in forms).
* **Maximum Execution Timeout**: Gunicorn worker timeout (60 seconds in Procfile; 30 seconds in render.yaml).
* **Background Thread Execution**: YES (Invoked in daemon thread on invoice issue and manual email).
* **RAM / CPU Bound**: **UNBOUNDED** (Scales with line item count and request frequency).
* **Maximum Simultaneous WeasyPrint Renders**: **UNBOUNDED PDF CONCURRENCY — PRODUCTION RISK** (Synchronous WSGI workers + un-bounded background email threads can execute unlimited WeasyPrint instances concurrently).

---

## 8. Email Cost Boundary

| Email Path | Trigger | Auth Required? | Per-User Limit | Per-Org Limit | Rate Limit | Cooldown | Attachment Size Cap | Risk Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Signup Verification** | User Signup | NO | **NONE** | **NONE** | **NONE** | **NONE** | None | **POTENTIALLY UNBOUNDED** |
| **Resend Verification** | User Resend Click | NO (Session) | **NONE** | **NONE** | **NONE** | **NONE** | None | **POTENTIALLY UNBOUNDED** |
| **Password Reset** | Form Submission | NO | **NONE** | **NONE** | **NONE** | **NONE** | None | **POTENTIALLY UNBOUNDED** |
| **Automatic Invoice Email** | Invoice Issue | YES | **NONE** | **NONE** | **NONE** | **NONE** | In-memory PDF | **POTENTIALLY UNBOUNDED** |
| **Manual Invoice Mail** | User Mail Click | YES | **NONE** | **NONE** | **NONE** | **NONE** | In-memory PDF | **POTENTIALLY UNBOUNDED** |
| **Instant Backup Mail** | Data Management Click | YES (Owner) | **NONE** | 6 days (Bypassed if forced) | **NONE** | **NONE** | 15 MB Hard Cap | **POTENTIALLY UNBOUNDED** |
| **Weekly Backup Cron** | Scheduled Command | CLI | 6-day Idempotency | 6-day Idempotency | N/A | 6 Days | 15 MB Hard Cap | **BOUNDED BY CRON** |

---

## 9. Database Cost Boundary

```
[Query Scaling Behavior]

1. Paginated Web Views (Invoice ListView, Customer Search)
   └── Query: Invoice.objects.filter(organization=org).select_related("customer")
   └── Boundary: Capped by paginate_by = 25 or [:20]
   └── Scaling: O(1) with respect to total database size. (BOUNDED)

2. Export & Backup Pipelines (generate_single_snapshot, ExcelBackupService)
   └── Query: Invoice.objects.filter(organization=org).select_related("customer")
   └── Query: InvoiceLine.objects.filter(invoice__organization=org).select_related("invoice", "product")
   └── Boundary: NONE (Unpaginated full table load into Python memory lists)
   └── Scaling: O(N) linear RAM growth with total organization record count. (UNBOUNDED RAM LOAD)
```

---

## 10. Database Connection Boundary

* **Connection Settings**: `conn_max_age=600`, `conn_health_checks=True`.
* **Worker Connection Pool**: 4 Gunicorn sync workers × 2 threads = 8 persistent database connections.
* **Background Thread Connection Demand**: Each background thread spawned by `send_invoice_email_async` executes `close_old_connections()` and opens a dedicated database connection.
* **Theoretical Maximum Connection Demand Formula**:
  $$\text{Max DB Connections} = (\text{Gunicorn Workers} \times \text{Threads}) + \text{Active Background Threads}$$
  $$\text{Max DB Connections} = 8 + N_{\text{threads}}$$
  If 50 invoices are issued rapidly, connection demand rises to $8 + 50 = 58$ concurrent PostgreSQL connections.

---

## 11. Data Export / Backup Cost Boundary

* **Memory Payload Architecture**: **Full In-Memory Loading** (Loads all database rows into Python dictionary structures before serializing to JSON or compiling openpyxl workbooks).
* **Streaming Implementation**: **NONE** (Does not use HTTP `StreamingHttpResponse` or chunked `QuerySet.iterator()`).
* **Attachment Limits**: 15 MB combined payload size check enforced BEFORE sending email in `backup_service.py:436`. *(Note: Memory is already allocated in RAM before the check occurs).*
* **Frequency Caps**: 6-day idempotency check on scheduled backups; manual exports and forced backups have **no rate or frequency limits**.

---

## 12. File Upload Cost Boundary

| Upload Field | Form / View | Max File Size | Allowed MIME Types | Extension Validation | Decompression Bomb Protection | Risk Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `logo` | `OrganizationUpdateForm` | **UNBOUNDED** | Image Types | **NONE** | **NONE** (`PIL.Image` default) | **UNBOUNDED FILE SIZE — PRODUCTION RISK** |
| `signature` | `OrganizationUpdateForm` | **UNBOUNDED** | Image Types | **NONE** | **NONE** (`PIL.Image` default) | **UNBOUNDED FILE SIZE — PRODUCTION RISK** |
| `letterhead` | `OrganizationUpdateForm` | **UNBOUNDED** | Image Types | **NONE** | **NONE** (`PIL.Image` default) | **UNBOUNDED FILE SIZE — PRODUCTION RISK** |
| `qr_code` | `OrganizationUpdateForm` | **UNBOUNDED** | Image Types | **NONE** | **NONE** (`PIL.Image` default) | **UNBOUNDED FILE SIZE — PRODUCTION RISK** |
| `backup_file` | `SettingsExcelImportRestoreView` | **UNBOUNDED** | `.xlsx` | Check via openpyxl | **NONE** | **UNBOUNDED FILE SIZE — PRODUCTION RISK** |

---

## 13. Storage Cost Boundary

* **Media Storage (Cloudinary)**: Uploaded logos, signatures, letterheads, and QR codes stored in Cloudinary. No per-organization storage quotas enforced.
* **Generated PDFs**: Rendered to in-memory `bytes`; **0 MB** persistent storage footprint.
* **Application Logs**: Bounded to **100 MB total** via `RotatingFileHandler` (2 files × 10 MB × 5 backups).
* **Database Storage**: Invoice and line item data grow linearly with business operations. Audit logs grow unbounded.

---

## 14. Logging Cost Boundary

* **File Rotation Caps**:
  * `logs/advance_billing.log`: Max 10 MB × 5 backups = 50 MB.
  * `logs/errors.log`: Max 10 MB × 5 backups = 50 MB.
* **Total Local Log Ceiling**: **100 MB Hard Cap**.
* **Container Storage Risk**: Writing logs to local disk inside containerized environments can cause ephemeral container storage bloat or log loss on container restart.

---

## 15. Rate-Limit Boundary Matrix

| Endpoint Path | View Name | Authentication Required? | Enforced Rate Limit | Burst Limit | Concurrency Limit | Expensive Operation? | Risk Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/login/` | `LoginView` | NO | **NONE** | **NONE** | **NONE** | YES (Password Hash) | **UNBOUNDED — HIGH RISK** |
| `/signup/` | `SignupView` | NO | **NONE** | **NONE** | **NONE** | YES (User DB + Email) | **UNBOUNDED — HIGH RISK** |
| `/forgot-password/` | `ForgotPasswordView` | NO | **NONE** | **NONE** | **NONE** | YES (SMTP Email) | **UNBOUNDED — HIGH RISK** |
| `/auth/resend-verification/` | `ResendVerificationEmailView` | NO (Session) | **NONE** | **NONE** | **NONE** | YES (SMTP Email) | **UNBOUNDED — HIGH RISK** |
| `/invoices/<uuid>/pdf/` | `InvoicePreviewView` | YES | **NONE** | **NONE** | **NONE** | YES (WeasyPrint PDF) | **UNBOUNDED — HIGH RISK** |
| `/settings/invoice-design/preview/` | `SettingsInvoiceDesignPreviewAPIView` | YES | **NONE** | **NONE** | **NONE** | YES (WeasyPrint PDF) | **UNBOUNDED — HIGH RISK** |
| `/invoices/<uuid>/mail/` | `InvoiceMailView` | YES | **NONE** | **NONE** | **NONE** | YES (Thread + PDF + SMTP)| **UNBOUNDED — HIGH RISK** |
| `/settings/data/export/` | `SettingsDataExportView` | YES (Owner) | **NONE** | **NONE** | **NONE** | YES (Full DB Fetch + ZIP) | **UNBOUNDED — HIGH RISK** |
| `/settings/data/export-excel/` | `SettingsExcelExportView` | YES (Owner) | **NONE** | **NONE** | **NONE** | YES (Full DB + openpyxl) | **UNBOUNDED — HIGH RISK** |
| `/settings/data/backup-mail/` | `SettingsDataBackupMailView` | YES (Owner) | **NONE** | **NONE** | **NONE** | YES (Dual Format + SMTP)| **UNBOUNDED — HIGH RISK** |

---

## 16. Input Cost Boundary

* **Invoice Line Items**: Formset accepts unbounded `lines-TOTAL_FORMS`. Submitting 1,000+ line items forces heavy calculation and WeasyPrint timeout.
* **Uploaded File Sizes**: Form fields accept unbounded file upload sizes.
* **Text Input Lengths**: Notes and terms fields use unbounded `TextField`.

---

## 17. Autoscaling Cost Boundary

> **"OCI-side configuration could not be verified from the available repository."**

### Verification Required Manually in OCI Console:
* **Compute Instance Pools**: Verify that instance pool autoscaling policies have an explicit **Maximum Instance Count Ceiling** (e.g. max 4 instances).
* **Autonomous Database**: Verify that max ECPU auto-scaling limits are explicitly bounded.
* **Load Balancer**: Configure request timeout (60s) and rate limiting on OCI Load Balancer.

---

## 18. OCI Resource Orphan & Accumulation Audit Checklist

* **Resources to Audit in OCI Console**: Unattached Block Volumes, unattached Boot Volumes, orphan Compute Snapshots, unattached Reserved Public IPs, un-lifecycle-managed Object Storage buckets.

---

## 19. Five Worst-Case Resource Amplification Chains

### Chain 1: Unbounded Background Worker Thread Spawning
`User Action (Issue Invoice)` ➔ `transaction.on_commit` ➔ `send_invoice_email_async` ➔ `threading.Thread.start()` ➔ `WeasyPrint PDF Render in Thread RAM` ➔ `Brevo SMTP Dispatch` ➔ **CPU/RAM Saturation & Worker OOM Crash**
* **Severity**: **P0** | **Growth**: Multiplicative / Unbounded | **Repeatable**: YES

### Chain 2: Synchronous PDF Rendering CPU Amplification
`HTTP GET (/invoices/<uuid>/pdf/)` ➔ `InvoicePreviewView` ➔ `InvoicePreviewService.render_bill_pdf` ➔ `WeasyPrint.write_pdf()` ➔ **100% CPU Core Saturation Across All Workers**
* **Severity**: **P0** | **Growth**: Multiplicative / Unbounded | **Repeatable**: YES

### Chain 3: In-Memory Full Data Export Memory Spike
`HTTP GET (/settings/data/export/)` ➔ `generate_single_snapshot()` ➔ `Full DB Table QuerySet Fetch` ➔ `JSON + openpyxl Construction in RAM` ➔ **Multi-Gigabyte Memory Spike & OOM Killer**
* **Severity**: **P1** | **Growth**: Linear with DB size | **Repeatable**: YES

### Chain 4: Un-ratelimited Password Reset Email Flooding
`Automated HTTP POST (/forgot-password/)` ➔ `ForgotPasswordView` ➔ `Brevo SMTP Dispatch` ➔ **Brevo API Quota Exhaustion & Third-Party Billing Spike**
* **Severity**: **P1** | **Growth**: Multiplicative / Unbounded | **Repeatable**: YES

### Chain 5: Image Decompression Bomb Memory Saturation
`HTTP POST (/organization/detail/)` ➔ `OrganizationUpdateForm` ➔ `Unvalidated Image Upload` ➔ `Pillow Decompress into RAM` ➔ **Process RAM Exhaustion & Worker Crash**
* **Severity**: **P1** | **Growth**: Unbounded Pixel Payload | **Repeatable**: YES

---

## 20. Cost Ceiling Test

* **Maximum work one user can cause in one minute**: **NOT BOUNDED** (Can trigger unlimited background WeasyPrint threads and synchronous PDF renders).
* **Maximum work one organization can cause in one minute**: **NOT BOUNDED** (Can trigger unlimited data exports, backup emails, and PDF previews).
* **Maximum work application can execute concurrently**: **NOT BOUNDED** (Background daemon threads spawn without a concurrency cap).

---

## 21. Hard Boundary Matrix

| Resource / Operation | Current Boundary | Effective? | Single User Max | Single Org Max | Global Max | Failure Behavior | Severity |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gunicorn workers** | Fixed Pool (4 Workers) | YES | 8 Slots | 8 Slots | 8 Slots | Requests Queue / Timeout | **P2** |
| **Background threads** | None | NO | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | RAM/CPU Saturation & OOM | **P0** |
| **PDF renders** | None | NO | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | 100% CPU Core Saturation | **P0** |
| **Invoice emails** | None | NO | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | Brevo Quota Exhaustion | **P1** |
| **Password reset emails** | None | NO | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | Brevo Quota Exhaustion | **P1** |
| **Data exports** | None | NO | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | RAM Spike & Worker OOM | **P1** |
| **Backups** | 15 MB Attachment Limit | PARTIAL | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | RAM Spike before check | **P1** |
| **File uploads** | None | NO | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | Pillow RAM Saturation | **P1** |
| **Database connections**| `conn_max_age=600` | YES | $8 + N_{\text{threads}}$ | $8 + N_{\text{threads}}$ | $8 + N_{\text{threads}}$ | Connection Pool Exhaustion | **P2** |
| **DB queries** | `[:20]` / `paginate_by=25` | PARTIAL (Except Exports) | **UNBOUNDED** (Exports) | **UNBOUNDED** | **UNBOUNDED** | High DB Read IOPS | **P1** |
| **Storage** | Cloudinary / Local Disk | PARTIAL | **UNBOUNDED** | **UNBOUNDED** | **UNBOUNDED** | Storage Bill Inflation | **P2** |
| **Logs** | 10 MB × 5 Rotation | YES | 100 MB | 100 MB | 100 MB Cap | Log File Rotation | **P3** |
| **OCI instances** | OCI Console Config | REQUIRES OCI VERIFICATION | Unknown | Unknown | Unknown | Autoscaling Multiplication | **P0** |
| **OCI database compute** | OCI Console Config | REQUIRES OCI VERIFICATION | Unknown | Unknown | Unknown | ECPU Scaling Multiplication | **P1** |

---

## 22. Required Final Report

### 1. Executive Verdict: **NEEDS COST CONTROLS**
The Advance Billing application contains robust domain models, correct multi-tenant scoping, and well-designed GST math calculations. However, it currently lacks finite cost and resource boundaries in critical runtime areas — specifically **un-bounded background thread spawning**, **synchronous WeasyPrint CPU/RAM saturation**, **un-ratelimited API and authentication endpoints**, and **un-paginated in-memory data exports**. Deploying the application in its current state without application-level rate limits and worker thread pools exposes the system to potential cloud billing spikes and worker process crashes under load.

### 2. Critical P0 Findings
1. **Unbounded Background Worker Thread Spawning on Invoice Issue** ([`invoice_email_service.py:248`](file:///Users/vyom/Vyom/Advance%20Billing/apps/billing/services/invoice_email_service.py#L248)) — Spawns un-bounded background daemon threads executing WeasyPrint rendering without a thread pool or concurrency cap.
2. **Unbounded Synchronous CPU/RAM Amplification via WeasyPrint PDF Rendering** ([`invoice_preview_service.py:257`](file:///Users/vyom/Vyom/Advance%20Billing/apps/invoices/services/invoice_preview_service.py#L257)) — Synchronous PDF generation on un-ratelimited endpoints allows request bursts to saturate 100% CPU cores and consume multi-gigabyte RAM.

### 3. P1 Findings
1. **Unbounded Memory Loading in Data Backup & Export Services** ([`backup_service.py:100`](file:///Users/vyom/Vyom/Advance%20Billing/apps/settings_app/services/backup_service.py#L100)) — Loads entire database tables into RAM lists during exports.
2. **Complete Absence of Rate Limiting Across All Endpoints** ([`authentication/views.py:75`](file:///Users/vyom/Vyom/Advance%20Billing/apps/authentication/views.py#L75)) — Zero `@ratelimit` decorators applied across the codebase.
3. **Unrestricted File Upload Size & Decompression Bomb Exposure** ([`organization/forms.py:65`](file:///Users/vyom/Vyom/Advance%20Billing/apps/organization/forms.py#L65)) — Unvalidated upload file sizes and image pixel dimensions.
4. **Unbounded Invoice Line Item Submission** ([`billing/views.py:197`](file:///Users/vyom/Vyom/Advance%20Billing/apps/billing/views.py#L197)) — Formset accepts unlimited line items per invoice.

### 4. P2 Findings
1. **Unbounded Growth of Audit and Backup Log Tables** ([`settings_app/models.py:120`](file:///Users/vyom/Vyom/Advance%20Billing/apps/settings_app/models.py#L120)) — No retention cleanup for backup and audit logs.
2. **Gunicorn Configuration Discrepancy Between Procfile and render.yaml** ([`render.yaml:13`](file:///Users/vyom/Vyom/Advance%20Billing/render.yaml#L13)) — `render.yaml` defaults to 1 sync worker.

### 5. P3 Findings
1. **Local Log File Rotation Writing to Container Storage** ([`base.py:368`](file:///Users/vyom/Vyom/Advance%20Billing/core/settings/base.py#L368)) — Writes logs to local disk in container environment.
2. **In-Memory LocMemCache Backend in Production** ([`production.py:120`](file:///Users/vyom/Vyom/Advance%20Billing/core/settings/production.py#L120)) — Un-shared cache across multiple workers.

### 6. Cost Boundary Matrix
*(Refer to Section 21 above for full table)*

### 7. Top 10 Cost Amplification Risks
1. Unbounded Background Daemon Threads on Invoice Issue
2. Brevo SMTP API Quota Exhaustion via Un-ratelimited Endpoints
3. Synchronous WeasyPrint CPU Saturation on PDF Previews
4. In-Memory Data Export RAM Spikes
5. Unrestricted Image Uploads inflating Cloudinary Storage Charges
6. Un-ratelimited Authentication Endpoints (Credential Stuffing CPU Load)
7. Unbounded Line Item Invoice Submissions
8. Un-ratelimited Manual Backup Mail Trigger
9. Un-archived Historical Database Growth
10. Un-pruned Audit Log Accumulation

### 8. Top 10 Resource Exhaustion Risks
1. Gunicorn Worker Memory Exhaustion (OOM) via WeasyPrint
2. Server CPU Core Saturation via WeasyPrint Layout Calculations
3. Python Process Thread Exhaustion via `send_invoice_email_async`
4. Server Memory (RAM) Exhaustion during Full DB Data Exports
5. Brevo SMTP Connection Timeout / Lockup
6. Pillow Decompression Bomb Memory Saturation
7. Single-Worker Throughput Lockup (`render.yaml` deployment)
8. Gunicorn Request Worker Timeout (60s SIGKILL)
9. Database Connection Pool Saturation
10. Database Storage Footprint Growth from Audit Logs

### 9. Five Worst-Case Attack / Abuse Paths
1. **Un-authenticated Auth Flooding**: Attacker script posts 1,000 requests/min to `/forgot-password/` ➔ Exhausts Brevo SMTP API quota & sends spam.
2. **PDF Preview CPU Denial of Service**: Attacker repeatedly hits `/invoices/<uuid>/pdf/` ➔ Locks all 4 Gunicorn workers in 100% CPU WeasyPrint loops.
3. **Decompression Bomb Upload**: Attacker uploads a 5 MB image decompressing to 4 GB in RAM ➔ Instantly triggers Gunicorn OOM killer.
4. **Data Export Memory Exhaustion**: Authenticated user repeatedly requests `/settings/data/export/` ➔ Spikes RAM by gigabytes until container crashes.
5. **Bulk Invoice Issue Thread Explosion**: User issues 100 invoices in automated loop ➔ Spawns 100 background threads running WeasyPrint & DB queries simultaneously.

### 10. Five Worst-Case Accidental Paths
1. **Accidental Rapid Clicking on "Email Copy"**: User clicks button multiple times ➔ Spawns multiple background threads & duplicate emails.
2. **Creating an Invoice with 1,000 Line Items**: User pastes large product list ➔ WeasyPrint times out after 60 seconds of 100% CPU rendering.
3. **Frequent Excel Backup Exports**: User repeatedly downloads Excel backups ➔ High RAM allocations on openpyxl workbook creation.
4. **Uploading Raw High-Res 50 MB DSLR Images**: User uploads uncompressed logo ➔ High Cloudinary bandwidth & slow page loads.
5. **Running Weekly Backups on Large Database**: Scheduled backup job fetches hundreds of thousands of rows into RAM ➔ Memory pressure on host VM.

### 11. OCI Controls Still Requiring Manual Verification
* **Compute Instance Pools**: Verify instance pool autoscaling has a **hard maximum instance count** (e.g. max 4 instances).
* **Autonomous Database**: Verify max ECPU Auto Scaling multiplier is capped.
* **Load Balancer**: Configure request timeout (60s) and rate-limiting rules on OCI Load Balancer.

### 12. Required Production Guardrails

#### Application
* Apply `@ratelimit` decorators to all auth, email, PDF, and export endpoints.
* Enforce max **100 line items** per invoice in `InvoiceForm`.
* Enforce max file size validation (**2 MB max** for images) and set `PIL.Image.MAX_IMAGE_PIXELS = 10_000_000`.

#### Workers
* Replace `threading.Thread` in `InvoiceEmailService` with a bounded worker pool or task queue (e.g. Celery / Redis / RQ).
* Add `--max-requests 1000 --max-requests-jitter 50` to Gunicorn CLI command.

#### PDF
* Cache rendered PDF bytes for issued invoices to prevent re-compilation.

#### Database
* Stream export datasets using `QuerySet.iterator()`.
* Add cleanup task for `OrganizationBackupLog` and `DataManagementAuditLog`.

#### Storage
* Enforce strict file size caps on uploads.

#### Email
* Set rate limits on all email dispatch endpoints.

#### OCI
* Cap maximum autoscaling instance counts and database ECPUs in OCI Console.

#### Monitoring
* Set OCI Billing Alerts at 50%, 75%, and 90% of monthly budget.

---

### 13. Minimum Required Before Public Launch
1. **Replace Raw Threads with Worker Queue**: Implement bounded task queue / worker pool for `send_invoice_email_async`.
2. **Apply Rate Limits**: Decorate all auth, email, PDF, and export endpoints with `django-ratelimit`.
3. **Enforce Upload & Line Caps**: Add max file size checks (2 MB) and max line item caps (100 items).
4. **Fix Gunicorn Startup Flags**: Align `render.yaml` startCommand with `Procfile` and add `--max-requests 1000`.
5. **Verify OCI Autoscaling Caps**: Ensure OCI Instance Pools have an explicit maximum instance ceiling in OCI Console.

---

### 14. Recommended Later Improvements
* Upgrade `LocMemCache` to Redis (`django-redis`).
* Configure production log handlers to output to `stdout`/`stderr` for cloud log drivers.
* Implement historical data archiving for multi-year invoices.

---

### Audit Verification Statement
This audit was performed strictly in **READ-ONLY** mode. Zero workspace files, database records, environment configurations, or infrastructure assets were modified during this audit.
