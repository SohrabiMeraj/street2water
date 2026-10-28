
"""
Test USGS elevation assignment for Bethlehem.

Input:
    outputs/bethlehem_demand_network.graphml

Outputs:
    outputs/bethlehem_elevation_network.graphml
    outputs/bethlehem_junction_elevation.csv
    outputs/bethlehem_elevation_map.png

The USGS API is queried only for missing elevations.
"""

from pathlib import Path
import time

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

from street2water import assign_usgs_elevation


# ================================================
# USER CONFIGURATION
# ================================================

INPUT_NETWORK = Path(
    "outputs/bethlehem_demand_network.graphml"
)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_PATH = Path(
    "data/elevation/bethlehem_usgs_elevations.csv"
)

MAX_WORKERS = 5
REFRESH = False


# ================================================
# 1. LOAD EXISTING NETWORK
# ================================================

print("\nLoading Bethlehem demand network...")

if not INPUT_NETWORK.exists():
    raise FileNotFoundError(
        f"Missing: {INPUT_NETWORK}\n"
        "Run examples/test_demand.py first."
    )

P = nx.read_graphml(INPUT_NETWORK)

print(f"Junctions: {P.number_of_nodes():,}")
print(f"Pipes: {P.number_of_edges():,}")


# ================================================
# 2. QUERY USGS ELEVATIONS
# ================================================

start = time.perf_counter()

P, info = assign_usgs_elevation(
    pipe_network=P,
    max_workers=MAX_WORKERS,
    cache_path=CACHE_PATH,
    timeout=30,
    retries=3,
    refresh=REFRESH,
    progress_every=25,
)

elapsed = time.perf_counter() - start


# ================================================
# 3. VERIFY ALL ELEVATIONS
# ================================================

missing_nodes = [
    n for n in P.nodes()
    if "elevation_m" not in P.nodes[n]
]

if missing_nodes:
    raise RuntimeError(
        f"{len(missing_nodes)} junctions are missing "
        "elevation. Successful results are cached; "
        "rerun this script to retry."
    )


# ================================================
# 4. SAVE JUNCTION ELEVATION TABLE
# ================================================

records = []

for node, data in P.nodes(data=True):

    records.append({
        "osm_id": str(node),
        "junction_id": data["junction_id"],
        "longitude": float(data["x"]),
        "latitude": float(data["y"]),
        "elevation_m": float(data["elevation_m"]),
        "population": float(
            data.get("population", 0)
        ),
        "demand_lps": float(
            data.get("demand_lps", 0)
        ),
    })

df = pd.DataFrame(records)

df["junction_number"] = (
    df["junction_id"]
    .str.replace("J_", "", regex=False)
    .astype(int)
)

df = df.sort_values("junction_number")
df = df.drop(columns=["junction_number"])

csv_path = (
    OUTPUT_DIR / "bethlehem_junction_elevation.csv"
)

df.to_csv(csv_path, index=False)

print(f"\nSaved: {csv_path}")


# ================================================
# 5. SAVE UPDATED NETWORK
# ================================================

network_path = (
    OUTPUT_DIR / "bethlehem_elevation_network.graphml"
)

nx.write_graphml(P, network_path)

print(f"Saved: {network_path}")


# ================================================
# 6. CREATE ELEVATION MAP
# ================================================

fig, ax = plt.subplots(figsize=(12, 12))

pos = {
    n: (
        float(P.nodes[n]["x"]),
        float(P.nodes[n]["y"]),
    )
    for n in P.nodes()
}

nx.draw_networkx_edges(
    P,
    pos,
    ax=ax,
    edge_color="lightgray",
    width=0.7,
    alpha=0.7,
)

elevations = [
    float(P.nodes[n]["elevation_m"])
    for n in P.nodes()
]

points = nx.draw_networkx_nodes(
    P,
    pos,
    ax=ax,
    node_size=20,
    node_color=elevations,
    cmap="terrain",
)

fig.colorbar(
    points,
    ax=ax,
    label="Ground elevation (m)",
    shrink=0.7,
)

ax.set_title(
    "Bethlehem - USGS Ground Elevation at Junctions"
)

ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.set_aspect("equal")

map_path = (
    OUTPUT_DIR / "bethlehem_elevation_map.png"
)

fig.savefig(
    map_path,
    dpi=300,
    bbox_inches="tight",
)

plt.close(fig)

print(f"Saved: {map_path}")


# ================================================
# 7. SUMMARY
# ================================================

print("\n" + "=" * 50)
print("BETHLEHEM ELEVATION RESULTS")
print("=" * 50)

print(f"Total junctions: {len(df):,}")
print(f"Minimum elevation: {df['elevation_m'].min():.2f} m")
print(f"Maximum elevation: {df['elevation_m'].max():.2f} m")
print(f"Mean elevation: {df['elevation_m'].mean():.2f} m")

print(
    f"Time required: {elapsed:.2f} seconds "
    f"({elapsed / 60:.2f} minutes)"
)

print("\nFirst 10 junctions:")

print(
    df[
        [
            "junction_id",
            "elevation_m",
            "population",
            "demand_lps",
        ]
    ].head(10).to_string(index=False)
)

print("\nElevation assignment completed successfully.")
