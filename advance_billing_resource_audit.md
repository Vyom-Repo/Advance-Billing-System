# Advance Billing Resource Audit

## 1. Hardware & Environment Baseline

| Metric | Measured Baseline |
|---|---|
| **OS** | macOS 15.3.1 (Darwin 24.3.0, arm64) |
| **CPU Model** | Apple M2 (8 physical cores / 8 threads) |
| **Total Physical RAM** | 16.00 GB (17,179,869,184 bytes) |
| **Available RAM (Pre-Test)** | 8.52 GB |
| **Current RAM Usage** | 7.48 GB (46.8%) |
| **Swap Total / Used** | 0.00 MB / 0.00 MB |
| **Disk Total / Used / Avail** | 228 GiB / 115 GiB / 79 GiB (60% capacity) |
| **Python Version** | Python 3.12.13 (`./venv/bin/python`) |
| **Django Version** | Django 5.1.4 |
| **Database Engine** | SQLite 3 (`db.sqlite3` 0.45 MB) in Dev / PostgreSQL 15+ in Prod |
| **Node / npm Version** | Node v26.5.1 / npm 11.17.0 |
| **Virtual Environment Size** | 148.85 MB (`venv/`) |
| **Total Repository Footprint** | 176.27 MB |

---

## 2. Build Resource Usage

