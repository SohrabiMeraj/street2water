
"""
Automated tests for street2water EPANET export.

Tests use synthetic networks, require no internet access,
and do not modify the existing Bethlehem network.
"""

from pathlib import Path

import networkx as nx
import pytest

from street2water.epanet import export_epanet_inp


def make_test_network():
    """Create a small network with known hydraulic attributes."""

    G = nx.Graph()

    G.add_node(
        1,
        junction_id="J_1",
        x=-75.37,
        y=40.62,
        elevation_m=100.0,
        demand_lps=0.5,
    )

    G.add_node(
        2,
        junction_id="J_2",
        x=-75.36,
        y=40.62,
        elevation_m=105.0,
        demand_lps=0.8,
    )

    G.add_node(
        3,
        junction_id="J_3",
        x=-75.35,
        y=40.62,
        elevation_m=110.0,
        demand_lps=0.0,
    )

    G.add_node(
        4,
        junction_id="J_4",
        x=-75.34,
        y=40.62,
        elevation_m=115.0,
        demand_lps=0.3,
    )

    G.add_edge(
        1, 2,
        pipe_id="P_1",
        length=100.0,
        road_type="primary",
    )

    G.add_edge(
        2, 3,
        pipe_id="P_2",
        length=150.0,
        road_type="secondary",
    )

    G.add_edge(
        3, 4,
        pipe_id="P_3",
        length=200.0,
        road_type="tertiary",
    )

    return G


def read_inp_sections(path):
    """Parse an EPANET INP file into section rows."""

    sections = {}
    current_section = None

    for raw_line in Path(path).read_text(
        encoding="utf-8"
    ).splitlines():

        line = raw_line.strip()

        if not line or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line.upper()
            sections[current_section] = []
            continue

        if current_section is not None:
            content = line.split(";", 1)[0].strip()

            if content:
                sections[current_section].append(
                    content.split()
                )

    return sections


def export_test_network(tmp_path, graph=None, **kwargs):
    """Export a network into pytest's temporary directory."""

    if graph is None:
        graph = make_test_network()

    output_file = tmp_path / "test_network.inp"

    export_epanet_inp(
        pipe_network=graph,
        output_file=output_file,
        **kwargs,
    )

    assert output_file.exists()

    return read_inp_sections(output_file)


def test_epanet_file_created(tmp_path):
    """An INP file should be created successfully."""

    sections = export_test_network(tmp_path)

    assert "[JUNCTIONS]" in sections
    assert "[PIPES]" in sections
    assert "[COORDINATES]" in sections
    assert "[END]" in sections


def test_junction_count(tmp_path):
    """All junctions must be exported."""

    sections = export_test_network(tmp_path)

    junctions = sections["[JUNCTIONS]"]

    assert len(junctions) == 4


def test_pipe_count(tmp_path):
    """All pipes must be exported."""

    sections = export_test_network(tmp_path)

    pipes = sections["[PIPES]"]

    assert len(pipes) == 3


def test_junction_elevations(tmp_path):
    """Exported elevations must match network attributes."""

    sections = export_test_network(tmp_path)

    junctions = {
        row[0]: row
        for row in sections["[JUNCTIONS]"]
    }

    assert float(junctions["J_1"][1]) == pytest.approx(100)
    assert float(junctions["J_2"][1]) == pytest.approx(105)
    assert float(junctions["J_3"][1]) == pytest.approx(110)
    assert float(junctions["J_4"][1]) == pytest.approx(115)


def test_junction_demands(tmp_path):
    """Exported base demands must match network attributes."""

    sections = export_test_network(tmp_path)

    junctions = {
        row[0]: row
        for row in sections["[JUNCTIONS]"]
    }

    assert float(junctions["J_1"][2]) == pytest.approx(0.5)
    assert float(junctions["J_2"][2]) == pytest.approx(0.8)
    assert float(junctions["J_3"][2]) == pytest.approx(0.0)
    assert float(junctions["J_4"][2]) == pytest.approx(0.3)


def test_pipe_lengths(tmp_path):
    """Exported lengths must match the source network."""

    sections = export_test_network(tmp_path)

    pipes = {
        row[0]: row
        for row in sections["[PIPES]"]
    }

    assert float(pipes["P_1"][3]) == pytest.approx(100)
    assert float(pipes["P_2"][3]) == pytest.approx(150)
    assert float(pipes["P_3"][3]) == pytest.approx(200)


def test_default_pipe_diameters(tmp_path):
    """Road classes must receive the expected diameters."""

    sections = export_test_network(tmp_path)

    pipes = {
        row[0]: row
        for row in sections["[PIPES]"]
    }

    assert float(pipes["P_1"][4]) == pytest.approx(300)
    assert float(pipes["P_2"][4]) == pytest.approx(250)
    assert float(pipes["P_3"][4]) == pytest.approx(200)


def test_custom_pipe_diameters(tmp_path):
    """Users must be able to override default diameters."""

    sections = export_test_network(
        tmp_path,
        diameter_by_road={
            "primary": 400,
            "secondary": 300,
            "tertiary": 250,
        },
    )

    pipes = {
        row[0]: row
        for row in sections["[PIPES]"]
    }

    assert float(pipes["P_1"][4]) == pytest.approx(400)
    assert float(pipes["P_2"][4]) == pytest.approx(300)
    assert float(pipes["P_3"][4]) == pytest.approx(250)


def test_pipe_connections(tmp_path):
    """Pipe endpoints must reference the correct junctions."""

    sections = export_test_network(tmp_path)

    pipes = {
        row[0]: row
        for row in sections["[PIPES]"]
    }

    assert set(pipes["P_1"][1:3]) == {"J_1", "J_2"}
    assert set(pipes["P_2"][1:3]) == {"J_2", "J_3"}
    assert set(pipes["P_3"][1:3]) == {"J_3", "J_4"}


def test_coordinates(tmp_path):
    """All junctions must have EPANET coordinates."""

    sections = export_test_network(tmp_path)

    coordinates = sections["[COORDINATES]"]

    assert len(coordinates) == 4

    assert {
        row[0] for row in coordinates
    } == {"J_1", "J_2", "J_3", "J_4"}


def test_disconnected_components_preserved(tmp_path):
    """Export must preserve all disconnected components."""

    G = make_test_network()

    G.add_node(
        5,
        junction_id="J_5",
        x=-75.30,
        y=40.60,
        elevation_m=120.0,
        demand_lps=0.1,
    )

    G.add_node(
        6,
        junction_id="J_6",
        x=-75.29,
        y=40.60,
        elevation_m=125.0,
        demand_lps=0.2,
    )

    G.add_edge(
        5, 6,
        pipe_id="P_4",
        length=100.0,
        road_type="tertiary",
    )

    sections = export_test_network(tmp_path, graph=G)

    assert len(sections["[JUNCTIONS]"]) == 6
    assert len(sections["[PIPES]"]) == 4


def test_missing_elevation_rejected(tmp_path):
    """Missing elevation values should cause an error."""

    G = make_test_network()

    del G.nodes[1]["elevation_m"]

    with pytest.raises((ValueError, KeyError)):
        export_epanet_inp(
            G,
            tmp_path / "invalid.inp",
        )


def test_duplicate_junction_ids_rejected(tmp_path):
    """Duplicate junction IDs must not be accepted."""

    G = make_test_network()

    G.nodes[2]["junction_id"] = "J_1"

    with pytest.raises(ValueError):
        export_epanet_inp(
            G,
            tmp_path / "invalid.inp",
        )
