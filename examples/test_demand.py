
"""
Test junction demand calculation.

Uses the NSI-populated network saved by
examples/test_population.py.
"""

from pathlib import Path

import networkx as nx
import pandas as pd

from street2water import calculate_junction_demand


# ==========================================
# USER INPUT
# ==========================================

LITERS_PER_PERSON_PER_DAY = 200.0  # Example; change this

POPULATION_ATTRIBUTE = "population"

INPUT_NETWORK = Path(
    "outputs/bethlehem_population_network.graphml"
)

OUTPUT_NETWORK = Path(
    "outputs/bethlehem_demand_network.graphml"
)

OUTPUT_CSV = Path(
    "outputs/bethlehem_junction_demand.csv"
)


# ==========================================
# 1. LOAD NETWORK
# ==========================================

if not INPUT_NETWORK.is_file():
    raise FileNotFoundError(
        f"Network not found: {INPUT_NETWORK}\n"
        "Run examples/test_population.py first."
    )

P = nx.read_graphml(INPUT_NETWORK)

print(f"Loaded {P.number_of_nodes():,} junctions.")


# ==========================================
# 2. CALCULATE DEMAND
# ==========================================

P, info = calculate_junction_demand(
    pipe_network=P,
    liters_per_person_per_day=LITERS_PER_PERSON_PER_DAY,
    population_attr=POPULATION_ATTRIBUTE,
)


# ==========================================
# 3. SAVE DEMAND TABLE
# ==========================================

results = pd.DataFrame([
    {
        "junction_id": P.nodes[n].get(
            "junction_id", f"J_{n}"
        ),
        "population": float(
            P.nodes[n][POPULATION_ATTRIBUTE]
        ),
        "demand_lps": float(
            P.nodes[n]["demand_lps"]
        ),
    }
    for n in P.nodes()
])

results.to_csv(OUTPUT_CSV, index=False)

print(f"Saved: {OUTPUT_CSV}")


# ==========================================
# 4. SAVE NETWORK
# ==========================================

nx.write_graphml(P, OUTPUT_NETWORK)

print(f"Saved: {OUTPUT_NETWORK}")


# ==========================================
# 5. VERIFY DEMAND
# ==========================================

expected_demand = (
    info["total_population"]
    * LITERS_PER_PERSON_PER_DAY
    / 86400.0
)

assert abs(
    results["demand_lps"].sum()
    - expected_demand
) < 1e-6

print("\nDemand conservation: PASSED")
print("\nTop 10 junctions by demand:")

print(
    results.sort_values(
        "demand_lps", ascending=False
    ).head(10).to_string(index=False)
)
