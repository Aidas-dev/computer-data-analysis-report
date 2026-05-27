#!/usr/bin/env python3
"""
Fetch FracTracker Open U.S. Data Centers Tracker dataset.

Downloads data center locations from the FracTracker ArcGIS feature service
and saves as CSV. Tries multiple discovery methods to find the service URL,
then downloads all records with pagination.

Output: data/raw/fractracker_datacenters.csv
"""

import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ── Configuration ──────────────────────────────────────────────────────────────

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "fractracker_datacenters.csv")

# Known working URLs (discovered 2026-05)
KNOWN_FEATURE_SERVER = "https://services.arcgis.com/jDGuO8tYggdCCnUJ/arcgis/rest/services/data_centers_v4_agol_all/FeatureServer"
KNOWN_FEATURE_LAYER = KNOWN_FEATURE_SERVER + "/0"
EXPERIENCE_APP_ID = "5a4d072ad01449bba5698a80103fb909"

# Pagination
PAGE_SIZE = 2000  # well under standardMaxRecordCountNoGeometry=32000
REQUEST_DELAY = 0.5  # seconds between pagination requests


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[fractracker] {msg}", flush=True)


def fetch_json(url, retries=3):
    """Fetch URL and parse JSON. Returns None on failure."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                log(f"  Retry {attempt + 1}/{retries} for {url[:80]}...: {e}")
                time.sleep(2 ** attempt)
            else:
                log(f"  Failed: {e}")
    return None


def safe_val(val):
    """Convert value to string safe for CSV, handling None."""
    if val is None:
        return ""
    return str(val)


# ── Discovery Methods ─────────────────────────────────────────────────────────

def discover_via_known_url():
    """Method 1: Try the known feature service URL directly."""
    log("Method 1: Trying known feature service URL...")
    data = fetch_json(KNOWN_FEATURE_LAYER + "?f=json")
    if data and "name" in data:
        name = data.get("name", "")
        count_url = KNOWN_FEATURE_LAYER + "/query?where=1%3D1&returnCountOnly=true&f=json"
        count_data = fetch_json(count_url)
        count = (count_data or {}).get("count", "?")
        log(f"  Found layer '{name}' with ~{count} features at:")
        log(f"  {KNOWN_FEATURE_LAYER}")
        return KNOWN_FEATURE_LAYER
    log("  Failed.")
    return None


def discover_via_experience_builder():
    """Method 2: Parse the Experience Builder app config to find webmap IDs."""
    log("Method 2: Checking Experience Builder app config...")

    # Try app data endpoint
    url = f"https://experience.arcgis.com/api/apps/{EXPERIENCE_APP_ID}/data?f=json"
    data = fetch_json(url)
    if data and "dataSources" in data:
        webmap_ids = []
        for ds_id, ds in data["dataSources"].items():
            if isinstance(ds, dict) and ds.get("type") == "WEB_MAP":
                webmap_ids.append((ds.get("itemId"), ds.get("sourceLabel", "?")))
        if webmap_ids:
            log(f"  Found {len(webmap_ids)} webmap(s):")
            for wid, label in webmap_ids:
                log(f"    - {label}: {wid}")
            # Try first webmap to find feature service
            return discover_via_webmap(wid)
    log("  Experience Builder config not accessible.")
    return None


def discover_via_webmap(webmap_id):
    """Method 3: Fetch webmap data to find feature service URLs."""
    log(f"Method 3: Fetching webmap {webmap_id}...")
    urls_to_try = [
        f"https://ft.maps.arcgis.com/sharing/rest/content/items/{webmap_id}/data?f=json",
        f"https://www.arcgis.com/sharing/rest/content/items/{webmap_id}/data?f=json",
    ]
    for url in urls_to_try:
        data = fetch_json(url)
        if data and "operationalLayers" in data:
            for layer in data["operationalLayers"]:
                url_val = layer.get("url", "")
                title = layer.get("title", "?")
                if "data_center" in url_val.lower() or "datacenter" in url_val.lower():
                    # Could be a group layer; check sublayers
                    if layer.get("layerType") == "GroupLayer":
                        for sub in layer.get("layers", []):
                            sub_url = sub.get("url", "")
                            if sub_url:
                                log(f"  Found sublayer '{sub.get('title','?')}'")
                                return sub_url + "/0" if "/FeatureServer/" not in sub_url else sub_url
                    elif url_val and "/FeatureServer/" in url_val:
                        log(f"  Found layer '{title}': {url_val}")
                        return url_val
            # If no direct match, just return the first ArcGIS feature layer found
            for layer in data["operationalLayers"]:
                url_val = layer.get("url", "")
                if url_val and "/FeatureServer/" in url_val:
                    log(f"  Falling back to layer '{layer.get('title','?')}'")
                    return url_val
    log("  No feature layers found in webmap.")
    return None


def discover_via_arcgis_search():
    """Method 4: Search ArcGIS for FracTracker data center items."""
    log("Method 4: Searching ArcGIS for FracTracker data centers...")
    url = "https://www.arcgis.com/sharing/rest/search?q=fractracker+data+center&f=json&num=20"
    data = fetch_json(url)
    if data and "results" in data:
        for result in data["results"]:
            result_type = result.get("type", "")
            result_id = result.get("id", "")
            if result_type == "Web Map" and result_id:
                log(f"  Found webmap '{result.get('title','?')}' ({result_id})")
                layer_url = discover_via_webmap(result_id)
                if layer_url:
                    return layer_url
    log("  No results via ArcGIS search.")
    return None


def discover_service_url():
    """Try all discovery methods; return first working feature layer URL."""
    methods = [
        ("Known URL", discover_via_known_url),
        ("Experience Builder config", discover_via_experience_builder),
        ("ArcGIS search", discover_via_arcgis_search),
    ]
    for name, method in methods:
        log(f"--- Discovery: {name} ---")
        result = method()
        if result:
            log(f"  ✓ Found: {result}")
            return result
        log("")
    return None


# ── Data Download ─────────────────────────────────────────────────────────────

def get_record_count(layer_url):
    """Get total number of records."""
    url = f"{layer_url}/query?where=1%3D1&returnCountOnly=true&f=json"
    data = fetch_json(url)
    if data and "count" in data:
        return int(data["count"])
    return None


def download_all_records(layer_url):
    """Download all records with pagination. Returns list of dicts."""
    total = get_record_count(layer_url)
    if total is None:
        log("  Could not get record count; downloading with pagination anyway.")
    else:
        log(f"  Total records: {total}")

    all_features = []
    offset = 0
    page = 1

    while True:
        log(f"  Fetching page {page} (offset={offset}, limit={PAGE_SIZE})...")
        url = (
            f"{layer_url}/query"
            f"?where=1%3D1"
            f"&outFields=*"
            f"&returnGeometry=false"
            f"&f=json"
            f"&resultOffset={offset}"
            f"&resultRecordCount={PAGE_SIZE}"
        )
        data = fetch_json(url)
        if not data:
            log(f"  Failed at offset {offset}. Stopping.")
            break

        features = data.get("features", [])
        if not features:
            log("  No more features.")
            break

        for feat in features:
            all_features.append(feat.get("attributes", {}))

        offset += len(features)
        page += 1

        if not data.get("exceededTransferLimit", False):
            log("  Last page (no exceededTransferLimit).")
            break

        if total and offset >= total:
            break

        time.sleep(REQUEST_DELAY)

    return all_features


# ── CSV Output ────────────────────────────────────────────────────────────────

def write_csv(records, output_path):
    """Write records to CSV. Preserves field order from first record."""
    if not records:
        log("  No records to write!")
        return False

    # Collect all field names in order
    fieldnames = list(records[0].keys())
    log(f"  Fields ({len(fieldnames)}): {fieldnames}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({k: safe_val(v) for k, v in rec.items()})

    log(f"  Wrote {len(records)} rows to {output_path}")
    return True


# ── Manual Instructions (fallback) ────────────────────────────────────────────

def print_manual_instructions():
    print()
    print("=" * 70)
    print("MANUAL DOWNLOAD INSTRUCTIONS")
    print("=" * 70)
    print()
    print("If automated discovery fails, download manually from the FracTracker")
    print("dashboard and save as CSV:")
    print()
    print("1. Open: https://experience.arcgis.com/experience/5a4d072ad01449bba5698a80103fb909")
    print("2. Click on a data center point to open the popup")
    print("3. Look for an option to view the full table/source data")
    print("   (usually a 'View Table' button or similar)")
    print("4. Alternatively, use the ArcGIS REST API directly:")
    print()
    print("   Known working feature service:")
    print(f"   {KNOWN_FEATURE_SERVER}/0/query?where=1%3D1&outFields=*&f=geojson")
    print()
    print("   To download as CSV via browser:")
    print(f"   {KNOWN_FEATURE_SERVER}/0/query?where=1%3D1&outFields=*&f=json")
    print()
    print("5. Save the results as fractracker_datacenters.csv")
    print("   in: " + OUTPUT_DIR)
    print()
    print("6. The feature service also supports format=csv but may have")
    print("   query parameter restrictions. Try in browser:")
    print(f"   {KNOWN_FEATURE_SERVER}/0/query?where=1%3D1&outFields=*&returnGeometry=false&f=json")
    print()
    print("   Then copy features[].attributes into a spreadsheet.")
    print()
    print("7. Alternative download from ArcGIS item page:")
    print("   https://www.arcgis.com/home/item.html?id=d82b23d87eff4e19b8109558e8126ae7")
    print("   Look for 'Download' or 'Export' options.")
    print()
    print("=== KNOWN DATA LAYERS (from Experience Builder config) ===")
    print("  Main map (DC_Main):        abd7c231595e491c9d63513a195e21fc")
    print("  Community (DC_Community):  a546cee53364464f9e04b26b288b9939")
    print("  Power Grid (DC_Grid):     d938c9b995c941c5959355bfed1fdc89")
    print("  Resistance (DC_Resistance): 373203ab093e4706a881332f63f3d6fc")
    print("  Environment (DC_Environment): dd71077d21214167ad87994de3467423")
    print("=" * 70)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("FracTracker Data Center Dataset Downloader")
    log(f"Output: {OUTPUT_FILE}")
    log("")

    # ── Step 1: Discover feature service URL ──
    log("=== STEP 1: Discovering Feature Service URL ===")
    layer_url = discover_service_url()

    if not layer_url:
        log("")
        log("All automated discovery methods failed.")
        print_manual_instructions()
        sys.exit(1)

    log("")
    log(f"Using feature layer: {layer_url}")

    # ── Step 2: Download data ──
    log("")
    log("=== STEP 2: Downloading Data ===")
    records = download_all_records(layer_url)

    if not records:
        log("ERROR: No records downloaded.")
        print_manual_instructions()
        sys.exit(1)

    log(f"Downloaded {len(records)} total records.")

    # ── Step 3: Save to CSV ──
    log("")
    log("=== STEP 3: Saving to CSV ===")

    # Try primary output path
    success = write_csv(records, OUTPUT_FILE)

    if success:
        log("")
        log("✓ Done! Dataset saved successfully.")
        log(f"  {OUTPUT_FILE}")
        log(f"  {len(records)} data center records")
    else:
        log("ERROR: Failed to write CSV.")
        sys.exit(1)

    # ── Summary ──
    log("")
    log("=== Summary ===")
    # Count by status
    statuses = {}
    for r in records:
        s = r.get("status", "Unknown") or "Unknown"
        statuses[s] = statuses.get(s, 0) + 1
    log("Records by status:")
    for s, c in sorted(statuses.items(), key=lambda x: -x[1]):
        log(f"  {s}: {c}")

    states = set(r.get("state", "") for r in records if r.get("state"))
    log(f"States/territories: {len(states)}")


if __name__ == "__main__":
    main()
