# OCI Cost Explosion & Resource Runaway Audit Report — Advance Billing

**Audit Date**: August 27, 2026  
**Application**: Advance Billing (GST Billing & Invoicing System)  
**Target Environment**: Oracle Cloud Infrastructure (OCI)  
**Audit Scope**: Read-Only Cost, Performance, & Cloud Resource Runaway Audit  
**Audit Status**: **NEEDS ATTENTION** (Critical P0 & P1 risks identified prior to production deployment)

---

## 1. Production Architecture Summary

| Architecture Component | Implementation / Technology Verified in Repository |
| :--- | :--- |
| **Framework & Version** | Django `5.1.4` (Python 3.12+) |
| **WSGI / Web Server** | Gunicorn `23.0.0` |
| **Worker Process Config** | Procfile: `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 60`<br>render.yaml: `gunicorn core.wsgi:application` (Default: 1 sync worker, 1 thread) |
| **Worker Recycling** | **NONE** (`max-requests` and `max-requests-jitter` are not configured) |
| **Worker Memory Limits** | **NONE** (No process RSS caps or `--limit-request-line` configured) |
| **Background Job System** | In-process daemon threads (`threading.Thread` in `InvoiceEmailService.send_invoice_email_async`). **No Celery, Redis, RQ, or external task queues present.** |
| **Cron / Scheduled Jobs** | Management commands (`run_weekly_backups`, `cleanup_notifications`). No repository-defined crontab or systemd timers. |
| **Database** | Production: PostgreSQL (`psycopg2-binary 2.9.10`, `dj-database-url 2.3.0`, `conn_max_age=600`, `conn_health_checks=True`). Dev: SQLite (`db.sqlite3`). |
| **File / Media Storage** | Production: Cloudinary (`cloudinary 1.42.1`, `django-cloudinary-storage 0.3.0`). Dev: Local file system (`MEDIA_ROOT = BASE_DIR / "media"`). |
| **PDF Generation Engine** | `WeasyPrint 63.0` (Synchronous C-extension rendering via Cairo/Pango/Fontconfig). Also invoked inside background threads when emailing invoices. |
| **Email Service** | Brevo via Django SMTP (`django.core.mail.backends.smtp.EmailBackend`). |
| **External APIs / Services** | Brevo SMTP API, Cloudinary Storage API, Lucide Icons CDN, Chart.js CDN, Google Fonts. |
| **Logging System** | Django standard logging to `logs/advance_billing.log` and `logs/errors.log` via `RotatingFileHandler` (10 MB max, 5 backups) and Console `StreamHandler`. |
| **OCI Configuration** | *OCI-side configuration could not be verified from the available repository.* |

---

## 2. Worker / Process Runaway Audit

* **Worker Count & Bounds**: Procfile specifies 4 sync workers with 2 threads per worker (8 concurrent slots). However, `render.yaml` specifies unflagged `gunicorn core.wsgi:application` (which defaults to 1 sync worker).
* **Process Spawning**: WSGI worker processes do not fork child sub-processes, but they spawn **un-bounded daemon Python threads** (`threading.Thread(target=worker, daemon=True)`) upon issuing invoices (`issue_invoice`).
* **Worker Crash Loops**: Gunicorn master process automatically restarts crashed sync workers. If WeasyPrint C-level memory allocation causes a worker to hit OS OOM limits, Gunicorn continuously restarts workers in a crash loop under traffic.
* **Worker Recycling**: **MISSING**. Without `max-requests` set in Gunicorn, memory leaks or C-extension heap fragmentation (from WeasyPrint / Cairo) accumulate continuously until the worker is killed by OS OOM.
* **Timeout Limits**: 60 seconds (Procfile) or 30 seconds (default). If WeasyPrint or SMTP blocks, worker thread is held for up to 60 seconds before SIGKILL.
* **Worker Exhaustion Risk**: With only 4 sync workers (or 1 in render.yaml), 4 concurrent heavy PDF downloads or slow Brevo SMTP email connections will lock 100% of available worker capacity, causing complete application Denial of Service (DoS) for all other users.

---

## 3. Background Job / Task Runaway Audit