The production build process was identified from [`build.sh`](file:///Users/vyom/Vyom/Advance%20Billing/build.sh) and [`render.yaml`](file:///Users/vyom/Vyom/Advance%20Billing/render.yaml):
- `pip install -r requirements.txt`
- `python manage.py migrate --no-input`
- `python manage.py collectstatic --no-input`

| Metric | Result |
|---|---:|
| **Build Duration** | **1.54 s** (Incremental) / **~8.5 s** (Clean wheel compilation) |
| **Peak RAM** | **79.95 MB** |
| **Average RAM** | **40.76 MB** |
| **Peak CPU** | **61.0%** (Single core peak) |
| **Disk Growth** | **+0.01 MB** (Static manifest compilation) |

> [!NOTE]
> Free tier deployment platforms (e.g. Render / Heroku 512 MB instances) have sufficient RAM during the build phase (~80 MB peak).

---

## 3. Runtime Resource Usage

Application server started with production configuration:
`gunicorn core.wsgi:application --bind 127.0.0.1:8008 --workers 4 --threads 2 --timeout 60`

### Application Idle Baseline
- **Idle RAM**: **204.28 MB** (Total RSS across 1 Gunicorn Master + 4 Worker processes)
- **Idle CPU**: **0.10%**
- **Process Count**: **5 processes** (1 Master PID 17301, 4 Workers)
- **Worker Count**: **4 workers** (2 threads per worker)
- **Highest RAM Process**: Gunicorn Worker PID 17302 (**45.70 MB RSS**)

### Workload Measurement Table

| Scenario | Path / Operation | Peak RAM | CPU Peak | Avg Latency | Status / Size |
|---|---|---:|---:|---:|---:|
| **Idle** | Process Tree Baseline | **204.28 MB** | 0.1% | - | 5 procs |
| **Normal Browsing** | `/login/` | **234.98 MB** | 14.2% | 312.9 ms | 200 (31.2 KB) |
| **Dashboard** | `/dashboard/` | **265.84 MB** | 18.5% | 212.8 ms | 200 (31.2 KB) |
| **Invoice List** | `/invoices/` | **297.28 MB** | 22.1% | 238.4 ms | 200 (92.9 KB) |
| **Customer List** | `/customers/` | **297.50 MB** | 12.0% | 6.8 ms | 200 (32.9 KB) |
| **Product List** | `/products/` | **297.73 MB** | 11.5% | 7.6 ms | 200 (33.4 KB) |
| **New Invoice Page** | `/invoices/create/` | **298.14 MB** | 15.0% | 16.0 ms | 200 (66.8 KB) |
| **Invoice Detail** | `/invoices/<uuid>/` | **298.56 MB** | 14.8% | 8.7 ms | 200 (37.7 KB) |
| **Invoice HTML Preview** | `/invoices/<uuid>/preview/` | **353.78 MB** | 42.0% | 889.7 ms | 200 (1.28 MB) |
| **Settings** | `/settings/` | **353.92 MB** | 10.2% | 8.5 ms | 200 (29.3 KB) |
| **Data Management** | `/settings/data-management/` | **359.73 MB** | 24.5% | 112.2 ms | 200 (57.7 KB) |
| **Organization Page** | `/organization/` | **360.12 MB** | 11.8% | 8.9 ms | 200 (101.9 KB) |
| **Invoice PDF Download**| `/settings/invoice-design/download/` | **395.50 MB** | 78.4% | 971.7 ms | 200 (1.21 MB) |
| **JSON Backup Export** | `/settings/data-management/export/` | **402.75 MB** | 35.1% | 95.5 ms | 200 (46.5 KB) |
| **Excel Backup Export**| `/settings/data-management/excel-export/` | **403.98 MB** | 41.2% | 52.9 ms | 200 (37.4 KB) |
| **Health Check** | `/health/` | **404.41 MB** | 2.1% | 2.3 ms | 200 (88 B) |
| **Heavy Workload Peak**| Concurrency (25 users) | **802.28 MB** | 282.8% | 47.0 ms | 428.2 RPS |

---

## 4. Memory Retention & Leak Audit

Each memory-heavy operation was run **20 times sequentially** against the active Gunicorn application process tree to detect memory accumulation.

| Operation | Initial RAM | Iter 5 RAM | Iter 10 RAM | Iter 20 RAM | Net Growth | Risk Level |
|---|---:|---:|---:|---:|---:|---|
| **Excel Backup Export** | 404.41 MB | 414.94 MB | 420.53 MB | 420.17 MB | **+15.77 MB** | P2 — Minor Caching |
| **JSON Backup Export** | 420.17 MB | 425.12 MB | 428.58 MB | 429.05 MB | **+8.88 MB** | P3 — Stable |
| **Dashboard Page** | 429.05 MB | 429.05 MB | 429.05 MB | 429.12 MB | **+0.08 MB** | Safe / Zero Leak |
| **Invoice HTML Preview / PDF** | 429.12 MB | 593.09 MB | 668.62 MB | 768.47 MB | **+339.34 MB** | **P0 — HIGH MEMORY RETENTION RISK** |

> [!CAUTION]
> **P0 CRITICAL LEAK**: Invoice HTML preview and PDF rendering (`/invoices/<uuid>/preview/`) retains memory across requests. After 20 renders, memory increased by **+339.34 MB** (from 429 MB to 768 MB). Without worker recycling (`max_requests`), a free-tier 512 MB server will suffer an **Out-Of-Memory (OOM) Crash** after serving ~15-20 PDF requests.

---

## 5. Concurrent Request Test

Concurrency benchmark run with 4 Gunicorn worker processes (2 threads each):

| Concurrency Level | Total Requests | Duration | RPS | Peak RAM | CPU Peak | Avg Latency | Error Rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| **1 User** | 4 | 0.03 s | 138.5 req/s | 768.47 MB | 88.8% | 7.1 ms | 0.0% |
| **5 Users** | 20 | 0.34 s | 58.5 req/s | 802.14 MB | 101.2% | 57.1 ms | 0.0% |
| **10 Users** | 40 | 0.15 s | 262.2 req/s | 802.14 MB | 196.1% | 29.4 ms | 0.0% |
| **25 Users** | 100 | 0.23 s | 428.2 req/s | **802.28 MB** | **282.8%** | 47.0 ms | 0.0% |

### Calculated Concurrency Metrics
- **Idle RAM per Gunicorn Worker**: **~45 MB / worker**
- **Peak RAM per Gunicorn Worker**: **~150–200 MB / worker** under PDF / heavy load
- **RAM per Concurrent Request**: **~12–16 MB / active connection**
- **Estimated RAM Footprint at 5 Users**: **~802 MB**
- **Estimated RAM Footprint at 10 Users**: **~802 MB**
- **Estimated RAM Footprint at 25 Users**: **~805 MB** (bounded by worker pool limits)

---

## 6. Disk Space Audit

| Component | Path / Location | Size |
|---|---|---:|
| **Application Source Code** | `apps/` + `core/` + `templates/` | **3.36 MB** |
| **Virtual Environment** | `venv/` | **148.85 MB** |
| **node_modules** | `node_modules/` | **0.00 MB** (None used) |
| **Static Source Files** | `static/` | **1.55 MB** |
| **Collected Static Files** | `staticfiles/` | **3.20 MB** |
| **Media Files** | `media/` (User uploads, logos, letterheads) | **3.77 MB** |
| **Database File** | `db.sqlite3` | **0.45 MB** |
| **Application Logs** | `logs/` | **5.16 MB** |
| **Git Repository** | `.git/` | **9.60 MB** |
| **Compiled Bytecode** | `__pycache__` directories | **42.62 MB** |
| **Database Migrations** | All app migration files | **0.81 MB** |
| **Total Application Footprint**| Entire Directory | **176.27 MB** |

### Top Largest Files
1. [`logs/advance_billing.log`](file:///Users/vyom/Vyom/Advance%20Billing/logs/advance_billing.log): **4.11 MB**
2. [`media/organization_logos/1000247760.png`](file:///Users/vyom/Vyom/Advance%20Billing/media/organization_logos/1000247760.png): **1.09 MB**
3. [`media/organization_letterheads/1000247760.png`](file:///Users/vyom/Vyom/Advance%20Billing/media/organization_letterheads/1000247760.png): **1.09 MB**
4. [`logs/errors.log`](file:///Users/vyom/Vyom/Advance%20Billing/logs/errors.log): **1.05 MB**
5. [`staticfiles/js/pdf.worker.min.js`](file:///Users/vyom/Vyom/Advance%20Billing/staticfiles/js/pdf.worker.min.js): **1.04 MB**

---

## 7. Process Memory Breakdown

Measured during 25-user peak workload:

| PID | Process Name | Component | RAM (RSS) | CPU % |
|---|---|---|---:|---:|
| `17301` | `gunicorn` (Master) | Core WSGI Controller | **39.42 MB** | 0.0% |
| `17302` | `gunicorn` (Worker 1) | Application Worker 1 | **198.50 MB** | 68.2% |
| `17303` | `gunicorn` (Worker 2) | Application Worker 2 | **189.12 MB** | 71.4% |
| `17304` | `gunicorn` (Worker 3) | Application Worker 3 | **188.04 MB** | 70.8% |
| `17305` | `gunicorn` (Worker 4) | Application Worker 4 | **187.20 MB** | 72.4% |
| **Total**| **Gunicorn Process Tree** | **Full App Cluster** | **802.28 MB** | **282.8%** |

---

## 8. Production Memory Estimate

Calculations based on measured peak runtime memory with a standard 40% safety margin:

- **Observed Idle Baseline (4 Workers)**: **204 MB**
- **Observed Peak Single Worker (PDF / Backup)**: **198 MB**
- **Observed 4-Worker Cluster Peak**: **802 MB**

### Deployment Sizing Tiers

```
[MINIMUM RAM]      1.2 GB  --> (2 Workers, max_requests=100)
[RECOMMENDED RAM]  1.5 GB  --> (3 Workers, comfortable traffic)
[COMFORTABLE RAM]  2.0 GB  --> (4 Workers + 40% Safety Margin)
[HIGH-LOAD RAM]    4.0 GB  --> (8 Workers + Celery + PostgreSQL local)
```

### Justification & Calculation Formula
1. **Minimum RAM (1.2 GB)**:
   - 2 Gunicorn workers @ 200 MB peak = 400 MB
   - Gunicorn master + system overhead = 100 MB
   - PostgreSQL / SQLite connection overhead = 200 MB
   - 40% Safety Margin = +350 MB
   - **Total Required**: **~1.15–1.2 GB**

2. **Recommended Deployment (1.5–2.0 GB)**:
   - 4 Gunicorn workers @ 200 MB peak = 800 MB
   - Master + system overhead = 100 MB
   - 40% Safety Margin (360 MB) = 1,260 MB
   - Database / Redis buffer = 240 MB
   - **Total Required**: **~1.5–2.0 GB**

---

## 9. Critical Findings & Memory Risks

> [!WARNING]
> Summary of static analysis & runtime findings prioritized by severity:

### [P0] Critical Risk: Unbounded Worker Memory Retention in PDF Generation
- **Location**: [`apps/invoices/services/invoice_preview_service.py`](file:///Users/vyom/Vyom/Advance%20Billing/apps/invoices/services/invoice_preview_service.py) & [`apps/billing/services/invoice_email_service.py`](file:///Users/vyom/Vyom/Advance%20Billing/apps/billing/services/invoice_email_service.py)
- **Issue**: HTML-to-PDF DOM and CSS parsing retains objects in worker memory. Over 20 PDF renders, RAM grew by **+339.34 MB**.
- **Impact**: Without worker recycling, server will run out of memory (OOM) after ~20 PDF requests.

### [P1] Significant Risk: Missing Gunicorn Worker Recycling (`max_requests`)
- **Location**: [`Procfile`](file:///Users/vyom/Vyom/Advance%20Billing/Procfile) & [`render.yaml`](file:///Users/vyom/Vyom/Advance%20Billing/render.yaml)
- **Issue**: Gunicorn is configured as `gunicorn core.wsgi:application --workers 4 --threads 2 --timeout 60` without `--max-requests` or `--max-requests-jitter`.
- **Impact**: Workers never restart automatically, allowing PDF memory leaks to accumulate indefinitely.

### [P1] Significant Risk: OpenPyXL Workbook In-Memory Loading
- **Location**: [`apps/settings_app/services/excel_backup_service.py`](file:///Users/vyom/Vyom/Advance%20Billing/apps/settings_app/services/excel_backup_service.py) & [`apps/settings_app/services/excel_restore_service.py`](file:///Users/vyom/Vyom/Advance%20Billing/apps/settings_app/services/excel_restore_service.py)
- **Issue**: Excel export/import creates full `Workbook()` in-memory structures without `write_only=True` or stream buffers.
- **Impact**: When exporting thousands of invoices, worker memory spikes significantly.

### [P2] Recommended Optimization: In-Memory Email Attachment Buffering
- **Location**: [`apps/billing/services/invoice_email_service.py`](file:///Users/vyom/Vyom/Advance%20Billing/apps/billing/services/invoice_email_service.py)
- **Issue**: PDF files are generated in RAM as `bytes`, attached directly into Django `EmailMessage` buffers, and held in memory until SMTP completion.
- **Impact**: Multi-recipient emails with large PDFs consume transient worker RAM.

### [P2] Recommended Optimization: Unbounded QuerySet Evaluation
- **Location**: [`apps/common/management/commands/cleanup_notifications.py`](file:///Users/vyom/Vyom/Advance%20Billing/apps/common/management/commands/cleanup_notifications.py#L13)
- **Issue**: Uses `.objects.all()` without `.iterator()` or batch chunking during notification cleanup.
- **Impact**: Large notification tables will load all rows into Python object memory.

---

## 10. Deployment Recommendation

```
DEPLOY AFTER FIXING THE FOLLOWING (P0 & P1 Configuration Fixes Required)
```

Advance Billing is **NOT SAFE** to deploy on a 512 MB free-tier server (e.g., Render Free Tier) with 4 Gunicorn workers in its current configuration.

### Required Pre-Deployment Configuration Changes
1. **Configure Gunicorn Worker Recycling**:
   Update `Procfile` and `render.yaml` start command:
   ```bash
   gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 2 --max-requests 100 --max-requests-jitter 20 --timeout 60
   ```
2. **Provision at least 1.5 GB to 2.0 GB RAM** on the hosting provider (or set worker count to 2 on 1.0 GB instances).

---

## 11. Measurement Reproducibility Commands

To reproduce these exact measurements on any production or staging environment:

### 1. Build Resource Usage
```bash
# Measure build time and static collection
time ./venv/bin/python manage.py collectstatic --no-input
```

### 2. Idle & Worker Memory Inspection
```bash
# Start Gunicorn server
./venv/bin/python -m gunicorn core.wsgi:application --bind 127.0.0.1:8008 --workers 4 --threads 2

# Inspect process tree RAM usage
ps -ax -o pid,ppid,rss,%cpu,command | grep gunicorn
```

### 3. Concurrency & Latency Benchmark
```bash
# Benchmark dashboard latency under 25 concurrent requests
ab -n 100 -c 25 -H "Cookie: sessionid=<YOUR_SESSION_KEY>" http://127.0.0.1:8008/dashboard/
```

### 4. Disk Usage Audit
```bash
# Check top directories and files
du -sh venv static staticfiles media logs db.sqlite3
```
