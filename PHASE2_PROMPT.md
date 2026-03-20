PROJECT: Cloud Workload Impact Monitor — Phase 2 (Azure Resource Discovery)
=========================================================================

CONTEXT
-------
We have a working cloud status monitor (Python, Flask, APScheduler) that:
- Polls Azure RSS, GCP incidents.json, OCI Statuspage API, Cloudflare Statuspage API
- Shows a Service × Region matrix per provider (like Azure status page)
- Runs locally and in Docker
- Code is at: d:/outskill/download_detector/

EXISTING FILES
--------------
src/download_detector/
  models.py          — StatusEvent, Provider, Severity
  store.py           — in-memory StatusStore
  config.py          — loads config/services.yaml + DD_* env vars
  scheduler.py       — APScheduler background polling
  collectors/        — azure.py, gcp.py, oci.py, cloudflare.py
  filters/region.py  — USA region allowlists
  ui/web.py          — Flask app + single-file HTML/CSS/JS UI
  ui/terminal.py     — Rich terminal dashboard
config/services.yaml
Dockerfile / docker-compose.yml

WHAT TO BUILD NEXT — Phase 2
-----------------------------
Goal: Tell the user whether a cloud outage actually impacts their workloads.

The user has ~70 Azure subscriptions across multiple regions (USA).

1. RESOURCE INVENTORY MODULE  (src/download_detector/inventory/)
   ├── base.py         — abstract BaseInventoryCollector
   ├── azure.py        — uses Azure Resource Graph API
   │     Query: resources | project subscriptionId, type, location
   │     Auth:  AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID
   │             (Service Principal with Reader role on all subscriptions)
   │     SDK:   azure-mgmt-resourcegraph  (pip package)
   │     Result: dict[subscription_id, list[ResourceRecord]]
   │     Refresh: every 6 hours (resources change slowly)
   ├── gcp.py          — Cloud Asset Inventory API (future)
   └── oci.py          — OCI Resource Search API (future)

2. SUBSCRIPTION CONFIG  (config/subscriptions.yaml)
   Seed file — user lists their subscription IDs + friendly names:
     subscriptions:
       - id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
         name: prod-payments
         regions: [East US, East US 2]
         tags: {env: prod, team: payments}
       - id: ...
   Regions field is optional — if omitted, auto-detected from Resource Graph.

3. RESOURCE RECORD MODEL  (add to models.py)
   class ResourceRecord(BaseModel):
     subscription_id: str
     subscription_name: str
     resource_type: str        # e.g. "microsoft.storage/storageaccounts"
     service_name: str         # normalized friendly name e.g. "Azure Storage"
     location: str             # Azure region e.g. "eastus" -> normalize to "East US"
     tags: dict[str, str]

   SERVICE_TYPE_MAP: dict[str, str]  — maps Azure resource type -> status page service name
     "microsoft.storage/storageaccounts"              -> "Azure Storage"
     "microsoft.compute/virtualmachines"              -> "Azure Virtual Machines"
     "microsoft.containerservice/managedclusters"     -> "Azure Kubernetes Service"
     "microsoft.sql/servers"                          -> "Azure SQL Database"
     "microsoft.keyvault/vaults"                      -> "Azure Key Vault"
     "microsoft.network/virtualnetworks"              -> "Azure Virtual Network"
     "microsoft.web/sites"                            -> "Azure App Service"
     "microsoft.cache/redis"                          -> "Azure Cache for Redis"
     "microsoft.eventhub/namespaces"                  -> "Azure Event Hubs"
     "microsoft.servicebus/namespaces"                -> "Azure Service Bus"
     "microsoft.insights/components"                  -> "Azure Monitor"
     "microsoft.cognitiveservices/accounts"           -> "Azure AI Services"
     ... (extend as needed)

4. IMPACT ENGINE  (src/download_detector/impact.py)
   class ImpactResult(BaseModel):
     subscription_id: str
     subscription_name: str
     region: str
     is_impacted: bool
     affected_incidents: list[StatusEvent]
     affected_services: list[str]

   def calculate_impact(
       incidents: list[StatusEvent],
       inventory: dict[str, list[ResourceRecord]]
   ) -> list[ImpactResult]:
     For each subscription:
       For each active incident:
         If incident.affected_services intersects subscription.services
         AND incident.affected_regions intersects subscription.regions:
           -> IMPACTED

5. NEW API ENDPOINTS  (add to ui/web.py)
   GET /api/workloads/impact
     Returns: list[ImpactResult] — all subscriptions with impact status
   GET /api/inventory
     Returns: resource counts per subscription (for debug/visibility)
   GET /api/demo/workloads   — demo data for 10 sample subscriptions

6. UI CHANGES  (ui/web.py INDEX_HTML)
   Add a 5th tab: "My Workloads" (after Cloudflare tab)

   Tab content:
     a) Summary banner: "X of 70 workloads impacted across Y providers"
        or green "All workloads operational"

     b) Table columns:
        Workload (subscription name) | Provider | Region | Status | Affected Services | Details
        - Status: IMPACTED / OK
        - Sortable by status (impacted first)
        - Filterable: [All] [Impacted only]

     c) Click row -> detail panel showing:
        - Which incidents are hitting this workload
        - Which resource types are affected
        - Link to Azure Portal subscription view

   Also on provider tabs:
     Incident banners get a tag:
       [IMPACTS YOUR WORKLOADS]  or  [Not in your workload]

7. CONFIG ADDITIONS  (config.py AppConfig)
   inventory_refresh_hours: int = 6
   azure_tenant_id: str = ""      # also from env DD_AZURE_TENANT_ID
   azure_client_id: str = ""      # also from env DD_AZURE_CLIENT_ID
   azure_client_secret: str = ""  # also from env DD_AZURE_CLIENT_SECRET

8. SCHEDULER ADDITIONS  (scheduler.py)
   Add inventory refresh job — runs every 6h:
     scheduler.add_job(refresh_inventory, IntervalTrigger(hours=6), ...)
   Run once on startup before showing UI.

NEW DEPENDENCIES TO ADD TO pyproject.toml:
  azure-mgmt-resourcegraph>=8.0
  azure-identity>=1.15
  azure-mgmt-subscription>=3.1

PHASE A SCOPE (build this first)
---------------------------------
- Azure only
- Resource Graph auto-discovery across all subscriptions in the tenant
- Impact calculation: service match + region match
- "My Workloads" tab in UI with impacted/ok per subscription
- Demo mode: 10 fake subscriptions with realistic resource types

PHASE B (later)
---------------
- GCP Cloud Asset Inventory
- OCI Resource Search
- Tag-based workload grouping (workload= tag)
- Email/webhook alerts when a workload is impacted
- Historical impact log

CONSTRAINTS
-----------
- Keep existing architecture (no database, in-memory store)
- No breaking changes to existing collector/UI code
- All secrets via environment variables (never in code or yaml)
- Docker: secrets passed as env vars, not baked into image
- Python 3.11 compatible (not 3.12+)
- Single-file HTML UI (no npm/webpack/React — vanilla JS only)