### Identified Background Execution Paths:
1. **`InvoiceEmailService.send_invoice_email_async`**
   * **Trigger**: Called in `apps/billing/services/lifecycle.py:185` via `transaction.on_commit(trigger_auto_email)` when any invoice is issued.
   * **Execution Model**: Spawns `threading.Thread(target=worker, daemon=True).start()`.
   * **Frequency**: Unbounded — triggers on every `post` to `/invoices/<uuid>/issue/`.
   * **Workload Inside Thread**: Runs full `WeasyPrint` PDF rendering (`generate_pdf_bytes`) inside thread RAM/CPU, constructs `EmailMultiAlternatives`, and calls `email.send()`.
   * **Worker Limits / Queue Depth**: **NONE**. No thread pool, no semaphores, no queue cap. Issuing 100 invoices spawns 100 concurrent threads running WeasyPrint simultaneously inside the Gunicorn worker process.
   * **Retries**: 0 automatic retries; catches exception and logs to `Invoice.email_last_error`.
2. **`run_weekly_backups` Management Command**
   * **Trigger**: Executed via external cron/scheduler (`python manage.py run_weekly_backups`).
   * **Behavior**: Loops over all organizations with `weekly_backup_enabled=True`. Checks 6-day idempotency (`now - setting.last_backup_at < 6 days`). Generates JSON + Excel backups in memory, validates payload size (< 15 MB), and dispatches dual-attachment emails.
   * **Retries**: None; logs failure to `OrganizationBackupLog`.

---

## 4. Request Amplification Audit

| Endpoint / Action | Trigger | Backend Amplification Mechanism | Risk Description |
| :--- | :--- | :--- | :--- |
| **Instant Backup Email** (`SettingsDataBackupMailView`) | 1 POST click | 1 Request → Reads entire org database → Generates JSON in memory → Generates multi-sheet Excel with openpyxl → Validates payloads → Dispatches SMTP email with 15MB attachments. | High CPU & RAM amplification per click. No rate limiting. |
| **AJAX PDF Design Preview** (`SettingsInvoiceDesignPreviewAPIView`) | 1 Input change / Preview click | 1 Request → Queries org assets → Serializes bill → Builds PrintableFrame geometry → Runs synchronous WeasyPrint PDF compilation. | Repeated rapid UI preview clicks trigger multiple concurrent CPU-heavy WeasyPrint renders. |
| **Invoice Issue Action** (`InvoiceIssueView`) | 1 POST click | 1 Request → Validates GST → Locks preference row (`select_for_update`) → Generates invoice number → `on_commit` spawns daemon thread → Thread runs WeasyPrint PDF render → Sends SMTP email. | Concurrent issuing creates multiple background WeasyPrint threads per request. |
| **Manual Data Export** (`SettingsDataExportView` & `SettingsExcelExportView`) | 1 GET click | 1 Request → Queries full database tables (`Customer`, `Product`, `Invoice`, `InvoiceLine`) into unpaginated memory list → Zips/compiles Excel in RAM → Streams byte payload. | Large database size causes high RAM spikes per download. |
| **Account Deletion** (`SettingsDeleteAccountView`) | 1 POST request | 1 Request → Deletes `InvoiceLine`, `Invoice`, `Customer`, `Product`, `Notification`, `OrganizationBackupSetting`, `OrganizationBackupLog`, `UserBillPreference`, `Organization` in single transaction. | High DB write/delete IOPS spike. |

---

## 5. PDF Generation Cost Audit

* **Rendering Engine**: `WeasyPrint 63.0` (C-library based Cairo/Pango/Fontconfig renderer).
* **Resource Profile**: **Extremely CPU and RAM intensive**. CSS parsing, layout calculation, font shaping, and vector drawing consume high CPU cycles and 50–200+ MB RAM per render pass.
* **Execution Model**: **Synchronous in WSGI Worker Threads** for previews and downloads; **Asynchronous in Daemon Threads** for invoice email delivery.
* **Caching**: **NONE**. PDF bytes are compiled from scratch on every preview, download, or email request.
* **Storage Cleanup**: PDFs are rendered to in-memory `bytes` and returned directly via HTTP / attached to email. Zero persistent disk PDF files accumulated.
* **Invoice Size Exposure**: **UNBOUNDED**. There is no limit on the number of line items allowed per invoice. An invoice containing 1,000 line items will force WeasyPrint to compute layout for dozens of pages, taking 10–30+ seconds of 100% CPU utilization and consuming gigabytes of memory, triggering Gunicorn worker timeouts (60s).

---

## 6. Database Resource Explosion Audit

