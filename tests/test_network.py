
"""
Automated tests for street2water network generation.

These tests use small synthetic OSM graphs and do not
require internet access or downloaded datasets.
"""

import networkx as nx
import pytest

from street2water.network import (
    create_pipe_network,
    clean_pipe_network,
)


def make_street_graph():
    """Create a small synthetic OSM street network."""

    G = nx.MultiDiGraph()

    coordinates = {
        1: (-75.37, 40.62),
        2: (-75.36, 40.62),
        3: (-75.35, 40.62),
        4: (-75.34, 40.62),
        5: (-75.33, 40.62),
        6: (-75.32, 40.62),
    }

    for node, (x, y) in coordinates.items():
        G.add_node(node, x=x, y=y)

    G.add_edge(
        1, 2, highway="primary", length=100.0
    )
    G.add_edge(
        2, 3, highway="secondary", length=120.0
    )
    G.add_edge(
        3, 4, highway="residential", length=80.0
    )
    G.add_edge(
        5, 6, highway="tertiary", length=150.0
    )

    return G


def test_residential_roads_excluded():
    """Residential roads must not be selected."""

    G = make_street_graph()

    P = create_pipe_network(
        G,
        road_types=[
            "primary",
            "secondary",
            "tertiary",
        ],
    )

    road_types = {
        data["road_type"]
        for _, _, data in P.edges(data=True)
    }

    assert "residential" not in road_types
    assert P.number_of_edges() == 3


def test_preserve_disconnected_components():
    """Cleaning must preserve components by default."""

    G = make_street_graph()

    P = create_pipe_network(
        G,
        road_types=[
            "primary",
            "secondary",
            "tertiary",
        ],
    )

    P = clean_pipe_network(
        P,
        keep_largest=False,
    )

    assert nx.number_connected_components(P) == 2
    assert P.number_of_nodes() == 5
    assert P.number_of_edges() == 3


def test_keep_largest_component():
    """Optionally retain only the largest component."""

    G = make_street_graph()

    P = create_pipe_network(
        G,
        road_types=[
            "primary",
            "secondary",
            "tertiary",
        ],
    )

    P = clean_pipe_network(
        P,
        keep_largest=True,
    )

    assert nx.number_connected_components(P) == 1
    assert P.number_of_nodes() == 3
    assert P.number_of_edges() == 2


def test_unique_network_ids():
    """Every junction and pipe must have a unique ID."""

    G = make_street_graph()

    P = create_pipe_network(
        G,
        road_types=[
            "primary",
            "secondary",
            "tertiary",
        ],
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


def test_duplicate_edges_keep_shortest():
    """Duplicate OSM edges should retain shortest length."""

    G = make_street_graph()

    G.add_edge(
        1, 2,
        highway="primary",
        length=75.0,
    )

    P = create_pipe_network(
        G,
        road_types=[
            "primary",
            "secondary",
            "tertiary",
        ],
    )

    assert P.edges[1, 2]["length"] == pytest.approx(75.0)


def test_pipe_road_classification():
    """Road classifications must be retained."""

    G = make_street_graph()

    P = create_pipe_network(
        G,
        road_types=[
            "primary",
            "secondary",
            "tertiary",
        ],
    )

    assert P.edges[1, 2]["road_type"] == "primary"
    assert P.edges[2, 3]["road_type"] == "secondary"
    assert P.edges[5, 6]["road_type"] == "tertiary"
