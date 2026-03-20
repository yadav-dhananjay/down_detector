"""USA region matching logic for each cloud provider."""

# Azure region display names that are in the USA
AZURE_USA_REGIONS: frozenset[str] = frozenset([
    "East US",
    "East US 2",
    "West US",
    "West US 2",
    "West US 3",
    "North Central US",
    "South Central US",
    "West Central US",
    "Central US",
])

# OCI region display names that are in the USA
OCI_USA_REGIONS: frozenset[str] = frozenset([
    "US East (Ashburn)",
    "US West (Phoenix)",
    "US Midwest (Chicago)",
    "US Gov East",
    "US Gov West",
    "US DoD East",
    "US DoD West",
])

# GCP: any location starting with "us-" is a USA region
def is_gcp_usa_region(location: str) -> bool:
    return location.lower().startswith("us-")


def filter_azure_usa_regions(regions: list[str]) -> list[str]:
    """Return only Azure region names that match USA regions.
    Performs case-insensitive substring matching to handle variations
    like 'East US (Stage)' or regions embedded in descriptions.
    """
    result = []
    for region in regions:
        for usa_region in AZURE_USA_REGIONS:
            if usa_region.lower() in region.lower():
                result.append(region)
                break
    return result


def filter_gcp_usa_regions(locations: list[str]) -> list[str]:
    return [loc for loc in locations if is_gcp_usa_region(loc)]


def filter_oci_usa_regions(regions: list[str]) -> list[str]:
    result = []
    for region in regions:
        for usa_region in OCI_USA_REGIONS:
            if usa_region.lower() in region.lower():
                result.append(region)
                break
    return result


def extract_azure_regions_from_text(text: str) -> list[str]:
    """Extract Azure USA region names mentioned in an HTML/text description."""
    found = []
    text_lower = text.lower()
    for region in AZURE_USA_REGIONS:
        if region.lower() in text_lower:
            found.append(region)
    return found