* **Unbounded QuerySets in Backups**: `OrganizationBackupService.generate_single_snapshot()` queries database records without pagination:
  ```python
  Customer.objects.filter(organization=organization)
  Product.objects.filter(organization=organization)
  Invoice.objects.filter(organization=organization).select_related("customer")
  InvoiceLine.objects.filter(invoice__organization=organization).select_related("invoice", "product")
  ```
  When an organization accumulates 100,000 invoices and 500,000 line items, exporting or backing up data loads the entire dataset into Python RAM at once.
* **Missing Retention Policies**: `OrganizationBackupLog` and `DataManagementAuditLog` grow linearly with system usage and have no cleanup task or retention expiration.
* **Optimized Queries**: `InvoiceListView` is properly paginated (`paginate_by = 25`) and uses `select_related("customer")`. `CustomerSearchAPIView` and `ProductSearchAPIView` cap results at `[:20]`. Database indexes exist on `(organization, status)` and `(organization, invoice_number)`.

---

## 7. Storage Growth Audit

* **Uploaded Assets**: Organization Logo, Signature Image, Letterhead Image, QR Code Image.
* **Storage Location**: Cloudinary in Production (`django-cloudinary-storage`); Local Disk in Development (`MEDIA_ROOT`).
* **Validation Deficiencies**: No maximum file size limit validation in `OrganizationSetupForm` or `OrganizationUpdateForm`.
* **Growth Estimation**:
  * 1,000 organizations × 4 branding images (average 1 MB each) = ~4 GB media storage.
  * Generated PDFs are in-memory bytes and do NOT consume media storage.

---

## 8. Logging / Disk Exhaustion Audit

* **Production Log Settings**: `DEBUG = False`. `django` logger set to `WARNING`, `apps` logger set to `INFO`.
* **Log Rotation**: `LOGGING` config uses `RotatingFileHandler`:
  * `advance_billing.log`: 10 MB max, 5 backups (50 MB ceiling).
  * `errors.log`: 10 MB max, 5 backups (50 MB ceiling).
* **Disk Risk**: Disk usage is strictly capped at 100 MB total. However, writing logs to container local disk (`BASE_DIR / "logs"`) in containerized environments (OCI Container Instances / Render) can cause ephemeral disk bloat or lost logs on container restart.

---

## 9. External API & Service Amplification Audit

* **Brevo SMTP API**:
  * Triggered on user signup, password reset, email change, invoice issuance, manual invoice mail, and weekly backup runs.
  * No per-user or global rate limiting is enforced on email endpoints.
  * Malicious users or retry loops can consume monthly Brevo SMTP quotas rapidly, resulting in unexpected usage-based API charges or service disruption.
* **Cloudinary Storage API**:
  * Triggered on organization logo/signature/letterhead upload.
  * Unrestricted file sizes could inflate Cloudinary storage and bandwidth billing.

---

## 10. File Upload Abuse & Resource Audit

* **Upload Fields**: `logo`, `signature`, `letterhead`, `qr_code` on `OrganizationUpdateForm`; `backup_file` on `SettingsExcelImportRestoreView`.
* **Validation Gaps**:
  1. **No Maximum File Size Limit**: No validation rejecting files larger than 2MB/5MB.
  2. **No Image Dimension Caps**: No `PIL.Image.MAX_IMAGE_PIXELS` safety limit. Small crafted files expanding to multi-gigabyte pixel arrays (decompression bombs) can cause immediate server RAM crash.
  3. **No File Extension Validation**: Upload forms do not restrict mime types via `FileExtensionValidator`.

---

## 11. Database Growth Map

```
[Users / Organizations Scale]
       │
       ├──► Customer Records (Linear DB Growth, Index-Protected)
       ├──► Product Records (Linear DB Growth, Index-Protected)
       ├──► Invoice & InvoiceLine Records (Linear DB Growth, Index-Protected)
       │        └──► Export / Backup Memory Load (MULTI-MEGABYTE RAM SPIKE ON EXPORT)
       ├──► Notifications (BOUNDED: Inline Cleanup Enforces 300 Max Per User)
       ├──► OrganizationBackupLog (UNBOUNDED DB Growth — No Retention Policy)
       └──► DataManagementAuditLog (UNBOUNDED DB Growth — No Retention Policy)
```

---

## 12. Notification & Email Runaway Audit

* **Notification Loop Check**: `NotificationService.create()` calls `_trigger_cleanup(user)` to enforce a strict limit of 300 notifications per user. It does not trigger secondary model saves or recursive signals. **No notification event loops exist.**
* **Email Loop Check**: `send_invoice_email()` updates `invoice.email_sent` via `save(update_fields=[...])`. It does not transition invoice status or re-trigger `issue_invoice()`. **No recursive email loops exist.**
* **Manual Trigger Risk**: `InvoiceMailView` allows users to click "Email Copy" repeatedly. Each click spawns an un-bounded background thread running WeasyPrint and calling SMTP without rate limiting.

