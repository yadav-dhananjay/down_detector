import time
import threading
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from ..models import Provider, Severity, StatusEvent
from ..store import StatusStore

console = Console()

SEVERITY_STYLES: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.OUTAGE: "red",
    Severity.DEGRADED: "yellow",
    Severity.MAINTENANCE: "cyan",
    Severity.OPERATIONAL: "green",
}

SEVERITY_ICONS: dict[Severity, str] = {
    Severity.CRITICAL: "🔴",
    Severity.OUTAGE: "🟠",
    Severity.DEGRADED: "🟡",
    Severity.MAINTENANCE: "🔵",
    Severity.OPERATIONAL: "🟢",
}

PROVIDER_LABELS: dict[Provider, str] = {
    Provider.AZURE: "Azure",
    Provider.GCP: "GCP",
    Provider.OCI: "OCI",
    Provider.CLOUDFLARE: "Cloudflare",
}


def _format_time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "[dim]never[/dim]"
    delta = datetime.utcnow() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


def _poll_status_style(dt: datetime | None, interval: int) -> str:
    if dt is None:
        return "dim"
    age = (datetime.utcnow() - dt).total_seconds()
    if age > interval * 2:
        return "yellow"
    return "green"


def build_header(store: StatusStore, poll_interval: int) -> Panel:
    summary = store.provider_summary()
    grid = Table.grid(padding=(0, 2))
    grid.add_column()
    grid.add_column()
    grid.add_column()
    grid.add_column()

    cells = []
    for provider in Provider:
        data = summary[provider]
        last_poll = data["last_poll"]
        error = data["error"]
        active = data["active_count"]
        style = _poll_status_style(last_poll, poll_interval)

        if error:
            status_text = Text(f"[ERROR] {_format_time_ago(last_poll)}", style="red")
        elif active > 0:
            status_text = Text(f"{active} incident{'s' if active != 1 else ''} • {_format_time_ago(last_poll)}", style="yellow")
        else:
            status_text = Text(f"OK • {_format_time_ago(last_poll)}", style=style)

        cell = Text()
        cell.append(f"{PROVIDER_LABELS[provider]}: ", style="bold")
        cell.append_text(status_text)
        cells.append(cell)

    grid.add_row(*cells)

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return Panel(
        grid,
        title=f"[bold cyan]Cloud Status Monitor[/bold cyan]  [dim]{now_str}[/dim]",
        border_style="cyan",
    )


def build_incidents_table(events: list[StatusEvent]) -> Table | Panel:
    active = [e for e in events if e.is_active]

    if not active:
        return Panel(
            Text("All systems operational — no active incidents in USA regions", style="bold green", justify="center"),
            border_style="green",
            title="[bold green]Incidents[/bold green]",
        )

    # Sort by severity (most critical first), then by start time
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.OUTAGE: 1,
        Severity.DEGRADED: 2,
        Severity.MAINTENANCE: 3,
        Severity.OPERATIONAL: 4,
    }
    active.sort(key=lambda e: (severity_order.get(e.severity, 9), e.started_at))

    table = Table(
        box=box.ROUNDED,
        border_style="bright_black",
        header_style="bold white",
        show_lines=True,
        expand=True,
    )
    table.add_column("Provider", width=12)
    table.add_column("Severity", width=12)
    table.add_column("Title", min_width=30)
    table.add_column("Services", min_width=20)
    table.add_column("Regions", min_width=18)
    table.add_column("Started", width=14)
    table.add_column("Duration", width=10)

    for event in active:
        style = SEVERITY_STYLES.get(event.severity, "white")
        icon = SEVERITY_ICONS.get(event.severity, "")

        provider_text = Text(PROVIDER_LABELS[event.provider], style="bold")
        severity_text = Text(f"{icon} {event.severity.value.upper()}", style=style)
        title_text = Text(event.title, overflow="fold")

        services_str = "\n".join(event.affected_services[:3])
        if len(event.affected_services) > 3:
            services_str += f"\n+{len(event.affected_services) - 3} more"

        regions_str = "\n".join(event.affected_regions[:3])
        if len(event.affected_regions) > 3:
            regions_str += f"\n+{len(event.affected_regions) - 3} more"

        started_str = event.started_at.strftime("%m/%d %H:%M")

        table.add_row(
            provider_text,
            severity_text,
            title_text,
            Text(services_str, style="dim"),
            Text(regions_str, style="dim"),
            Text(started_str),
            Text(event.duration_str),
        )

    return Panel(table, title=f"[bold red]Active Incidents ({len(active)})[/bold red]", border_style="red")


def build_footer() -> Text:
    return Text(
        " [q] Quit  [r] Force Refresh  [f] Toggle resolved  —  Polling every 60s",
        style="dim",
        justify="center",
    )


def run_terminal_dashboard(store: StatusStore, poll_interval: int, stop_event: threading.Event) -> None:
    """Run the Rich live dashboard. Blocks until stop_event is set or user quits."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="body"),
        Layout(name="footer", size=1),
    )

    with Live(layout, console=console, refresh_per_second=1, screen=True) as live:
        while not stop_event.is_set():
            events = store.get_all()

            layout["header"].update(build_header(store, poll_interval))
            layout["body"].update(build_incidents_table(events))
            layout["footer"].update(build_footer())

            time.sleep(1)
