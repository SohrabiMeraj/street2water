
"""
street2water.network

Create and clean synthetic water distribution pipe networks
from OpenStreetMap street networks.

Junction IDs:
    J_1, J_2, J_3, ..., J_N

Pipe IDs:
    P_1, P_2, P_3, ..., P_M

Original OpenStreetMap node IDs are preserved internally.

Each pipe stores:
    - Pipe ID
    - Pipe length (meters)
    - OSM road classification

Road classification will later be used to assign
initial pipe diameters in EPANET.
"""

import math

import networkx as nx


# ============================================================
# DEFAULT ROAD TYPES
# ============================================================

DEFAULT_ROAD_TYPES = [
    "primary",
    "secondary",
    "tertiary",

]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _node_sort_key(node):
    """
    Provide deterministic ordering for OSM node IDs.
    """

    try:
        return (0, int(node))

    except (ValueError, TypeError):
        return (1, str(node))


def _edge_sort_key(edge):
    """
    Deterministic sorting for undirected edges.

    Ensures that (u, v) and (v, u) are treated
    consistently when assigning pipe IDs.
    """

    u, v = edge[:2]

    endpoints = sorted(
        [u, v],
        key=_node_sort_key,
    )

    return (
        _node_sort_key(endpoints[0]),
        _node_sort_key(endpoints[1]),
    )


def _renumber_network(graph):
    """
    Assign consecutive junction and pipe IDs.

    Does not change NetworkX node keys or connectivity.
    """

    # --------------------------------------------------
    # 1. Junction numbering
    # --------------------------------------------------

    sorted_nodes = sorted(
        graph.nodes,
        key=_node_sort_key,
    )

    for i, node in enumerate(
        sorted_nodes,
        start=1,
    ):

        graph.nodes[node]["junction_id"] = f"J_{i}"

        # Preserve original OSM node ID
        graph.nodes[node]["osm_id"] = str(node)

    # --------------------------------------------------
    # 2. Pipe numbering
    # --------------------------------------------------

    sorted_edges = sorted(
        graph.edges(),
        key=_edge_sort_key,
    )

    for i, (u, v) in enumerate(
        sorted_edges,
        start=1,
    ):

        graph.edges[u, v]["pipe_id"] = f"P_{i}"

    return graph


def _normalize_highway(highway):
    """
    Normalize an OSM highway attribute.

    Examples
    --------
    "primary"
        -> ["primary"]

    ["primary", "secondary"]
        -> ["primary", "secondary"]

    None
        -> []
    """

    if highway is None:
        return []

    if isinstance(highway, str):
        highway = [highway]

    elif not isinstance(
        highway,
        (list, tuple, set),
    ):
        highway = [highway]

    return [
        str(road).strip().lower()
        for road in highway
        if road is not None and str(road).strip()
    ]


def _select_road_type(
    highway,
    selected_road_types,
):
    """
    Select one road classification from an OSM edge.

    The default road hierarchy is:

        primary
        secondary
        tertiary

    Residential and other road classes can be explicitly
    selected by the user.
    """

    matched = [
        road
        for road in highway
        if road in selected_road_types
    ]

    if not matched:
        return None

    # Prioritize default road classes
    for road in DEFAULT_ROAD_TYPES:

        if road in matched:
            return road

    # Support additional road classifications
    return sorted(matched)[0]


# ============================================================
# CREATE PIPE NETWORK
# ============================================================

