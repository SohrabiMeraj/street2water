
"""
Automated tests for street2water demand calculations.

Tests use small synthetic networks and do not require
internet access or external datasets.
"""

import networkx as nx
import pytest

from street2water.demand import calculate_junction_demand


def make_population_network():
    """Create a network with known junction populations."""

    G = nx.Graph()

    G.add_node("J1", population=100)
    G.add_node("J2", population=250)
    G.add_node("J3", population=0)

    G.add_edge("J1", "J2", length=100.0)
    G.add_edge("J2", "J3", length=150.0)

    return G


def calculate_demand_graph(
    graph,
    liters_per_person_per_day=200,
    **kwargs,
):
    """
    Call the existing demand function and extract its graph.

    The current street2water implementation returns a tuple
    containing the updated graph and additional results.
    """

    result = calculate_junction_demand(
        graph,
        liters_per_person_per_day=liters_per_person_per_day,
        **kwargs,
    )

    assert isinstance(result, tuple), (
        "Expected calculate_junction_demand to return a tuple."
    )

    assert len(result) >= 2, (
        "Expected a graph and additional demand results."
    )

    updated_graph = result[0]

    assert isinstance(updated_graph, nx.Graph), (
        "The first return value must be a NetworkX graph."
    )

    return updated_graph


def test_demand_calculation():
    """Check population-to-demand conversion."""

    G = make_population_network()

    P = calculate_demand_graph(G)

    assert P.nodes["J1"]["demand_lps"] == pytest.approx(
        100 * 200 / 86400
    )

    assert P.nodes["J2"]["demand_lps"] == pytest.approx(
        250 * 200 / 86400
    )


def test_zero_population():
    """Zero population must produce zero demand."""

    G = make_population_network()

    P = calculate_demand_graph(G)

    assert P.nodes["J3"]["demand_lps"] == pytest.approx(0.0)


def test_total_demand():
    """Total demand must equal the population-based calculation."""

    G = make_population_network()

    P = calculate_demand_graph(G)

    total_demand = sum(
        data["demand_lps"]
        for _, data in P.nodes(data=True)
    )

    expected = 350 * 200 / 86400

    assert total_demand == pytest.approx(expected)


def test_custom_population_attribute():
    """Support alternative population attributes."""

    G = nx.Graph()

    G.add_node("J1", population_day=500)

    P = calculate_demand_graph(
        G,
        liters_per_person_per_day=150,
        population_attr="population_day",
    )

    assert P.nodes["J1"]["demand_lps"] == pytest.approx(
        500 * 150 / 86400
    )


def test_custom_demand_attribute():
    """Support alternative demand attribute names."""

    G = nx.Graph()

    G.add_node("J1", population=100)

    P = calculate_demand_graph(
        G,
        demand_attr="base_demand",
    )

    assert P.nodes["J1"]["base_demand"] == pytest.approx(
        100 * 200 / 86400
    )


def test_network_structure_preserved():
    """Demand calculation must preserve network topology."""

    G = make_population_network()

    original_nodes = set(G.nodes())

    original_edges = {
        frozenset(edge)
        for edge in G.edges()
    }

    P = calculate_demand_graph(G)

    assert set(P.nodes()) == original_nodes

    assert {
        frozenset(edge)
        for edge in P.edges()
    } == original_edges


def test_return_structure():
    """Verify the demand function's return structure."""

    G = make_population_network()

    result = calculate_junction_demand(
        G,
        liters_per_person_per_day=200,
    )

    assert isinstance(result, tuple)
    assert len(result) >= 2
    assert isinstance(result[0], nx.Graph)
