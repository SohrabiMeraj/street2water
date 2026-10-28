
"""
street2water.epanet

Export a synthetic street-based water distribution network
to an EPANET input (.inp) file.

Features
--------
- Preserves all connected components
- Exports junction elevations and base demands
- Exports pipe lengths and initial diameters
- Uses road classification to assign pipe diameters
- Includes network coordinates
- Does not automatically add reservoirs, tanks, or pumps

The resulting network is intended for manual editing in
EPANET before hydraulic simulation.
"""

from pathlib import Path
import math

import networkx as nx


DEFAULT_DIAMETERS_MM = {
    "primary": 300.0,
    "secondary": 250.0,
    "tertiary": 200.0,
}


def _positive_number(value, label):
    """Validate a positive finite numeric value."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{label} must be numeric; received {value!r}"
        ) from exc

    if not math.isfinite(number) or number <= 0:
        raise ValueError(
            f"{label} must be positive and finite; received {value!r}"
        )

    return number


def _finite_number(value, label):
    """Validate a finite numeric value."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{label} must be numeric; received {value!r}"
        ) from exc

    if not math.isfinite(number):
        raise ValueError(
            f"{label} must be finite; received {value!r}"
        )

    return number


def _id_sort_key(value):
    """Sort IDs such as J_2 before J_10."""

    value = str(value)

    prefix, separator, number = value.rpartition("_")

    if separator and number.isdigit():
        return (prefix, 0, int(number), value)

    return (value, 1, 0, value)


