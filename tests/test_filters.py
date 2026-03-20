from down_detector.filters.region import (
    filter_azure_usa_regions,
    filter_gcp_usa_regions,
    filter_oci_usa_regions,
    extract_azure_regions_from_text,
)


def test_gcp_usa_filter_includes_us_regions():
    locs = ["us-east1", "us-central1", "europe-west1", "asia-east1"]
    assert filter_gcp_usa_regions(locs) == ["us-east1", "us-central1"]


def test_gcp_usa_filter_empty():
    assert filter_gcp_usa_regions([]) == []


def test_azure_usa_filter():
    regions = ["East US", "West Europe", "South Central US", "Japan East"]
    result = filter_azure_usa_regions(regions)
    assert "East US" in result
    assert "South Central US" in result
    assert "West Europe" not in result


def test_oci_usa_filter():
    regions = ["US East (Ashburn)", "EU Frankfurt 1", "US West (Phoenix)"]
    result = filter_oci_usa_regions(regions)
    assert "US East (Ashburn)" in result
    assert "US West (Phoenix)" in result
    assert "EU Frankfurt 1" not in result


def test_extract_azure_regions_from_text():
    text = "Customers in East US and West US 2 may experience issues."
    regions = extract_azure_regions_from_text(text)
    assert "East US" in regions
    assert "West US 2" in regions
    assert "West Europe" not in regions