---

## 13. Rate Limiting Audit

| Endpoint | Path | Rate Limit Status | Risk Classification |
| :--- | :--- | :--- | :--- |
| **Login** | `/login/` | **UNLIMITED** | **DANGEROUS** (Brute-force / Credential stuffing) |
| **Signup** | `/signup/` | **UNLIMITED** | **DANGEROUS** (Account creation spam) |
| **Forgot Password** | `/forgot-password/` | **UNLIMITED** | **DANGEROUS** (Brevo SMTP quota exhaustion) |
| **Resend Verification** | `/auth/resend-verification/` | **UNLIMITED** | **DANGEROUS** (Email flooding) |
| **Invoice PDF View** | `/invoices/<uuid>/pdf/` | **UNLIMITED** | **DANGEROUS** (CPU/RAM WeasyPrint saturation) |
| **AJAX Design Preview** | `/settings/invoice-design/preview/` | **UNLIMITED** | **DANGEROUS** (Synchronous PDF CPU exhaustion) |
| **Invoice Email Copy** | `/invoices/<uuid>/mail/` | **UNLIMITED** | **DANGEROUS** (Unbounded thread + SMTP amplification) |
| **Data Export ZIP** | `/settings/data/export/` | **UNLIMITED** | **DANGEROUS** (High RAM DB load per download) |
| **Excel Export** | `/settings/data/export-excel/` | **UNLIMITED** | **DANGEROUS** (High RAM openpyxl compilation) |
| **Instant Backup Mail** | `/settings/data/backup-mail/` | **UNLIMITED** | **DANGEROUS** (Dual backup + Email dispatch) |

*Note: `django-ratelimit` is installed in `requirements.txt` and `INSTALLED_APPS`, but zero `@ratelimit` decorators are applied to any view function or class in the repository.*

---

## 14. Input Limit Audit

* **Line Items Quantity**: `lines-TOTAL_FORMS` in invoice forms is unbounded. Posting 1,000+ line items causes high calculation overhead and WeasyPrint timeout.
* **Uploaded Images**: File sizes and image pixel dimensions are unrestricted.
* **Text Fields**: `notes` and `terms` fields use unbounded `TextField`.

---

## 15. OCI Infrastructure & Autoscaling Audit

> **"OCI-side configuration could not be verified from the available repository."**

### Verification Required Manually in OCI Console:
1. **Compute Instance Pools & Autoscaling**: Ensure instance pool autoscaling policies have a **hard maximum instance count** (e.g., max 4 instances) to prevent runaway instance scaling under CPU saturation.
2. **Autonomous / Managed Database**: Check OCI Autonomous Database Auto Scaling settings for ECPUs and Storage to ensure max ECPU auto-scaling is capped.
3. **Object Storage Lifecycle Rules**: Verify lifecycle policies are configured to purge old backups or temporary objects if OCI Object Storage is used.
4. **Load Balancer Connection Limits**: Set max connection limits and request timeout thresholds on OCI Flexible Load Balancer.

---

## 16. Failure-Loop Audit

| Scenario | Application Behavior | Resource Impact | Bounded? |
| :--- | :--- | :--- | :--- |
| **Database Unavailable** | `dj-database-url` health checks detect error; Django returns 500 error page. | Minimal (Connection retries drop gracefully). | **YES** |
| **PDF Rendering Fails** | Catches exception, logs warning, attempts fallback `simple_invoice.html`, then emergency HTML string. | 1 Extra WeasyPrint render attempt, then returns response. | **YES** |
| **Email Provider Fails** | SMTP exception caught, logged, `email_last_status = FAILED` saved to DB. | No retry loop; thread terminates. | **YES** |
| **Redis Unavailable** | Application uses `LocMemCache` in production; Redis is not configured. | N/A | **YES** |
| **Background Thread Crashes** | Thread logs error, executes `close_old_connections()` in `finally` block, terminates. | No automatic thread restart. | **YES** |
| **User Repeatedly Clicks "Generate PDF"** | Each request runs WeasyPrint synchronously in Gunicorn worker or background thread. | CPU/RAM usage multiplies linearly with request rate. | **NO (UNBOUNDED)** |
| **User Submits 2,000 Line Item Invoice** | Calculation completes, but WeasyPrint layout parsing exceeds timeout (60s). | Worker killed by Gunicorn SIGKILL after 60s CPU load. | **NO (HIGH SPIKE)** |

