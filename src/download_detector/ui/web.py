"""Flask web UI — Azure-style status page with matrix grid."""
from datetime import datetime, timedelta
from flask import Flask, jsonify, Response

from ..store import StatusStore
from ..models import Provider, Severity

# ── Demo data ─────────────────────────────────────────────────────────────────

def _demo_matrix(provider: str) -> dict:
    now = datetime.utcnow()

    _data = {
        "azure": {
            "services": ["Azure Storage", "Azure Virtual Machines", "Azure Kubernetes Service",
                         "Azure SQL Database", "Azure Active Directory", "Azure App Service",
                         "Azure Monitor", "Azure CDN"],
            "regions": ["East US", "East US 2", "West US", "West US 2", "Central US", "South Central US"],
            "incidents": [
                {
                    "id": "DEMO-AZ-001",
                    "title": "Azure Storage — Degraded Experience in East US",
                    "severity": "degraded",
                    "status": "investigating",
                    "affected_services": ["Azure Storage"],
                    "affected_regions": ["East US", "East US 2"],
                    "started_at": (now - timedelta(hours=2, minutes=15)).isoformat(),
                    "last_updated": (now - timedelta(minutes=18)).isoformat(),
                    "resolved_at": None,
                    "duration": "2h 15m",
                    "url": "https://status.azure.com",
                    "description": "We are investigating an issue impacting Azure Storage accounts in the East US region. Customers may experience intermittent failures when performing read/write operations. Mitigation is in progress.",
                    "is_resolved": False,
                },
                {
                    "id": "DEMO-AZ-002",
                    "title": "Azure SQL Database — Connectivity Issues in West US 2",
                    "severity": "outage",
                    "status": "identified",
                    "affected_services": ["Azure SQL Database"],
                    "affected_regions": ["West US 2"],
                    "started_at": (now - timedelta(minutes=45)).isoformat(),
                    "last_updated": (now - timedelta(minutes=5)).isoformat(),
                    "resolved_at": None,
                    "duration": "45m",
                    "url": "https://status.azure.com",
                    "description": "We have identified an issue causing connection failures to Azure SQL Database in West US 2. Root cause identified as a faulty networking device. Replacement is underway.",
                    "is_resolved": False,
                },
                {
                    "id": "DEMO-AZ-003",
                    "title": "Azure Monitor — Planned Maintenance",
                    "severity": "maintenance",
                    "status": "in_progress",
                    "affected_services": ["Azure Monitor"],
                    "affected_regions": ["Central US", "South Central US"],
                    "started_at": (now - timedelta(minutes=30)).isoformat(),
                    "last_updated": (now - timedelta(minutes=30)).isoformat(),
                    "resolved_at": None,
                    "duration": "30m",
                    "url": "https://status.azure.com",
                    "description": "Planned maintenance is being performed on Azure Monitor infrastructure. Alert processing may be delayed by up to 5 minutes. Expected completion in 1 hour.",
                    "is_resolved": False,
                },
            ],
        },
        "gcp": {
            "services": ["Cloud Run", "Cloud SQL", "Google Kubernetes Engine",
                         "Cloud Storage", "Vertex AI", "BigQuery", "Cloud Functions", "Cloud Pub/Sub"],
            "regions": ["us-east1", "us-east4", "us-central1", "us-west1", "us-west2", "us-south1"],
            "incidents": [
                {
                    "id": "DEMO-GCP-001",
                    "title": "Cloud Run — High Latency and Increased Error Rates",
                    "severity": "degraded",
                    "status": "investigating",
                    "affected_services": ["Cloud Run", "Cloud Functions"],
                    "affected_regions": ["us-central1", "us-east1"],
                    "started_at": (now - timedelta(hours=1, minutes=10)).isoformat(),
                    "last_updated": (now - timedelta(minutes=12)).isoformat(),
                    "resolved_at": None,
                    "duration": "1h 10m",
                    "url": "https://status.cloud.google.com",
                    "description": "We are investigating an issue with Cloud Run in us-central1 and us-east1. Some requests are experiencing elevated latency (p99 > 3s) and a subset of invocations are returning HTTP 500 errors.",
                    "is_resolved": False,
                },
                {
                    "id": "DEMO-GCP-002",
                    "title": "Cloud SQL — Major Outage in us-west1",
                    "severity": "critical",
                    "status": "identified",
                    "affected_services": ["Cloud SQL"],
                    "affected_regions": ["us-west1"],
                    "started_at": (now - timedelta(minutes=25)).isoformat(),
                    "last_updated": (now - timedelta(minutes=3)).isoformat(),
                    "resolved_at": None,
                    "duration": "25m",
                    "url": "https://status.cloud.google.com",
                    "description": "Cloud SQL instances in us-west1 are unavailable. New connections are failing and existing connections are being dropped. Engineers have identified the root cause and are working on restoration.",
                    "is_resolved": False,
                },
            ],
        },
        "oci": {
            "services": ["Compute", "Object Storage", "Kubernetes Engine (OKE)",
                         "Autonomous Database", "Networking", "Load Balancer"],
            "regions": ["US East (Ashburn)", "US West (Phoenix)", "US Midwest (Chicago)"],
            "incidents": [
                {
                    "id": "DEMO-OCI-001",
                    "title": "Object Storage — Intermittent Failures in US East (Ashburn)",
                    "severity": "degraded",
                    "status": "mitigating",
                    "affected_services": ["Object Storage"],
                    "affected_regions": ["US East (Ashburn)"],
                    "started_at": (now - timedelta(hours=3)).isoformat(),
                    "last_updated": (now - timedelta(minutes=22)).isoformat(),
                    "resolved_at": None,
                    "duration": "3h 0m",
                    "url": "https://ocistatus.oracle.com",
                    "description": "Some customers may experience intermittent errors when accessing Object Storage in the US East (Ashburn) region. Read operations are more impacted than writes. Mitigation is in progress.",
                    "is_resolved": False,
                },
            ],
        },
        "cloudflare": {
            "services": ["CDN / Cache", "DNS", "Workers", "Access", "R2 Storage", "Pages"],
            "regions": ["Ashburn, VA (IAD)", "Dallas, TX (DFW)", "Los Angeles, CA (LAX)",
                        "Chicago, IL (ORD)", "Atlanta, GA (ATL)", "New York, NY (EWR)"],
            "incidents": [
                {
                    "id": "DEMO-CF-001",
                    "title": "Workers — Elevated Error Rates in Eastern US",
                    "severity": "outage",
                    "status": "investigating",
                    "affected_services": ["Workers", "Pages"],
                    "affected_regions": ["Ashburn, VA (IAD)", "New York, NY (EWR)", "Atlanta, GA (ATL)"],
                    "started_at": (now - timedelta(minutes=55)).isoformat(),
                    "last_updated": (now - timedelta(minutes=8)).isoformat(),
                    "resolved_at": None,
                    "duration": "55m",
                    "url": "https://www.cloudflarestatus.com",
                    "description": "Cloudflare Workers are experiencing elevated error rates in Eastern US data centers. Approximately 15% of requests are failing with 5xx errors. We are investigating the root cause.",
                    "is_resolved": False,
                },
            ],
        },
    }

    p = _data.get(provider, {"services": [], "regions": [], "incidents": []})
    services = p["services"]
    regions  = p["regions"]
    incidents = p["incidents"]

    # Build matrix from incidents
    matrix: dict[str, dict] = {svc: {reg: {"status": "operational", "incidents": []} for reg in regions} for svc in services}
    for inc in incidents:
        for svc in inc["affected_services"]:
            if svc not in matrix:
                continue
            for reg in inc["affected_regions"]:
                if reg not in matrix[svc]:
                    continue
                cell = matrix[svc][reg]
                cell["incidents"].append(inc)
                sev_order = {"critical":0,"outage":1,"degraded":2,"maintenance":3,"operational":4}
                cur_o = sev_order.get(cell["status"], 4)
                new_o = sev_order.get(inc["severity"], 4)
                if new_o < cur_o:
                    cell["status"] = inc["severity"]

    sev_order = {"critical":0,"outage":1,"degraded":2,"maintenance":3,"operational":4}
    sorted_incidents = sorted(incidents, key=lambda i: sev_order.get(i["severity"], 4))
    worst = sorted_incidents[0]["severity"] if sorted_incidents else "operational"

    return {
        "provider": provider,
        "overall_status": worst,
        "active_count": len(incidents),
        "last_poll": now.isoformat(),
        "error": None,
        "services": services,
        "regions": regions,
        "matrix": matrix,
        "incidents": sorted_incidents,
        "_demo": True,
    }

SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.OUTAGE: 1,
    Severity.DEGRADED: 2,
    Severity.MAINTENANCE: 3,
    Severity.OPERATIONAL: 4,
}


def _worst_severity(severities: list[Severity]) -> Severity:
    if not severities:
        return Severity.OPERATIONAL
    return min(severities, key=lambda s: SEVERITY_ORDER[s])


def _serialize_event(e) -> dict:
    return {
        "id": e.incident_id,
        "title": e.title,
        "severity": e.severity.value,
        "status": e.status,
        "affected_services": e.affected_services,
        "affected_regions": e.affected_regions,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
        "last_updated": e.last_updated.isoformat() if e.last_updated else None,
        "duration": e.duration_str,
        "url": e.url,
        "description": e.description,
        "is_resolved": e.is_resolved,
    }


def create_app(store: StatusStore) -> Flask:
    app = Flask(__name__)

    @app.route("/api/summary")
    def api_summary():
        result = {}
        for provider in Provider:
            events = [e for e in store.get_by_provider(provider) if e.is_active]
            worst = _worst_severity([e.severity for e in events])
            last_poll = store.last_poll_time(provider)
            result[provider.value] = {
                "overall_status": worst.value,
                "active_count": len(events),
                "last_poll": last_poll.isoformat() if last_poll else None,
                "error": store.last_poll_error(provider),
            }
        return jsonify(result)

    @app.route("/api/matrix/<provider_name>")
    def api_matrix(provider_name: str):
        """Return service × region matrix for a provider."""
        try:
            provider = Provider(provider_name.lower())
        except ValueError:
            return jsonify({"error": f"Unknown provider: {provider_name}"}), 400

        events = [e for e in store.get_by_provider(provider) if e.is_active]

        # Collect all unique services and regions from active incidents
        all_services: list[str] = []
        all_regions: list[str] = []
        for event in events:
            for svc in (event.affected_services or []):
                if svc and svc not in all_services:
                    all_services.append(svc)
            for reg in (event.affected_regions or []):
                if reg and reg not in all_regions:
                    all_regions.append(reg)

        all_services.sort()
        all_regions.sort()

        # Build matrix: matrix[service][region] = {status, incidents[]}
        matrix: dict[str, dict[str, dict]] = {}
        for svc in all_services:
            matrix[svc] = {}
            for reg in all_regions:
                matrix[svc][reg] = {"status": "operational", "incidents": []}

        for event in events:
            svcs = event.affected_services or ["(unknown)"]
            regs = event.affected_regions or ["(global)"]
            ser = _serialize_event(event)
            for svc in svcs:
                if svc not in matrix:
                    continue
                for reg in regs:
                    if reg not in matrix[svc]:
                        continue
                    cell = matrix[svc][reg]
                    cell["incidents"].append(ser)
                    # Upgrade cell status to worst severity
                    cur = Severity(cell["status"]) if cell["status"] != "operational" else Severity.OPERATIONAL
                    cell["status"] = _worst_severity([cur, event.severity]).value

        # Build flat incidents list for the banner
        all_incidents = [_serialize_event(e) for e in
                         sorted(events, key=lambda e: SEVERITY_ORDER.get(e.severity, 9))]

        last_poll = store.last_poll_time(provider)
        overall = _worst_severity([e.severity for e in events]) if events else Severity.OPERATIONAL

        return jsonify({
            "provider": provider.value,
            "overall_status": overall.value,
            "active_count": len(events),
            "last_poll": last_poll.isoformat() if last_poll else None,
            "error": store.last_poll_error(provider),
            "services": all_services,
            "regions": all_regions,
            "matrix": matrix,
            "incidents": all_incidents,
        })

    @app.route("/api/demo/matrix/<provider_name>")
    def api_demo_matrix(provider_name: str):
        if provider_name.lower() not in [p.value for p in Provider]:
            return jsonify({"error": f"Unknown provider: {provider_name}"}), 400
        return jsonify(_demo_matrix(provider_name.lower()))

    @app.route("/api/demo/summary")
    def api_demo_summary():
        result = {}
        for p in Provider:
            data = _demo_matrix(p.value)
            result[p.value] = {
                "overall_status": data["overall_status"],
                "active_count": data["active_count"],
                "last_poll": data["last_poll"],
                "error": None,
            }
        return jsonify(result)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

    @app.route("/")
    def index():
        return Response(INDEX_HTML, mimetype="text/html")

    @app.route("/demo")
    def demo():
        return Response(INDEX_HTML.replace("const DEMO_MODE = false;", "const DEMO_MODE = true;"), mimetype="text/html")

    return app


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cloud Status Monitor</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --ms-blue:      #0078d4;
  --ms-blue-dark: #005a9e;
  --ms-blue-bg:   #eff6fc;
  --green:        #107c10;
  --green-light:  #dff6dd;
  --yellow:       #835b00;
  --yellow-light: #fff4ce;
  --orange:       #8a3200;
  --orange-light: #fce4d6;
  --red:          #8a0000;
  --red-light:    #fde7e9;
  --blue-info:    #004578;
  --blue-light:   #cfe4f6;
  --bg:           #ffffff;
  --bg-subtle:    #faf9f8;
  --bg-panel:     #f3f2f1;
  --border:       #edebe9;
  --border-dark:  #c8c6c4;
  --text:         #201f1e;
  --text-secondary: #605e5c;
  --text-muted:   #a19f9d;
  --radius:       4px;
  --shadow:       0 2px 4px rgba(0,0,0,.08), 0 0 1px rgba(0,0,0,.08);
  --shadow-panel: 2px 0 8px rgba(0,0,0,.12);
}