def create_pipe_network(
    street_graph,
    road_types=None,
):
    """
    Create an undirected synthetic pipe network from OSM.

    Parameters
    ----------
    street_graph : networkx.MultiDiGraph
        OpenStreetMap street network from OSMnx.

    road_types : list[str], optional
        Selected road classifications.

        Default:
            primary
            secondary
            tertiary

        Residential and other road classes may be
        included explicitly using road_types.

    Returns
    -------
    pipe_graph : networkx.Graph
        Synthetic water distribution network.

    Node attributes
    ---------------
    x : float
        Longitude.

    y : float
        Latitude.

    junction_id : str
        Sequential junction ID.

    osm_id : str
        Original OSM node ID.

    Edge attributes
    ---------------
    length : float
        Pipe length in meters.

    road_type : str
        OSM road classification.

    pipe_id : str
        Sequential pipe ID.
    """

    # --------------------------------------------------
    # 1. Validate selected road types
    # --------------------------------------------------

    if road_types is None:
        road_types = DEFAULT_ROAD_TYPES

    selected_road_types = {
        str(road).strip().lower()
        for road in road_types
        if road is not None and str(road).strip()
    }

    if not selected_road_types:
        raise ValueError(
            "road_types must contain at least one "
            "valid road classification."
        )

    if not street_graph.is_multigraph():
        raise TypeError(
            "street_graph must be a NetworkX "
            "MultiGraph or MultiDiGraph."
        )

    pipe_graph = nx.Graph()

    # --------------------------------------------------
    # 2. Extract eligible street edges
    # --------------------------------------------------

    for u, v, key, data in street_graph.edges(
        keys=True,
        data=True,
    ):

        # Read OSM highway classification
        highway = _normalize_highway(
            data.get("highway")
        )

        # Determine road classification
        road_type = _select_road_type(
            highway,
            selected_road_types,
        )

        # Skip unselected roads
        if road_type is None:
            continue

        # Skip self-loops
        if u == v:
            continue

        # Validate pipe length
        try:
            length = float(
                data.get("length", 0)
            )

        except (ValueError, TypeError):
            continue

        if not math.isfinite(length) or length <= 0:
            continue

        # --------------------------------------------------
        # Handle duplicate undirected edges
        # --------------------------------------------------

        # A NetworkX Graph allows only one pipe
        # between a pair of junctions.
        #
        # If multiple OSM edges connect the same
        # nodes, retain the shortest valid length.

        if pipe_graph.has_edge(u, v):

            existing_length = pipe_graph.edges[
                u, v
            ]["length"]

            if length < existing_length:

                pipe_graph.edges[
                    u, v
                ]["length"] = length

                pipe_graph.edges[
                    u, v
                ]["road_type"] = road_type

            continue

        # --------------------------------------------------
        # Add new pipe
        # --------------------------------------------------

        pipe_graph.add_edge(
            u,
            v,
            length=length,
            road_type=road_type,
        )

    # --------------------------------------------------
    # 3. Assign junction coordinates
    # --------------------------------------------------

    for node in pipe_graph.nodes:

        street_data = street_graph.nodes[node]

        try:
            longitude = float(
                street_data["x"]
            )

            latitude = float(
                street_data["y"]
            )

        except (
            KeyError,
            ValueError,
            TypeError,
        ) as exc:

            raise ValueError(
                f"Invalid coordinates for "
                f"OSM node {node}"
            ) from exc

        if not (
            math.isfinite(longitude)
            and math.isfinite(latitude)
            and -180 <= longitude <= 180
            and -90 <= latitude <= 90
        ):

            raise ValueError(
                f"Invalid coordinates for "
                f"OSM node {node}"
            )

        pipe_graph.nodes[node]["x"] = longitude
        pipe_graph.nodes[node]["y"] = latitude

        pipe_graph.nodes[node]["osm_id"] = str(node)

    # --------------------------------------------------
    # 4. Assign sequential IDs
    # --------------------------------------------------

    _renumber_network(pipe_graph)

    # --------------------------------------------------
    # 5. Print network summary
    # --------------------------------------------------

    print("\nPipe network created")
    print("-----------------------------------")

    print(
        f"Junctions: "
        f"{pipe_graph.number_of_nodes():,}"
    )

    print(
        f"Pipes: "
        f"{pipe_graph.number_of_edges():,}"
    )

    components = nx.number_connected_components(
        pipe_graph
    )

    print(
        f"Connected components: {components}"
    )

    # --------------------------------------------------
    # 6. Road classification summary
    # --------------------------------------------------

    road_counts = {}

    for _, _, data in pipe_graph.edges(
        data=True
    ):

        road = data["road_type"]

        road_counts[road] = (
            road_counts.get(road, 0) + 1
        )

    print("\nRoad classification summary:")

    for road, count in sorted(
        road_counts.items()
    ):

        print(
            f"  {road}: {count:,} pipes"
        )

    return pipe_graph