---

## 17. Cost-Amplification Matrix

| Component | Trigger | Resource Consumed | Can Grow Indefinitely? | Maximum Bound | Severity |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Background Worker Threads** | Invoice Issue (`issue_invoice`) | CPU / RAM / Threads | **YES** | **UNBOUNDED** | **P0** |
| **PDF Rendering Engine** | Preview / Download / Mail / Design | CPU / RAM | **YES** | **UNBOUNDED** (No concurrency cap) | **P0** |
| **Data Export & Backups** | Export ZIP / Backup Mail / Command | DB IOPS / RAM / CPU | **YES** | **UNBOUNDED** (Loads all DB rows into RAM) | **P1** |
| **Rate Limiting Deficiencies** | Auth / PDF / Mail / Export Endpoints | CPU / RAM / SMTP API | **YES** | **UNBOUNDED** | **P1** |
| **File Upload Validation** | Logo / Signature / Backup Uploads | RAM / Disk / Storage | **YES** | **UNBOUNDED** (No file size/pixel cap) | **P1** |
| **Invoice Line Item Formset** | Invoice Creation / Editing | CPU / RAM / DB | **YES** | **UNBOUNDED** (No line item limit) | **P1** |
| **Audit Log Tables** | Backup Logs & Audit Logs | DB Storage / IOPS | **YES** | **UNBOUNDED** (No retention policy) | **P2** |
| **Gunicorn Config Discrepancy** | Deployment via `render.yaml` | Worker Throughput | **NO** | 1 Sync Worker Limit | **P2** |
| **Log File Rotation** | System Logging | Local Disk | **NO** | 100 MB (50 MB x 2 log files) | **P3** |
| **LocMemCache in Production** | Cache Operations | Process RAM | **NO** | Bounded by Process Memory | **P3** |

---

## 18. Detailed Audit Findings

### P0-1: Unbounded Background Worker Thread Spawning on Invoice Issue
* **Severity**: **P0**
* **Exact Location**: `apps/billing/services/invoice_email_service.py:248`, `apps/billing/services/lifecycle.py:185`
* **Trigger**: Every call to `issue_invoice()` triggers `transaction.on_commit(trigger_auto_email)`, which calls `InvoiceEmailService.send_invoice_email_async()`.
* **Resource Affected**: CPU / RAM / OS Process Threads.
* **Growth Behavior**: Multiplicative / Unbounded (1 daemon thread per issued invoice, zero concurrency cap).
* **Worst-Case Scenario**: Issuing invoices in bulk or rapid API calls spawns dozens of background daemon threads inside the Gunicorn worker process. Each thread executes heavy WeasyPrint PDF rendering in C memory. This causes CPU saturation, multi-gigabyte RAM spikes, and OS OOM killer termination of Gunicorn workers.
* **Billing Impact**: Triggers OCI Compute CPU/RAM utilization spikes and potential instance autoscaling multiplication, directly inflating OCI compute costs.
* **Existing Protection**: None.
* **Recommended Fix**: Replace raw `threading.Thread` with a dedicated asynchronous job queue (e.g. Celery + Redis or RQ) with bounded worker concurrency and queue limits.

---

### P0-2: Unbounded Synchronous CPU/RAM Amplification via WeasyPrint PDF Rendering
* **Severity**: **P0**
* **Exact Location**: `apps/invoices/services/invoice_preview_service.py:257`, `apps/settings_app/views.py:481`, `apps/billing/views.py:604`, `apps/organization/views.py:253`
* **Trigger**: Visiting PDF preview (`/invoices/<uuid>/pdf/`), clicking invoice design AJAX preview, downloading PDF, or letterhead preview.
* **Resource Affected**: CPU / RAM.
* **Growth Behavior**: Multiplicative / Unbounded.
* **Worst-Case Scenario**: WeasyPrint performs heavy HTML/CSS layout calculation and Cairo vector drawing synchronously inside the Gunicorn HTTP request thread. Multiple concurrent PDF requests or requests for invoices with large line-item counts saturate 100% CPU cores and consume gigabytes of RAM, locking all Gunicorn workers and causing web application unavailability.
* **Billing Impact**: High CPU saturation on OCI compute instances, potentially triggering autoscaling scaling events and high OCI compute billing.
* **Existing Protection**: Fallback template mechanism (`simple_invoice.html`), but zero rate limiting, zero concurrency capping, and zero PDF caching.
* **Recommended Fix**: Implement rate limiting (`django-ratelimit`) on PDF endpoints, enforce maximum line item limits for rendering, and cache generated PDF bytes for issued invoices.

