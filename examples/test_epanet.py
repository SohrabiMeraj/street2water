
"""
Test EPANET input-file export for Bethlehem, Pennsylvania.

Input:
    outputs/bethlehem_elevation_network.graphml

Output:
    outputs/bethlehem_network.inp
"""

from pathlib import Path
from collections import Counter

import networkx as nx

from street2water.epanet import export_epanet_inp


# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_DIR = Path("outputs")

INPUT_FILE = (
    OUTPUT_DIR
    / "bethlehem_elevation_network.graphml"
)

EPANET_FILE = (
    OUTPUT_DIR
    / "bethlehem_network.inp"
)

DIAMETERS_MM = {
    "primary": 300.0,
    "secondary": 250.0,
    "tertiary": 200.0,
}


# ============================================================
# STEP 1 — LOAD NETWORK
# ============================================================

print("\nSTEP 1: Loading network")

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Missing file: {INPUT_FILE}\n"
        "Run test_population.py, test_demand.py, "
        "and test_elevation.py first."
    )

P = nx.read_graphml(INPUT_FILE)

print(f"Junctions: {P.number_of_nodes():,}")
print(f"Pipes: {P.number_of_edges():,}")
print(
    "Connected components:",
    nx.number_connected_components(P),
)


# ============================================================
# STEP 2 — VERIFY ROAD TYPES
# ============================================================

print("\nSTEP 2: Checking road types")

road_counts = Counter(
    str(data.get("road_type", "MISSING")).lower()
    for _, _, data in P.edges(data=True)
)

for road, count in sorted(road_counts.items()):
    print(f"{road}: {count:,}")

unexpected = (
    set(road_counts)
    - set(DIAMETERS_MM)
)

if unexpected:
    raise ValueError(
        "Unexpected road types in elevation network: "
        f"{sorted(unexpected)}.\n"
        "Regenerate downstream files from the corrected "
        "pipe network before exporting."
    )


# ============================================================
# STEP 3 — VERIFY JUNCTION DATA
# ============================================================

print("\nSTEP 3: Checking junction attributes")

required_attributes = [
    "junction_id",
    "elevation_m",
    "demand_lps",
    "x",
    "y",
]

for attribute in required_attributes:

    missing = [
        node
        for node, data in P.nodes(data=True)
        if attribute not in data
    ]

    if missing:
        raise ValueError(
            f"{len(missing)} junctions are missing "
            f"'{attribute}'. Example: {missing[:5]}"
        )

print("All required junction attributes exist.")


# ============================================================
# STEP 4 — EXPORT EPANET FILE
# ============================================================

print("\nSTEP 4: Exporting EPANET INP")

summary = export_epanet_inp(
    pipe_network=P,
    output_file=EPANET_FILE,
    diameter_by_road=DIAMETERS_MM,
    default_diameter_mm=200.0,
    default_roughness=130.0,
)


# ============================================================
# STEP 5 — VALIDATE EXPORT
# ============================================================

print("\nSTEP 5: Validating export")

assert EPANET_FILE.exists()

assert summary["junctions"] == P.number_of_nodes()

assert summary["pipes"] == P.number_of_edges()

assert (
    summary["connected_components"]
    == nx.number_connected_components(P)
)

assert summary["has_water_sources"] is False

print("EPANET export validation passed.")
print(f"\nOpen this file in EPANET:\n{EPANET_FILE.resolve()}")
