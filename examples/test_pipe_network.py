
"""
Test synthetic pipe network generation for Bethlehem, PA.

Selected road types:
    - primary
    - secondary
    - tertiary

Residential roads are excluded.

All disconnected components are preserved.
"""

from pathlib import Path
from collections import Counter

import networkx as nx
import street2water


# ============================================================
# CONFIGURATION
# ============================================================

CITY = "Bethlehem, Pennsylvania, USA"

ROAD_TYPES = [
    "primary",
    "secondary",
    "tertiary",
]

KEEP_LARGEST = False

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STREET_FILE = OUTPUT_DIR / "bethlehem_streets.graphml"
PIPE_FILE = OUTPUT_DIR / "bethlehem_pipe_network.graphml"


# ============================================================
# STEP 1 — LOAD STREET NETWORK
# ============================================================

print("\nSTEP 1: Loading street network")

if STREET_FILE.exists():

    G = nx.read_graphml(
        STREET_FILE,
        force_multigraph=True,
    )

    print(f"Loaded: {STREET_FILE}")

else:

    raise FileNotFoundError(
        f"Street network file not found: {STREET_FILE}\n"
        "Run examples/test_streets.py first."
    )

print(f"Street nodes: {G.number_of_nodes():,}")
print(f"Street edges: {G.number_of_edges():,}")


# ============================================================
# STEP 2 — CREATE PIPE NETWORK
# ============================================================

print("\nSTEP 2: Creating pipe network")

print(f"Selected road types: {ROAD_TYPES}")

P = street2water.create_pipe_network(
    G,
    road_types=ROAD_TYPES,
)


# ============================================================
# STEP 3 — CLEAN PIPE NETWORK
# ============================================================

print("\nSTEP 3: Cleaning pipe network")

P = street2water.clean_pipe_network(
    P,
    keep_largest=KEEP_LARGEST,
)


# ============================================================
# STEP 4 — VERIFY ROAD CLASSIFICATIONS
# ============================================================

print("\nSTEP 4: Checking road classifications")

road_counts = Counter(
    data.get("road_type", "MISSING")
    for _, _, data in P.edges(data=True)
)

for road, count in sorted(road_counts.items()):
    print(f"{road}: {count:,} pipes")

assert "residential" not in road_counts, (
    "Residential roads were unexpectedly included!"
)

assert "MISSING" not in road_counts, (
    "Some pipes are missing road_type!"
)

assert all(
    road in ROAD_TYPES
    for road in road_counts
), "Unexpected road classification found."


# ============================================================
# STEP 5 — NETWORK SUMMARY
# ============================================================

print("\nSTEP 5: Final network summary")

print(f"Junctions: {P.number_of_nodes():,}")
print(f"Pipes: {P.number_of_edges():,}")

components = list(nx.connected_components(P))

print(f"Connected components: {len(components)}")

for i, component in enumerate(
    sorted(components, key=len, reverse=True),
    start=1,
):

    subgraph = P.subgraph(component)

    print(
        f"Component {i}: "
        f"{subgraph.number_of_nodes():,} junctions, "
        f"{subgraph.number_of_edges():,} pipes"
    )


# ============================================================
# STEP 6 — SAVE PIPE NETWORK
# ============================================================

print("\nSTEP 6: Saving pipe network")

nx.write_graphml(
    P,
    PIPE_FILE,
)

print(f"Saved: {PIPE_FILE}")


# ============================================================
# STEP 7 — FINAL VALIDATION
# ============================================================

print("\nFINAL VALIDATION")

assert P.number_of_nodes() > 0, (
    "No junctions were generated."
)

assert P.number_of_edges() > 0, (
    "No pipes were generated."
)

junction_ids = [
    data["junction_id"]
    for _, data in P.nodes(data=True)
]

pipe_ids = [
    data["pipe_id"]
    for _, _, data in P.edges(data=True)
]

assert len(junction_ids) == len(set(junction_ids))
assert len(pipe_ids) == len(set(pipe_ids))

print("All junction IDs are unique.")
print("All pipe IDs are unique.")
print("No residential roads are included.")
print("All disconnected components are preserved.")

print("\nPipe network test completed successfully.")