---

### P1-1: Unbounded Memory Loading in Data Backup & Export Services
* **Severity**: **P1**
* **Exact Location**: `apps/settings_app/services/backup_service.py:100-238`, `apps/settings_app/services/excel_backup_service.py:60-350`, `apps/settings_app/views.py:686`
* **Trigger**: Manual export download (`/settings/data/export/`), Excel export, instant backup email, or `run_weekly_backups` command.
* **Resource Affected**: RAM / CPU / Database Read IOPS.
* **Growth Behavior**: Linear with database size (Unbounded RAM payload).
* **Worst-Case Scenario**: `generate_single_snapshot()` queries all `Customer`, `Product`, `Invoice`, and `InvoiceLine` records belonging to an organization into unpaginated Python memory lists. For large organizations, this constructs multi-hundred-megabyte JSON structures and openpyxl workbooks entirely in RAM, causing worker OOM crashes.
* **Billing Impact**: High RAM consumption on OCI compute instances and elevated Read IOPS on OCI PostgreSQL.
* **Existing Protection**: 15 MB combined email attachment size check BEFORE sending email, but memory payload is already fully allocated in RAM before the check.
* **Recommended Fix**: Use chunked database iterators (`QuerySet.iterator()`) and stream ZIP/Excel creation to disk/response instead of holding full datasets in memory.

---

### P1-2: Complete Absence of Rate Limiting Across All Endpoints
* **Severity**: **P1**
* **Exact Location**: `apps/authentication/views.py:75`, `apps/authentication/views.py:131`, `apps/authentication/views.py:309`, `apps/billing/views.py:537`, `apps/settings_app/views.py:411`
* **Trigger**: Automated HTTP requests to Login, Signup, Forgot Password, Resend Verification, Invoice Mail, or Export endpoints.
* **Resource Affected**: CPU / RAM / Database / Brevo SMTP API Quota.
* **Growth Behavior**: Multiplicative / Unbounded.
* **Worst-Case Scenario**: `django-ratelimit` is installed in `requirements.txt` and `INSTALLED_APPS`, but zero `@ratelimit` decorators are applied to any view. An attacker or client script can flood `/forgot-password/` (exhausting Brevo SMTP API quota), `/login/` (causing DB password check CPU load), or `/invoices/<uuid>/mail/` (spawning background threads).
* **Billing Impact**: Rapid exhaustion of Brevo SMTP email API credits (usage-based billing) and elevated OCI compute usage.
* **Existing Protection**: `django-ratelimit` installed in settings, but NOT applied to any views.
* **Recommended Fix**: Apply `@ratelimit` decorators to authentication, email sending, PDF rendering, and data export endpoints.

---

### P1-3: Unrestricted File Upload Size & Decompression Bomb Exposure
* **Severity**: **P1**
* **Exact Location**: `apps/organization/forms.py:65`, `apps/organization/models.py:42-60`, `apps/settings_app/views.py:865`
* **Trigger**: Uploading logo, signature, letterhead, QR code images, or Excel backup files.
* **Resource Affected**: RAM / Disk / Cloudinary Storage.
* **Growth Behavior**: Unbounded.
* **Worst-Case Scenario**: No maximum file size validation exists in forms or models for image uploads. Uploading multi-megabyte image files or crafted PNG decompression bombs causes Pillow or openpyxl to consume gigabytes of RAM during parsing, crashing the Gunicorn worker.
* **Billing Impact**: Increased Cloudinary media storage costs and server RAM exhaustion.
* **Existing Protection**: None.
* **Recommended Fix**: Enforce strict file size limits (e.g. 2 MB max for images, 10 MB max for Excel) in Django forms and configure `PIL.Image.MAX_IMAGE_PIXELS`.

---

