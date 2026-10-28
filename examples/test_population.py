
"""
Test NSI population assignment for Bethlehem.

Downloads NSI structure records, assigns their
population to nearest pipe-network junctions,
and saves results.

No WorldPop raster or water demand required.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
import pandas as pd

from street2water import (
    create_pipe_network,
    clean_pipe_network,
    download_nsi_structures,
    assign_nsi_population,
)


# ==================================================
# CONFIGURATION
# ==================================================

CITY = "Bethlehem, Pennsylvania, USA"

OUTPUT_DIR = Path("outputs")
DATA_DIR = Path("data/nsi")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

STREET_FILE = OUTPUT_DIR / "bethlehem_streets.graphml"
NSI_CACHE = DATA_DIR / "bethlehem_nsi.geojson"

ROAD_TYPES = [
    "primary",
    "secondary",
    "tertiary",
]

MAX_DISTANCE = None
REFRESH_NSI = False


# ==================================================
# 1. LOAD STREET NETWORK
# ==================================================

print("\nLoading existing Bethlehem street network...")

if not STREET_FILE.is_file():
    raise FileNotFoundError(
        f"Street network not found: {STREET_FILE}"
    )

G = ox.load_graphml(STREET_FILE)

print(f"Street nodes: {G.number_of_nodes():,}")
print(f"Street edges: {G.number_of_edges():,}")


# ==================================================
# 2. CREATE PIPE NETWORK
# ==================================================

print("\nCreating pipe network...")

P = create_pipe_network(
    G,
    road_types=ROAD_TYPES,
)

P = clean_pipe_network(
    P,
    keep_largest=False,
)

print(f"Junctions: {P.number_of_nodes():,}")
print(f"Pipes: {P.number_of_edges():,}")

if P.number_of_nodes() == 0:
    raise ValueError("No junctions in pipe network.")


# ==================================================
# 3. DOWNLOAD OR LOAD NSI STRUCTURES
# ==================================================

print("\nLoading NSI population data...")

structures = download_nsi_structures(
    city=CITY,
    cache_path=NSI_CACHE,
    refresh=REFRESH_NSI,
)

print(f"NSI structures: {len(structures):,}")


# ==================================================
# 4. ASSIGN POPULATION TO NEAREST JUNCTIONS
# ==================================================

P, assigned_structures, info = assign_nsi_population(
    pipe_network=P,
    structures=structures,
    max_distance=MAX_DISTANCE,
)


# ==================================================
# 5. CREATE JUNCTION POPULATION TABLE
# ==================================================

junction_table = pd.DataFrame([
    {
        "node_id": str(node),
        "junction_id": str(
            P.nodes[node].get("junction_id", f"J_{node}")
        ),
        "population": float(
            P.nodes[node]["population"]
        ),
        "population_night": float(
            P.nodes[node]["population_night"]
        ),
        "population_day": float(
            P.nodes[node]["population_day"]
        ),
        "longitude": float(P.nodes[node]["x"]),
        "latitude": float(P.nodes[node]["y"]),
    }
    for node in P.nodes()
])

junction_table = junction_table.sort_values(
    "population_night",
    ascending=False,
).reset_index(drop=True)


# ==================================================
# 6. CHECK POPULATION CONSERVATION
# ==================================================

night_total = junction_table["population_night"].sum()
day_total = junction_table["population_day"].sum()

assert abs(
    night_total - info["assigned_population_night"]
) <= max(1e-6, abs(night_total) * 1e-9)

assert abs(
    day_total - info["assigned_population_day"]
) <= max(1e-6, abs(day_total) * 1e-9)

if MAX_DISTANCE is None:
    assert info["unassigned_structures"] == 0

    assert abs(
        night_total - info["source_population_night"]
    ) <= max(1e-6, abs(night_total) * 1e-9)

    assert abs(
        day_total - info["source_population_day"]
    ) <= max(1e-6, abs(day_total) * 1e-9)

print("\nPopulation conservation: PASSED")


# ==================================================
# 7. SAVE JUNCTION POPULATION CSV
# ==================================================

junction_csv = (
    OUTPUT_DIR / "bethlehem_junction_population.csv"
)

junction_table.to_csv(junction_csv, index=False)

print(f"Saved: {junction_csv}")


# ==================================================
# 8. SAVE STRUCTURE ASSIGNMENTS
# ==================================================

structure_csv = (
    OUTPUT_DIR / "bethlehem_nsi_assignments.csv"
)

export_columns = [
    col for col in [
        "fd_id",
        "occtype",
        "population_night",
        "population_day",
        "junction_id",
        "nearest_junction",
        "distance_m",
        "assigned",
    ]
    if col in assigned_structures.columns
]

assigned_structures[export_columns].to_csv(
    structure_csv,
    index=False,
)

print(f"Saved: {structure_csv}")


# ==================================================
# 9. SAVE STRUCTURE GEOPACKAGE
# ==================================================

structure_gpkg = (
    OUTPUT_DIR / "bethlehem_nsi_structures.gpkg"
)

assigned_structures.to_file(
    structure_gpkg,
    driver="GPKG",
)

print(f"Saved: {structure_gpkg}")


# ==================================================
# 10. SAVE POPULATED NETWORK
# ==================================================

network_file = (
    OUTPUT_DIR / "bethlehem_population_network.graphml"
)

nx.write_graphml(P, network_file)

print(f"Saved: {network_file}")


# ==================================================
# 11. PLOT POPULATION MAP
# ==================================================

print("\nCreating NSI population map...")

fig, ax = plt.subplots(figsize=(12, 12))

pos = {
    node: (
        float(P.nodes[node]["x"]),
        float(P.nodes[node]["y"]),
    )
    for node in P.nodes()
}

nx.draw_networkx_edges(
    P,
    pos,
    ax=ax,
    edge_color="lightgray",
    width=0.8,
    alpha=0.8,
)

pop_values = [
    float(P.nodes[node]["population_night"])
    for node in P.nodes()
]

node_plot = nx.draw_networkx_nodes(
    P,
    pos,
    ax=ax,
    node_size=24,
    node_color=pop_values,
    cmap="viridis",
)

fig.colorbar(
    node_plot,
    ax=ax,
    label="Estimated nighttime population per junction",
    shrink=0.7,
)

ax.set_title(
    "Bethlehem - NSI Nighttime Population "
    "Assigned to Nearest Junctions"
)

ax.set_aspect("equal")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

map_file = (
    OUTPUT_DIR / "bethlehem_nsi_population.png"
)

fig.savefig(
    map_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close(fig)

print(f"Saved: {map_file}")


# ==================================================
# 12. PRINT SUMMARY
# ==================================================

print("\n" + "=" * 50)
print("NSI POPULATION ASSIGNMENT RESULTS")
print("=" * 50)

print(f"City: {CITY}")
print(f"Junctions: {P.number_of_nodes():,}")
print(f"Pipes: {P.number_of_edges():,}")
print(f"NSI structures: {info['total_structures']:,}")

print(
    f"Assigned structures: "
    f"{info['assigned_structures']:,}"
)

print(
    f"Unassigned structures: "
    f"{info['unassigned_structures']:,}"
)

print(f"Nighttime population: {night_total:,.0f}")
print(f"Daytime population: {day_total:,.0f}")

print(
    f"Populated junctions: "
    f"{info['populated_junctions']:,}"
)

if info["mean_distance_m"] is not None:
    print(
        f"Mean assignment distance: "
        f"{info['mean_distance_m']:.2f} m"
    )

if info["max_distance_m"] is not None:
    print(
        f"Maximum assignment distance: "
        f"{info['max_distance_m']:.2f} m"
    )

print("\nTop 10 junctions by nighttime population:")

print(
    junction_table[
        ["junction_id", "population_night", "population_day"]
    ].head(10).to_string(index=False)
)

print("\nAll NSI results saved successfully.")