body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  font-size: 14px;
  color: var(--text);
  background: var(--bg);
  line-height: 1.5;
  min-height: 100vh;
}

/* ── Top bar ── */
.topbar {
  background: var(--ms-blue);
  color: white;
  padding: 0 32px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 200;
  transition: background .3s;
}
.topbar.theme-gcp         { background: #1a73e8; }
.topbar.theme-oci         { background: #c74634; }
.topbar.theme-cloudflare  { background: #f6821f; }

.topbar-brand { display: flex; align-items: center; gap: 10px; }
.topbar-brand svg { opacity: .9; }
.topbar-brand h1 { font-size: 15px; font-weight: 600; letter-spacing: -.2px; }
.topbar-brand span { opacity: .75; font-size: 13px; border-left: 1px solid rgba(255,255,255,.35); padding-left: 10px; margin-left: 2px; }
.topbar-meta { font-size: 12px; opacity: .9; display: flex; align-items: center; gap: 14px; }
.refresh-btn {
  background: rgba(255,255,255,.18);
  border: 1px solid rgba(255,255,255,.3);
  color: white;
  padding: 5px 11px;
  border-radius: var(--radius);
  font-size: 12px;
  cursor: pointer;
  display: flex; align-items: center; gap: 5px;
  transition: background .15s;
}
.refresh-btn:hover { background: rgba(255,255,255,.3); }
.refresh-btn.spinning svg { animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Demo banner ── */
.demo-banner {
  background: #fff4ce; border-bottom: 1px solid #ffb900;
  padding: 8px 32px;
  font-size: 12px; color: #835b00;
  display: flex; align-items: center; gap: 8px;
}
.demo-banner a { color: #0078d4; text-decoration: none; font-weight: 500; }
.demo-banner a:hover { text-decoration: underline; }

/* ── Provider tabs ── */
.provider-tabs {
  background: var(--bg);
  border-bottom: 1px solid var(--border-dark);
  padding: 0 32px;
  display: flex;
  overflow-x: auto;
  position: sticky;
  top: 45px;
  z-index: 100;
}
.ptab {
  display: flex; align-items: center; gap: 9px;
  padding: 0 22px;
  height: 52px;
  font-size: 13px; font-weight: 500;
  color: var(--text-secondary);
  border-bottom: 3px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
  background: none; border-top: none; border-left: none; border-right: none;
  transition: color .15s, background .15s, border-color .15s;
  position: relative;
}
.ptab:hover { background: #f8f8f8; }

/* Azure — Microsoft Blue */
.ptab-azure:hover   { color: #0078d4; background: #eff6fc; }
.ptab-azure.active  { color: #0078d4; border-bottom-color: #0078d4; font-weight: 600; background: #f7fbff; }
/* GCP — Google Blue */
.ptab-gcp:hover     { color: #4285f4; background: #f0f4ff; }
.ptab-gcp.active    { color: #4285f4; border-bottom-color: #4285f4; font-weight: 600; background: #f5f8ff; }
/* OCI — Oracle Red */
.ptab-oci:hover     { color: #c74634; background: #fff3f2; }
.ptab-oci.active    { color: #c74634; border-bottom-color: #c74634; font-weight: 600; background: #fff7f6; }
/* Cloudflare — Orange */
.ptab-cloudflare:hover  { color: #f6821f; background: #fff8f2; }
.ptab-cloudflare.active { color: #f6821f; border-bottom-color: #f6821f; font-weight: 600; background: #fffaf5; }

.ptab-logo {
  width: 18px; height: 18px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.ptab-logo img { width: 18px; height: 18px; object-fit: contain; }
.ptab-indicator { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ptab-count {
  font-size: 11px; font-weight: 600;
  background: var(--red-light); color: var(--red);
  border-radius: 10px; padding: 1px 7px;
  min-width: 20px; text-align: center;
}
.ptab-ok .ptab-count { display: none; }

/* ── Page body ── */
.page { display: flex; }
.main { flex: 1; overflow: auto; }

/* ── Incident banners ── */
.banners { padding: 16px 32px 0; }
.banner {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px 16px;
  border-radius: var(--radius);
  border-left: 4px solid;
  margin-bottom: 10px;
  cursor: pointer;
  transition: filter .15s;
}
.banner:hover { filter: brightness(.97); }
.banner-icon { font-size: 16px; margin-top: 1px; flex-shrink: 0; }
.banner-body { flex: 1; }
.banner-title { font-weight: 600; font-size: 13px; }
.banner-meta  { font-size: 12px; margin-top: 2px; }
.banner-arrow { color: var(--text-muted); font-size: 16px; align-self: center; }

.banner-critical { background: var(--red-light);    border-color: #a80000; }
.banner-critical .banner-title { color: var(--red); }
.banner-critical .banner-meta  { color: #8a0000cc; }
.banner-outage   { background: var(--orange-light);  border-color: #d83b01; }
.banner-outage .banner-title   { color: var(--orange); }
.banner-outage .banner-meta    { color: #8a3200cc; }
.banner-degraded { background: var(--yellow-light);  border-color: #ffb900; }
.banner-degraded .banner-title { color: var(--yellow); }
.banner-degraded .banner-meta  { color: #835b00cc; }
.banner-maintenance { background: var(--blue-light); border-color: var(--ms-blue); }
.banner-maintenance .banner-title { color: var(--blue-info); }
.banner-maintenance .banner-meta  { color: #004578cc; }

/* ── All clear ── */
.all-clear {
  display: flex; align-items: center; gap: 14px;
  padding: 20px 24px;
  background: var(--green-light);
  border: 1px solid #bad7ba;
  border-radius: var(--radius);
  margin: 20px 32px;
}
.all-clear-icon { font-size: 28px; }
.all-clear-title { font-size: 15px; font-weight: 600; color: var(--green); }
.all-clear-sub { font-size: 13px; color: #0e6e0e; margin-top: 2px; }

/* ── Section heading ── */
.section-head {
  padding: 20px 32px 10px;
  display: flex; align-items: center; justify-content: space-between;
}
.section-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .6px; }
.section-legend { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--text-secondary); }
.legend-item { display: flex; align-items: center; gap: 5px; }

/* ── Matrix ── */
.matrix-wrap { padding: 0 32px 32px; overflow-x: auto; }
.matrix {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid var(--border-dark);
  border-radius: 6px;
  overflow: hidden;
  box-shadow: var(--shadow);
  min-width: 600px;
}

.matrix thead tr { background: var(--bg-panel); }
.matrix th {
  padding: 10px 14px;
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .5px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-dark);
  white-space: nowrap;
  text-align: center;
}
.matrix th.service-col { text-align: left; min-width: 200px; }
.matrix th.region-col  { min-width: 90px; }

.matrix tbody tr { background: var(--bg); transition: background .1s; }
.matrix tbody tr:nth-child(even) { background: var(--bg-subtle); }
.matrix tbody tr:hover { background: var(--ms-blue-bg); }

.matrix td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.matrix tbody tr:last-child td { border-bottom: none; }
.matrix td.service-name {
  font-size: 13px; font-weight: 500;
  color: var(--text);
  border-right: 1px solid var(--border-dark);
  white-space: nowrap;
}
.matrix td.status-cell {
  text-align: center;
  cursor: default;
}
.matrix td.status-cell.has-incident { cursor: pointer; }
.matrix td.status-cell.has-incident:hover .status-icon { transform: scale(1.2); }
.status-icon { display: inline-flex; align-items: center; justify-content: center; transition: transform .15s; }

/* ── Status icons ── */
.icon-operational { color: var(--green); }
.icon-degraded    { color: #ffb900; }
.icon-outage      { color: #d83b01; }
.icon-critical    { color: #a80000; }
.icon-maintenance { color: var(--ms-blue); }

/* ── Cell tooltip ── */
.status-cell { position: relative; }
.cell-tip {
  display: none;
  position: absolute;
  bottom: calc(100% + 4px);
  left: 50%; transform: translateX(-50%);
  background: #323130;
  color: white;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 3px;
  white-space: nowrap;
  z-index: 50;
  pointer-events: none;
}
.cell-tip::after {
  content: '';
  position: absolute;
  top: 100%; left: 50%; transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: #323130;
}
.status-cell:hover .cell-tip { display: block; }

/* ── Detail panel ── */
.detail-panel {
  width: 420px;
  flex-shrink: 0;
  background: var(--bg);
  border-left: 1px solid var(--border-dark);
  box-shadow: -2px 0 8px rgba(0,0,0,.08);
  display: flex; flex-direction: column;
  position: sticky; top: 89px;
  height: calc(100vh - 89px);
  overflow: hidden;
  transform: translateX(420px);
  transition: transform .2s ease, width .2s ease;
  width: 0; overflow: hidden;
}
.detail-panel.open {
  transform: translateX(0);
  width: 420px;
  overflow: hidden;
}
.panel-header {
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-dark);
  padding: 16px 20px;
  display: flex; align-items: flex-start; justify-content: space-between; gap: 10px;
  flex-shrink: 0;
}
.panel-sev { margin-bottom: 6px; }
.panel-title { font-size: 14px; font-weight: 600; line-height: 1.4; color: var(--text); }
.panel-close {
  background: none; border: none;
  color: var(--text-muted); cursor: pointer;
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius);
  font-size: 16px; flex-shrink: 0;
  transition: background .1s, color .1s;
}
.panel-close:hover { background: var(--border); color: var(--text); }
.panel-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.panel-footer { padding: 16px 20px; border-top: 1px solid var(--border); flex-shrink: 0; }

.detail-section { display: flex; flex-direction: column; gap: 4px; }
.detail-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; color: var(--text-muted); }
.detail-value { font-size: 13px; color: var(--text); }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.tag {
  padding: 3px 10px; border-radius: 2px;
  font-size: 12px; background: var(--bg-panel);
  border: 1px solid var(--border-dark);
  color: var(--text-secondary);
}
.desc-box {
  background: var(--bg-subtle); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 12px;
  font-size: 13px; color: var(--text-secondary);
  line-height: 1.6; white-space: pre-wrap;
  max-height: 200px; overflow-y: auto;
}
.btn-primary {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius);
  background: var(--ms-blue); color: white;
  font-size: 13px; font-weight: 500;
  text-decoration: none; border: none; cursor: pointer;
  transition: background .15s;
}
.btn-primary:hover { background: var(--ms-blue-dark); }

/* ── Status pill ── */
.sev-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 2px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .4px;
}
.sev-operational { background: var(--green-light);   color: var(--green); }
.sev-degraded    { background: var(--yellow-light);  color: var(--yellow); }
.sev-outage      { background: var(--orange-light);  color: var(--orange); }
.sev-critical    { background: var(--red-light);     color: var(--red); }
.sev-maintenance { background: var(--blue-light);    color: var(--blue-info); }

/* ── Poll error ── */
.poll-error {
  margin: 0 32px 0;
  padding: 10px 14px;
  background: var(--yellow-light);
  border: 1px solid #ffb900;
  border-radius: var(--radius);
  font-size: 12px; color: var(--yellow);
  display: flex; align-items: center; gap: 8px;
}

/* ── Loading ── */
.loading { padding: 60px; text-align: center; color: var(--text-muted); }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-dark); border-radius: 3px; }

/* ── Responsive ── */
@media (max-width: 700px) {
  .topbar { padding: 10px 16px; }
  .provider-tabs { padding: 0 8px; }
  .banners, .section-head, .matrix-wrap { padding-left: 16px; padding-right: 16px; }
  .all-clear { margin: 16px; }
}
</style>
</head>
<body>

<!-- Top bar -->
<div class="topbar" id="topbar">
  <div class="topbar-brand">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
      <path d="M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 3a4 4 0 100 8 4 4 0 000-8z"/>
    </svg>
    <h1>Cloud Status Monitor</h1>
    <span>USA Regions</span>
  </div>
  <div class="topbar-meta">
    <span id="updated-text">Updating…</span>
    <button class="refresh-btn" id="refresh-btn" onclick="manualRefresh()">
      <svg id="refresh-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/>
        <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
      </svg>
      Refresh
    </button>
  </div>
</div>
<div id="demo-banner" style="display:none" class="demo-banner">
  🧪 <strong>Demo Mode</strong> — showing simulated incidents for preview.
  <a href="/">View live data →</a>
</div>

<!-- Provider tabs -->
<div class="provider-tabs" id="provider-tabs"></div>

<!-- Page -->
<div class="page">
  <div class="main" id="main">
    <div class="loading">Loading cloud status data…</div>
  </div>
  <div class="detail-panel" id="detail-panel">
    <div class="panel-header">
      <div style="flex:1">
        <div class="panel-sev" id="panel-sev"></div>
        <div class="panel-title" id="panel-title"></div>
      </div>
      <button class="panel-close" onclick="closePanel()" title="Close">✕</button>
    </div>
    <div class="panel-body" id="panel-body"></div>
    <div class="panel-footer" id="panel-footer"></div>
  </div>
</div>

<script>
const DEMO_MODE = false;

const PROVIDERS = ['azure', 'gcp', 'oci', 'cloudflare'];
const LABELS = { azure: 'Azure', gcp: 'GCP', oci: 'OCI', cloudflare: 'Cloudflare' };
const SEV_ORDER = { critical:0, outage:1, degraded:2, maintenance:3, operational:4 };

// Provider brand config
const BRAND = {
  azure:      { color: '#0078d4', topbar: '',               logo: '🔷' },
  gcp:        { color: '#4285f4', topbar: 'theme-gcp',      logo: '🔵' },
  oci:        { color: '#c74634', topbar: 'theme-oci',      logo: '🔴' },
  cloudflare: { color: '#f6821f', topbar: 'theme-cloudflare', logo: '🟠' },
};

let activeProvider = 'azure';
let summary = {};
let selectedId = null;

// ── Icons ───────────────────────────────────────────────────────────────────

const SVG = {
  ok: `<svg class="status-icon icon-operational" width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor" opacity=".15"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  degraded: `<svg class="status-icon icon-degraded" width="18" height="18" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" fill="currentColor" opacity=".15" stroke="currentColor" stroke-width="1.5"/><line x1="12" y1="9" x2="12" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="17" x2="12.01" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
  outage: `<svg class="status-icon icon-outage" width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor" opacity=".2" stroke="currentColor" stroke-width="1.5"/><line x1="12" y1="8" x2="12" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="16" x2="12.01" y2="16" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>`,
  critical: `<svg class="status-icon icon-critical" width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor" opacity=".2" stroke="currentColor" stroke-width="1.5"/><line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
  maintenance: `<svg class="status-icon icon-maintenance" width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor" opacity=".15"/><path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`,
};
const DOT_COLOR = { operational:'#107c10', degraded:'#ffb900', outage:'#d83b01', critical:'#a80000', maintenance:'#0078d4' };

function statusIcon(s) { return SVG[s] || SVG.ok; }

function sevPill(s) {
  const labels = { operational:'Operational', degraded:'Degraded', outage:'Partial Outage', critical:'Major Outage', maintenance:'Under Maintenance' };
  return `<span class="sev-pill sev-${s}">${statusIcon(s)} ${labels[s]||s}</span>`;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso) {
  if (!iso) return '—';
  const s = Math.floor((Date.now() - new Date(iso.endsWith('Z')?iso:iso+'Z')) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s/60)}m ago`;
  if (s < 86400) return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m ago`;
  return `${Math.floor(s/86400)}d ago`;
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso.endsWith('Z')?iso:iso+'Z').toLocaleString('en-US',{
    month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', timeZoneName:'short'
  });
}
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ── Summary / Tabs ───────────────────────────────────────────────────────────

async function loadSummary() {
  const url = DEMO_MODE ? '/api/demo/summary' : '/api/summary';
  const r = await fetch(url);
  summary = await r.json();
  renderTabs();
  document.getElementById('updated-text').textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

function renderTabs() {
  // Update topbar brand color
  const topbar = document.getElementById('topbar');
  topbar.className = 'topbar ' + (BRAND[activeProvider]?.topbar || '');

  document.getElementById('provider-tabs').innerHTML = PROVIDERS.map(p => {
    const s = summary[p] || {};
    const sev = s.overall_status || 'operational';
    const cnt = s.active_count || 0;
    const cntHtml = cnt > 0 ? `<span class="ptab-count">${cnt}</span>` : '';
    const brand = BRAND[p];
    return `<button class="ptab ptab-${p} ${p===activeProvider?'active':''} ${cnt===0?'ptab-ok':''}"
      onclick="switchProvider('${p}')">
      <span style="font-size:15px;line-height:1">${brand.logo}</span>
      <span class="ptab-indicator" style="background:${DOT_COLOR[sev]}"></span>
      ${LABELS[p]}${cntHtml}
    </button>`;
  }).join('');
}

// ── Switch provider ──────────────────────────────────────────────────────────

async function switchProvider(p) {
  activeProvider = p;
  selectedId = null;
  closePanel();
  renderTabs();
  await loadMatrix();
}

// ── Matrix view ──────────────────────────────────────────────────────────────

async function loadMatrix() {
  document.getElementById('main').innerHTML = '<div class="loading">Loading…</div>';
  try {
    const url = DEMO_MODE ? `/api/demo/matrix/${activeProvider}` : `/api/matrix/${activeProvider}`;
    const r = await fetch(url);
    const data = await r.json();
    renderMatrix(data);
  } catch(e) {
    document.getElementById('main').innerHTML = `<div class="poll-error" style="margin:24px 32px">Failed to load: ${esc(e.message)}</div>`;
  }
}

function renderMatrix(data) {
  const main = document.getElementById('main');
  let html = '';

  // Poll error
  if (data.error) {
    html += `<div class="poll-error" style="margin-top:16px">⚠ Last poll failed — showing cached data: ${esc(data.error)}</div>`;
  }

  // Incident banners
  const incidents = data.incidents || [];
  if (incidents.length) {
    html += '<div class="banners">';
    incidents.slice(0, 5).forEach(inc => {
      const cls = `banner-${inc.severity}`;
      const icon = { critical:'🔴', outage:'🟠', degraded:'🟡', maintenance:'🔵' }[inc.severity] || '⚠';
      const regions = (inc.affected_regions||[]).slice(0,3).join(', ');
      const extra = (inc.affected_regions||[]).length > 3 ? ` +${inc.affected_regions.length-3} more` : '';
      html += `<div class="banner ${cls}" onclick="showIncidentDetail(${JSON.stringify(JSON.stringify(inc))})">
        <span class="banner-icon">${icon}</span>
        <div class="banner-body">
          <div class="banner-title">${esc(inc.title)}</div>
          <div class="banner-meta">
            Started ${timeAgo(inc.started_at)} · ${inc.status}
            ${regions ? ` · ${esc(regions)}${esc(extra)}` : ''}
            ${inc.duration ? ` · Duration: ${inc.duration}` : ''}
          </div>
        </div>
        <span class="banner-arrow">›</span>
      </div>`;
    });
    if (incidents.length > 5) {
      html += `<div style="padding:8px 0;font-size:12px;color:var(--text-muted)">+ ${incidents.length - 5} more active incidents</div>`;
    }
    html += '</div>';
  } else {
    html += `<div class="all-clear">
      <span class="all-clear-icon">✅</span>
      <div>
        <div class="all-clear-title">All systems are operational</div>
        <div class="all-clear-sub">There are currently no active events in USA regions for ${LABELS[activeProvider]}.</div>
      </div>
    </div>`;
  }

  // Matrix section
  const services = data.services || [];
  const regions  = data.regions  || [];

  if (services.length && regions.length) {
    html += `<div class="section-head">
      <div class="section-title">Service Status — USA Regions</div>
      <div class="section-legend">
        <span class="legend-item">${SVG.ok} Good</span>
        <span class="legend-item">${SVG.degraded} Degraded</span>
        <span class="legend-item">${SVG.outage} Partial outage</span>
        <span class="legend-item">${SVG.critical} Major outage</span>
        <span class="legend-item">${SVG.maintenance} Maintenance</span>
      </div>
    </div>
    <div class="matrix-wrap">
      <table class="matrix">
        <thead>
          <tr>
            <th class="service-col">Service</th>
            ${regions.map(r => `<th class="region-col">${esc(r)}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${services.map(svc => {
            const cells = regions.map(reg => {
              const cell = (data.matrix[svc]||{})[reg] || { status:'operational', incidents:[] };
              const s = cell.status;
              const hasInc = cell.incidents && cell.incidents.length > 0;
              const incData = hasInc ? JSON.stringify(JSON.stringify(cell.incidents[0])) : '';
              const tip = hasInc ? `<span class="cell-tip">${esc(cell.incidents[0].title.slice(0,60))}</span>` : '';
              return `<td class="status-cell ${hasInc?'has-incident':''}" ${hasInc?`onclick="showIncidentDetail(${incData})"`:''}>
                ${tip}${statusIcon(s)}
              </td>`;
            }).join('');
            return `<tr><td class="service-name">${esc(svc)}</td>${cells}</tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`;
  }

  main.innerHTML = html;
}

// ── Detail panel ─────────────────────────────────────────────────────────────

function showIncidentDetail(jsonStr) {
  const inc = JSON.parse(jsonStr);
  selectedId = inc.id;

  document.getElementById('panel-sev').innerHTML = sevPill(inc.severity);
  document.getElementById('panel-title').textContent = inc.title;

  const services = (inc.affected_services||[]).map(s=>`<span class="tag">${esc(s)}</span>`).join('');
  const regions  = (inc.affected_regions ||[]).map(r=>`<span class="tag">${esc(r)}</span>`).join('');

  document.getElementById('panel-body').innerHTML = `
    <div class="detail-grid">
      <div class="detail-section">
        <div class="detail-label">Started</div>
        <div class="detail-value">${fmtDate(inc.started_at)}</div>
      </div>
      <div class="detail-section">
        <div class="detail-label">Duration</div>
        <div class="detail-value">${inc.duration||'—'}</div>
      </div>
      <div class="detail-section">
        <div class="detail-label">Current Status</div>
        <div class="detail-value" style="text-transform:capitalize">${esc(inc.status||'—')}</div>
      </div>
      <div class="detail-section">
        <div class="detail-label">Last Updated</div>
        <div class="detail-value">${timeAgo(inc.last_updated)}</div>
      </div>
    </div>
    ${services?`<div class="detail-section">
      <div class="detail-label">Affected Services</div>
      <div class="tag-list">${services}</div>
    </div>`:''}
    ${regions?`<div class="detail-section">
      <div class="detail-label">Affected Regions</div>
      <div class="tag-list">${regions}</div>
    </div>`:''}
    ${inc.description?`<div class="detail-section">
      <div class="detail-label">Latest Update</div>
      <div class="desc-box">${esc(inc.description)}</div>
    </div>`:''}
    <div class="detail-section">
      <div class="detail-label">Incident ID</div>
      <div class="detail-value" style="font-family:monospace;font-size:12px;color:var(--text-secondary)">${esc(inc.id)}</div>
    </div>
  `;

  document.getElementById('panel-footer').innerHTML = inc.url
    ? `<a class="btn-primary" href="${esc(inc.url)}" target="_blank" rel="noopener">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
        View on ${LABELS[activeProvider]}
      </a>` : '';

  document.getElementById('detail-panel').classList.add('open');
}

function closePanel() {
  selectedId = null;
  document.getElementById('detail-panel').classList.remove('open');
}

// ── Refresh ──────────────────────────────────────────────────────────────────

let refreshing = false;
async function manualRefresh() {
  if (refreshing) return;
  refreshing = true;
  document.getElementById('refresh-btn').classList.add('spinning');
  await loadSummary();
  await loadMatrix();
  document.getElementById('refresh-btn').classList.remove('spinning');
  refreshing = false;
}

async function autoRefresh() {
  await loadSummary();
  await loadMatrix();
}

// ── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  if (DEMO_MODE) {
    document.getElementById('demo-banner').style.display = 'flex';
  }
  await loadSummary();
  await loadMatrix();
  if (!DEMO_MODE) setInterval(autoRefresh, 30000);
}

init();
</script>
</body>
</html>
"""