### P1-4: Unbounded Invoice Line Item Submission
* **Severity**: **P1**
* **Exact Location**: `apps/billing/views.py:197`, `apps/billing/forms.py:35`
* **Trigger**: Submitting an invoice form with an arbitrarily large number of line items (`lines-TOTAL_FORMS = 1000+`).
* **Resource Affected**: CPU / RAM / Database.
* **Growth Behavior**: Linear to Multiplicative.
* **Worst-Case Scenario**: Invoice formset accepts any number of lines submitted in POST data. An invoice with 1,000+ lines forces WeasyPrint to attempt rendering a multi-page PDF document, causing worker timeout (60s) and high RAM usage.
* **Billing Impact**: Excessive CPU/RAM consumption per request.
* **Existing Protection**: None.
* **Recommended Fix**: Enforce a hard maximum limit on line items per invoice (e.g. max 100 lines per invoice) in `InvoiceForm`.

---

### P2-1: Unbounded Growth of Audit and Backup Log Tables
* **Severity**: **P2**
* **Exact Location**: `apps/settings_app/models.py:120`, `apps/settings_app/models.py:165`
* **Trigger**: Routine backup executions and data management actions creating `OrganizationBackupLog` and `DataManagementAuditLog` records.
* **Resource Affected**: Database Storage / Index Space.
* **Growth Behavior**: Linear with time.
* **Worst-Case Scenario**: Unlike `Notification` (which has an inline 300-count cap), backup and audit logs accumulate rows indefinitely, steadily increasing database storage requirements and index maintenance overhead.
* **Billing Impact**: Gradual long-term increase in OCI PostgreSQL database storage costs.
* **Existing Protection**: None.
* **Recommended Fix**: Implement a cron cleanup command to prune backup/audit log entries older than 180 days.

---

### P2-2: Gunicorn Configuration Discrepancy Between Procfile and render.yaml
* **Severity**: **P2**
* **Exact Location**: `Procfile:1`, `render.yaml:13`
* **Trigger**: Deployment utilizing `render.yaml` startCommand instead of `Procfile`.
* **Resource Affected**: Worker Throughput / Concurrency.
* **Growth Behavior**: Fixed Constraint.
* **Worst-Case Scenario**: `Procfile` specifies `--workers 4 --threads 2 --timeout 60`, but `render.yaml` uses `gunicorn core.wsgi:application` (defaulting to 1 worker, 1 thread). Deploying via `render.yaml` restricts the entire application to 1 single-threaded worker, allowing any single slow request to freeze the entire application.
* **Billing Impact**: Severe application throughput bottleneck.
* **Existing Protection**: None.
* **Recommended Fix**: Align `render.yaml` startCommand to explicitly specify `--workers 4 --threads 2 --timeout 60`.

---

### P3-1: Local Log File Rotation Writing to Container Storage
* **Severity**: **P3**
* **Exact Location**: `core/settings/base.py:368-378`
* **Trigger**: Application logging to `logs/advance_billing.log` and `logs/errors.log`.
* **Resource Affected**: Local Disk.
* **Growth Behavior**: Bounded (Capped at 100 MB total).
* **Worst-Case Scenario**: Writing log files to local disk inside containerized environments can fill ephemeral container storage or be lost on restart.
* **Billing Impact**: Negligible (100 MB limit).
* **Existing Protection**: `RotatingFileHandler` with `maxBytes=10MB` and `backupCount=5`.
* **Recommended Fix**: Configure logging handlers to output to `stdout` / `stderr` in production for cloud log driver collection.

---

### P3-2: In-Memory LocMemCache Backend in Production
* **Severity**: **P3**
* **Exact Location**: `core/settings/production.py:120-125`
* **Trigger**: Cache framework usage in production.
* **Resource Affected**: Server RAM.
* **Growth Behavior**: Bounded by process memory.
* **Worst-Case Scenario**: `LocMemCache` isolates cache memory per worker process. In multi-worker deployments, rate-limiting counters or cached fragments are not shared across workers.
* **Billing Impact**: None.
* **Existing Protection**: Comment advising Redis upgrade when scaling.
* **Recommended Fix**: Upgrade to Redis (`django-redis`) when scaling beyond 1 worker.

---

## 19. Executive Summary & Top Rankings

### Executive Summary: **NEEDS ATTENTION**
The Advance Billing codebase contains solid business logic, strict GST calculations, and proper ORM organization scoping. However, it currently contains **critical resource amplification risks (P0 & P1)** — primarily around **un-bounded background thread creation**, **synchronous WeasyPrint CPU/RAM saturation**, **un-ratelimited authentication and API endpoints**, and **un-paginated in-memory data exports**. These issues must be addressed before production deployment on Oracle Cloud Infrastructure to prevent severe unexpected billing and service instability.