def export_epanet_inp(
    pipe_network,
    output_file,
    diameter_by_road=None,
    default_diameter_mm=200.0,
    default_roughness=130.0,
    elevation_attr="elevation_m",
    demand_attr="demand_lps",
    road_type_attr="road_type",
):
    """
    Export a NetworkX pipe network to an EPANET INP file.

    Parameters
    ----------
    pipe_network : networkx.Graph
        Complete synthetic water distribution network.

    output_file : str or pathlib.Path
        Destination EPANET .inp file.

    diameter_by_road : dict, optional
        Pipe diameter in millimeters by OSM road type.

    default_diameter_mm : float
        Diameter for unknown road classifications.

    default_roughness : float
        Hazen-Williams roughness coefficient.

    elevation_attr : str
        Junction elevation attribute.

    demand_attr : str
        Junction demand attribute in L/s.

    road_type_attr : str
        Pipe road classification attribute.

    Returns
    -------
    dict
        Export summary.
    """

    # ========================================================
    # 1. VALIDATE NETWORK
    # ========================================================

    if not isinstance(pipe_network, nx.Graph):
        raise TypeError(
            "pipe_network must be a NetworkX Graph."
        )

    if pipe_network.is_directed():
        raise ValueError(
            "EPANET exporter requires an undirected graph."
        )

    if pipe_network.is_multigraph():
        raise ValueError(
            "This exporter requires a simple Graph, "
            "not a MultiGraph."
        )

    if pipe_network.number_of_nodes() == 0:
        raise ValueError("The pipe network is empty.")

    if pipe_network.number_of_edges() == 0:
        raise ValueError("The pipe network contains no pipes.")

    output_file = Path(output_file)
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    diameters = DEFAULT_DIAMETERS_MM.copy()

    if diameter_by_road is not None:
        diameters.update(diameter_by_road)

    default_diameter_mm = _positive_number(
        default_diameter_mm,
        "Default diameter",
    )

    default_roughness = _positive_number(
        default_roughness,
        "Hazen-Williams roughness",
    )

    for road, diameter in diameters.items():
        _positive_number(
            diameter,
            f"Diameter for {road}",
        )

    # ========================================================
    # 2. PREPARE JUNCTIONS
    # ========================================================

    junctions = []
    junction_ids = set()
    node_to_junction = {}

    for node, data in pipe_network.nodes(data=True):

        junction_id = str(
            data.get("junction_id", "")
        ).strip()

        if not junction_id:
            raise ValueError(
                f"Missing junction_id for node {node}"
            )

        if junction_id in junction_ids:
            raise ValueError(
                f"Duplicate junction ID: {junction_id}"
            )

        junction_ids.add(junction_id)
        node_to_junction[node] = junction_id

        elevation = _finite_number(
            data.get(elevation_attr),
            f"Elevation for {junction_id}",
        )

        demand = _finite_number(
            data.get(demand_attr),
            f"Demand for {junction_id}",
        )

        if demand < 0:
            raise ValueError(
                f"Negative demand at {junction_id}"
            )

        longitude = _finite_number(
            data.get("x"),
            f"Longitude for {junction_id}",
        )

        latitude = _finite_number(
            data.get("y"),
            f"Latitude for {junction_id}",
        )

        if not (
            -180 <= longitude <= 180
            and -90 <= latitude <= 90
        ):
            raise ValueError(
                f"Invalid geographic coordinates for {junction_id}"
            )

        junctions.append({
            "id": junction_id,
            "elevation": elevation,
            "demand": demand,
            "longitude": longitude,
            "latitude": latitude,
        })

    junctions.sort(
        key=lambda item: _id_sort_key(item["id"])
    )

    # ========================================================
    # 3. PREPARE PIPES
    # ========================================================

    pipes = []
    pipe_ids = set()
    road_counts = {}

    for u, v, data in pipe_network.edges(data=True):

        pipe_id = str(
            data.get("pipe_id", "")
        ).strip()

        if not pipe_id:
            raise ValueError(
                f"Missing pipe_id between {u} and {v}"
            )

        if pipe_id in pipe_ids:
            raise ValueError(
                f"Duplicate pipe ID: {pipe_id}"
            )

        pipe_ids.add(pipe_id)

        length = _positive_number(
            data.get("length"),
            f"Length for {pipe_id}",
        )

        road_type = str(
            data.get(road_type_attr, "")
        ).strip().lower()

        diameter = _positive_number(
            diameters.get(
                road_type,
                default_diameter_mm,
            ),
            f"Diameter for {pipe_id}",
        )

        road_counts[road_type or "unknown"] = (
            road_counts.get(
                road_type or "unknown",
                0,
            ) + 1
        )

        pipes.append({
            "id": pipe_id,
            "node1": node_to_junction[u],
            "node2": node_to_junction[v],
            "length": length,
            "diameter": diameter,
            "roughness": default_roughness,
            "road_type": road_type,
        })

    pipes.sort(
        key=lambda item: _id_sort_key(item["id"])
    )

    # ========================================================
    # 4. WRITE EPANET INPUT FILE
    # ========================================================

    lines = []

    lines.extend([
        "[TITLE]",
        "Synthetic water distribution network",
        "Generated by street2water",
        "",
        "[JUNCTIONS]",
        ";ID Elevation Demand Pattern",
    ])

    for junction in junctions:
        lines.append(
            f"{junction['id']} "
            f"{junction['elevation']:.3f} "
            f"{junction['demand']:.6f}"
        )

    lines.extend([
        "",
        "[RESERVOIRS]",
        "; No reservoirs added automatically",
        "",
        "[TANKS]",
        "; No tanks added automatically",
        "",
        "[PIPES]",
        ";ID Node1 Node2 Length Diameter Roughness MinorLoss Status",
    ])

    for pipe in pipes:
        lines.append(
            f"{pipe['id']} "
            f"{pipe['node1']} "
            f"{pipe['node2']} "
            f"{pipe['length']:.3f} "
            f"{pipe['diameter']:.2f} "
            f"{pipe['roughness']:.2f} "
            "0 OPEN"
        )

    lines.extend([
        "",
        "[PUMPS]",
        "",
        "[VALVES]",
        "",
        "[DEMANDS]",
        "",
        "[EMITTERS]",
        "",
        "[STATUS]",
        "",
        "[PATTERNS]",
        "",
        "[CURVES]",
        "",
        "[CONTROLS]",
        "",
        "[RULES]",
        "",
        "[ENERGY]",
        "",
        "[OPTIONS]",
        "UNITS LPS",
        "HEADLOSS H-W",
        "DEMAND MODEL DDA",
        "",
        "[TIMES]",
        "DURATION 0:00",
        "",
        "[REPORT]",
        "STATUS YES",
        "SUMMARY YES",
        "",
        "[COORDINATES]",
        ";Node X-Coord Y-Coord",
    ])

    # Use projected local coordinates for EPANET display.
    # A local equirectangular projection provides a useful
    # visual layout in meters without requiring pyproj.

    mean_latitude = (
        sum(j["latitude"] for j in junctions)
        / len(junctions)
    )

    mean_longitude = (
        sum(j["longitude"] for j in junctions)
        / len(junctions)
    )

    earth_radius_m = 6371000.0
    reference_lat_rad = math.radians(
        mean_latitude
    )

    for junction in junctions:

        x_m = (
            earth_radius_m
            * math.radians(
                junction["longitude"] - mean_longitude
            )
            * math.cos(reference_lat_rad)
        )

        y_m = (
            earth_radius_m
            * math.radians(
                junction["latitude"] - mean_latitude
            )
        )

        lines.append(
            f"{junction['id']} "
            f"{x_m:.3f} "
            f"{y_m:.3f}"
        )

    lines.extend([
        "",
        "[END]",
        "",
    ])

    output_file.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    # ========================================================
    # 5. SUMMARY
    # ========================================================

    total_demand = sum(
        junction["demand"]
        for junction in junctions
    )

    components = nx.number_connected_components(
        pipe_network
    )

    summary = {
        "output_file": str(output_file),
        "junctions": len(junctions),
        "pipes": len(pipes),
        "connected_components": components,
        "total_demand_lps": total_demand,
        "road_counts": road_counts,
        "has_water_sources": False,
    }

    print("\nEPANET export completed")
    print("-----------------------------------")
    print(f"File: {output_file}")
    print(f"Junctions: {len(junctions):,}")
    print(f"Pipes: {len(pipes):,}")
    print(f"Connected components: {components}")
    print(f"Total demand: {total_demand:.3f} L/s")
    print("Water sources: None (add manually in EPANET)")

    print("\nPipe classifications:")
    for road, count in sorted(road_counts.items()):
        print(f"  {road}: {count:,}")

    return summary
