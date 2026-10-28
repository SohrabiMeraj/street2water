
"""
Demand estimation for street2water.

Calculate average junction water demand from
population and user-defined per-capita consumption.

Input:  liters/person/day
Output: liters/second
"""

import math
import networkx as nx


SECONDS_PER_DAY = 86400.0


def calculate_junction_demand(
    pipe_network,
    liters_per_person_per_day,
    population_attr="population",
    demand_attr="demand_lps",
):
    """
    Calculate average water demand at each junction.

    Parameters
    ----------
    pipe_network : networkx.Graph
        Network with population assigned to junctions.

    liters_per_person_per_day : float
        User-defined water consumption rate in
        liters per person per day.

    population_attr : str
        Node attribute containing population.
        Default: 'population' (NSI nighttime population).

    demand_attr : str
        Node attribute for calculated demand.
        Default: 'demand_lps'.

    Returns
    -------
    P : networkx.Graph
        Copy of network with calculated demand.

    info : dict
        Network demand summary.
    """

    rate = float(liters_per_person_per_day)

    if not math.isfinite(rate) or rate < 0:
        raise ValueError(
            "Water consumption must be a finite, "
            "nonnegative number."
        )

    if pipe_network.number_of_nodes() == 0:
        raise ValueError("Pipe network has no junctions.")

    P = pipe_network.copy()

    total_population = 0.0
    total_demand_lps = 0.0

    for node, data in P.nodes(data=True):

        if population_attr not in data:
            raise ValueError(
                f"Population attribute '{population_attr}' "
                f"is missing at node {node}."
            )

        population = float(data[population_attr])

        if not math.isfinite(population) or population < 0:
            raise ValueError(
                f"Invalid population at node {node}."
            )

        demand_lps = (
            population * rate / SECONDS_PER_DAY
        )

        data[demand_attr] = demand_lps

        total_population += population
        total_demand_lps += demand_lps

    info = {
        "total_junctions": P.number_of_nodes(),
        "total_population": total_population,
        "liters_per_person_per_day": rate,
        "total_demand_lps": total_demand_lps,
        "total_demand_m3_per_day": (
            total_demand_lps * 86.4
        ),
        "junctions_with_demand": sum(
            P.nodes[n][demand_attr] > 0
            for n in P.nodes()
        ),
    }

    print("\nJunction demand calculation")
    print("-----------------------------------")
    print(f"Junctions: {info['total_junctions']:,}")
    print(f"Population: {total_population:,.0f}")
    print(f"Consumption rate: {rate:,.2f} L/person/day")
    print(f"Total demand: {total_demand_lps:,.4f} L/s")
    print(
        f"Total demand: "
        f"{info['total_demand_m3_per_day']:,.2f} m³/day"
    )

    return P, info