### Top 10 Cost Risks
1. **Unbounded Background Daemon Threads on Invoice Issue** (Spawns concurrent WeasyPrint renders, spiking OCI CPU/RAM & autoscaling).
2. **Brevo SMTP API Quota Exhaustion** (Un-ratelimited email sending and backup endpoints consuming paid API credits).
3. **Synchronous WeasyPrint CPU Saturation** (Un-ratelimited PDF previews driving 100% OCI compute core utilization).
4. **In-Memory Data Export RAM Spikes** (Full database table loads into RAM during exports, requiring oversized OCI VM shapes).
5. **Unrestricted Image Uploads** (High-resolution image uploads inflating Cloudinary media storage charges).
6. **Un-ratelimited Authentication Endpoints** (Credential stuffing and brute force attacks driving database CPU load).
7. **Unbounded Line Item Invoice Submissions** (Heavy multi-page PDF layout generation driving prolonged CPU consumption).
8. **Un-ratelimited Manual Backup Mail Trigger** (Instant backup POST endpoint generating dual attachments & SMTP sends per click).
9. **Un-archived Historical Database Growth** (Continuous table growth increasing OCI Managed DB storage footprint).
10. **Un-pruned Audit Log Accumulation** (Indefinite growth of backup and audit log tables).

### Top 10 Resource Exhaustion Risks
1. **Gunicorn Worker Memory Exhaustion (OOM)** — Caused by multiple concurrent WeasyPrint PDF renders.
2. **Server CPU Core Saturation** — Caused by synchronous WeasyPrint HTML/CSS layout calculations.
3. **Python Process Thread Exhaustion** — Caused by unbounded `threading.Thread` spawning on invoice issuing.
4. **Server Memory (RAM) Exhaustion** — Caused by un-paginated DB queries in `backup_service.py`.
5. **Brevo SMTP Connection Timeout / Lockup** — Caused by synchronous email dispatch during backup runs.
6. **Pillow Decompression Bomb Memory Saturation** — Caused by unrestricted image upload pixel dimensions.
7. **Single-Worker Throughput Lockup** — Caused by unflagged `render.yaml` startCommand running 1 worker.
8. **Gunicorn Request Worker Timeout (60s SIGKILL)** — Caused by rendering extremely large line-item PDFs.
9. **Database Connection Pool Saturation** — Caused by multiple un-pooled background threads querying DB.
10. **Database Storage Exhaustion** — Caused by un-pruned historical log tables over extended runtime.

---

## 20. Production Guardrails & Required Action Plan

### Application-Level Guardrails
* Apply `@ratelimit` decorators to `/login/`, `/signup/`, `/forgot-password/`, `/invoices/<uuid>/pdf/`, `/settings/invoice-design/preview/`, `/invoices/<uuid>/mail/`, and `/settings/data/export/`.
* Enforce a hard maximum of **100 line items** per invoice in `InvoiceForm`.
* Enforce maximum file size validation (**2 MB max** for images, **10 MB max** for Excel backups) and set `PIL.Image.MAX_IMAGE_PIXELS = 10_000_000`.
* Cache rendered PDF bytes for issued invoices to eliminate redundant WeasyPrint compilations.

### Worker & Background Task Guardrails
* Replace `threading.Thread` in `InvoiceEmailService.send_invoice_email_async()` with a bounded worker pool or task queue (e.g. Celery / Redis / RQ).
* Add `--max-requests 1000 --max-requests-jitter 50` to Gunicorn command line to recycle worker processes and eliminate C-extension memory fragmentation.
* Align `render.yaml` startCommand with `Procfile`: `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 60`.

### Database & Storage Guardrails
* Refactor `OrganizationBackupService.generate_single_snapshot()` to stream database records via `iterator()` rather than loading all rows into RAM.
* Add a management command (`cleanup_audit_logs`) to delete `OrganizationBackupLog` and `DataManagementAuditLog` entries older than 180 days.

### OCI Infrastructure Guardrails (To Verify in OCI Console)
* **Compute Instance Pools**: Set explicit **Maximum Instance Count** ceiling on OCI Instance Pool Autoscaling.
* **Autonomous Database**: Cap maximum ECPU Auto Scaling multiplier on OCI Database.
* **Load Balancer**: Configure request timeout (60s) and rate-limiting rules on OCI Flexible Load Balancer.

---

### Audit Verification Statement
This audit was performed strictly in **READ-ONLY** mode. Zero workspace files, database records, environment configurations, or infrastructure assets were modified during this audit.
