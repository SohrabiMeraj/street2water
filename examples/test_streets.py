
import street2water
import osmnx as ox
from pathlib import Path

# Select a city
city = "Bethlehem, Pennsylvania, USA"

# Create output directory
output_dir = Path("outputs")
output_dir.mkdir(exist_ok=True)

# Download street network
print("Downloading street network...")
G = street2water.download_streets(city)

# Display network information
print("Number of nodes:", G.number_of_nodes())
print("Number of edges:", G.number_of_edges())

# Save street network
ox.save_graphml(
    G,
    filepath=output_dir / "bethlehem_streets.graphml"
)

# Plot and save network
fig, ax = ox.plot_graph(
    G,
    node_size=0,
    edge_linewidth=0.8,
    show=False,
    close=False
)

fig.savefig(
    output_dir / "bethlehem_streets.png",
    dpi=300,
    bbox_inches="tight"
)

print("Street network saved successfully.")