# ============================================================
# CLEAN PIPE NETWORK
# ============================================================

def clean_pipe_network(
    pipe_graph,
    keep_largest=False,
):
    """
    Clean the synthetic pipe network.

    Parameters
    ----------
    pipe_graph : networkx.Graph
        Synthetic pipe network.

    keep_largest : bool, default False
        False:
            Preserve all connected components.

        True:
            Retain only the largest component.

    Returns
    -------
    cleaned_graph : networkx.Graph
        Cleaned network with sequential junction
        and pipe IDs.

    Notes
    -----
    Preserves all surviving node and edge attributes,
    including road_type, length, x, and y.
    """

    # --------------------------------------------------
    # 1. Copy original network
    # --------------------------------------------------

    cleaned_graph = pipe_graph.copy()

    # --------------------------------------------------
    # 2. Remove self-loops
    # --------------------------------------------------

    self_loops = list(
        nx.selfloop_edges(cleaned_graph)
    )

    cleaned_graph.remove_edges_from(
        self_loops
    )

    # --------------------------------------------------
    # 3. Remove invalid pipes
    # --------------------------------------------------

    invalid_edges = []

    for u, v, data in cleaned_graph.edges(
        data=True
    ):

        try:
            length = float(
                data.get("length", 0)
            )

        except (ValueError, TypeError):

            invalid_edges.append(
                (u, v)
            )

            continue

        if (
            not math.isfinite(length)
            or length <= 0
        ):

            invalid_edges.append(
                (u, v)
            )

    cleaned_graph.remove_edges_from(
        invalid_edges
    )

    # --------------------------------------------------
    # 4. Remove isolated junctions
    # --------------------------------------------------

    isolated_nodes = list(
        nx.isolates(cleaned_graph)
    )

    cleaned_graph.remove_nodes_from(
        isolated_nodes
    )

    # --------------------------------------------------
    # 5. Check empty network
    # --------------------------------------------------

    if cleaned_graph.number_of_nodes() == 0:

        print(
            "\nPipe network is empty after cleaning."
        )

        return cleaned_graph

    # --------------------------------------------------
    # 6. Identify connected components
    # --------------------------------------------------

    components = list(
        nx.connected_components(
            cleaned_graph
        )
    )

    print(
        f"\nOriginal components: "
        f"{len(components)}"
    )

    # --------------------------------------------------
    # 7. Optionally retain largest component
    # --------------------------------------------------

    if keep_largest:

        largest_component = sorted(
            components,
            key=lambda component: (
                -len(component),
                _node_sort_key(
                    min(
                        component,
                        key=_node_sort_key,
                    )
                ),
            ),
        )[0]

        cleaned_graph = cleaned_graph.subgraph(
            largest_component
        ).copy()

        print(
            "Retaining largest connected component."
        )

    else:

        print(
            "Retaining all connected components."
        )

    # --------------------------------------------------
    # 8. Renumber junctions and pipes
    # --------------------------------------------------

    _renumber_network(
        cleaned_graph
    )

    # --------------------------------------------------
    # 9. Print final results
    # --------------------------------------------------

    print(
        f"Final junctions: "
        f"{cleaned_graph.number_of_nodes():,}"
    )

    print(
        f"Final pipes: "
        f"{cleaned_graph.number_of_edges():,}"
    )

    print(
        f"Final connected components: "
        f"{nx.number_connected_components(cleaned_graph)}"
    )

    return cleaned_graph
