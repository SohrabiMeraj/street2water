
"""
NSI population assignment for street2water.

Downloads USACE National Structure Inventory (NSI)
structure records and assigns their modeled population
to the nearest pipe-network junction.

Does not calculate water demand.
"""

import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import requests

from scipy.spatial import cKDTree
from shapely.geometry import mapping


NSI_URL = (
    "https://nsi.sec.usace.army.mil/"
    "nsiapi/structures?fmt=fc"
)

POPULATION_FIELDS = [
    "pop2amu65",
    "pop2amo65",
    "pop2pmu65",
    "pop2pmo65",
]


def download_nsi_structures(
    city,
    cache_path=None,
    refresh=False,
    timeout=180,
):
    """
    Download NSI structures inside a city boundary.

    Parameters
    ----------
    city : str
        OSMnx geocoding query, e.g.
        'Bethlehem, Pennsylvania, USA'.

    cache_path : str or Path or None
        Local GeoJSON cache.

    refresh : bool
        If True, download again even when cached.

    timeout : int
        HTTP request timeout in seconds.

    Returns
    -------
    structures : geopandas.GeoDataFrame
        NSI structure points in EPSG:4326.
    """

    if cache_path is not None:
        cache_path = Path(cache_path)

        if cache_path.exists() and not refresh:
            print(f"Loading cached NSI data: {cache_path}")

            structures = gpd.read_file(cache_path)

            if structures.crs is None:
                raise ValueError(
                    "Cached NSI data has no CRS."
                )

            return structures.to_crs("EPSG:4326")

    print(f"Obtaining city boundary: {city}")

    boundary = ox.geocode_to_gdf(city).to_crs(
        "EPSG:4326"
    )

    if boundary.empty:
        raise ValueError("City boundary is empty.")

    # Use a GeoJSON FeatureCollection, as required
    # by the NSI polygon POST API.
    features = []

    for geom in boundary.geometry:
        if geom is None or geom.is_empty:
            continue

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {},
        })

    if not features:
        raise ValueError(
            "No valid polygon geometry found."
        )

    payload = {
        "type": "FeatureCollection",
        "features": features,
    }

    print("Requesting NSI structures from USACE...")

    try:
        response = requests.post(
            NSI_URL,
            json=payload,
            headers={
                "Accept": "application/geo+json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

        response.raise_for_status()

        result = response.json()

    except requests.RequestException as exc:
        raise RuntimeError(
            "NSI API request failed. "
            "Check your internet connection, "
            "API availability, or request size."
        ) from exc

    except ValueError as exc:
        raise RuntimeError(
            "NSI API did not return valid JSON."
        ) from exc

    if result.get("type") != "FeatureCollection":
        raise ValueError(
            "Unexpected NSI API response format."
        )

    features = result.get("features", [])

    if not features:
        raise ValueError(
            "NSI API returned no structures."
        )

    structures = gpd.GeoDataFrame.from_features(
        features,
        crs="EPSG:4326",
    )

    # Keep only point records.
    structures = structures.loc[
        structures.geometry.notna()
        & (structures.geometry.geom_type == "Point")
    ].copy()

    # Enforce the actual city boundary locally.
    # This also prevents retaining any records
    # outside the intended study area.
    inside = structures.geometry.apply(
        lambda point: any(
            polygon.covers(point)
            for polygon in boundary.geometry
        )
    )

    structures = structures.loc[inside].copy()

    if structures.empty:
        raise ValueError(
            "No NSI structure points inside city."
        )

    # Avoid duplicate structures if overlapping
    # boundary features were queried.
    if "fd_id" in structures.columns:
        structures = structures.drop_duplicates(
            subset="fd_id"
        )
    else:
        structures = structures.drop_duplicates(
            subset="geometry"
        )

    structures = structures.reset_index(drop=True)

    if cache_path is not None:
        cache_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        structures.to_file(
            cache_path,
            driver="GeoJSON",
        )

        print(f"NSI cache saved: {cache_path}")

    print(
        f"NSI structures downloaded: "
        f"{len(structures):,}"
    )

    return structures


def assign_nsi_population(
    pipe_network,
    structures,
    max_distance=None,
):
    """
    Assign NSI structure population to nearest
    pipe-network junction.

    Parameters
    ----------
    pipe_network : networkx.Graph
        Network with x/y coordinates in EPSG:4326.

    structures : geopandas.GeoDataFrame
        NSI structure points.

    max_distance : float or None
        Maximum assignment distance in meters.
        None means all structures are assigned.

    Returns
    -------
    P : networkx.Graph
        Network with population attributes.

    assigned_structures : geopandas.GeoDataFrame
        NSI points with junction assignments.

    info : dict
        Population and assignment statistics.
    """

    if pipe_network.number_of_nodes() == 0:
        raise ValueError(
            "Pipe network has no junctions."
        )

    if structures.empty:
        raise ValueError(
            "NSI structure dataset is empty."
        )

    if structures.crs is None:
        raise ValueError(
            "NSI structures have no CRS."
        )

    if max_distance is not None:
        if max_distance <= 0:
            raise ValueError(
                "max_distance must be positive."
            )

    missing = [
        field
        for field in POPULATION_FIELDS
        if field not in structures.columns
    ]

    if missing:
        raise ValueError(
            "Missing NSI population fields: "
            + ", ".join(missing)
        )

    P = pipe_network.copy()
    structures = structures.copy()

    # -----------------------------------------
    # 1. Read population attributes
    # -----------------------------------------

    for field in POPULATION_FIELDS:
        structures[field] = pd.to_numeric(
            structures[field],
            errors="coerce",
        )

    # Missing population is unknown, not zero.
    # Fail rather than silently undercounting.
    if structures[POPULATION_FIELDS].isna().any().any():
        raise ValueError(
            "Some NSI population values are missing. "
            "Inspect the records before assignment."
        )

    if (structures[POPULATION_FIELDS] < 0).any().any():
        raise ValueError(
            "Negative NSI population values found."
        )

    structures["population_night"] = (
        structures["pop2amu65"]
        + structures["pop2amo65"]
    )

    structures["population_day"] = (
        structures["pop2pmu65"]
        + structures["pop2pmo65"]
    )

    # -----------------------------------------
    # 2. Create junction GeoDataFrame
    # -----------------------------------------

    nodes = list(P.nodes())

    junctions = gpd.GeoDataFrame(
        {"node_id": [str(n) for n in nodes]},
        geometry=gpd.points_from_xy(
            [float(P.nodes[n]["x"]) for n in nodes],
            [float(P.nodes[n]["y"]) for n in nodes],
        ),
        crs="EPSG:4326",
    )

    # -----------------------------------------
    # 3. Project to meters
    # -----------------------------------------

    metric_crs = junctions.estimate_utm_crs()

    if metric_crs is None:
        raise ValueError(
            "Could not determine metric CRS."
        )

    junctions_m = junctions.to_crs(metric_crs)

    structures_m = structures.to_crs(metric_crs)

    # -----------------------------------------
    # 4. Find nearest junction
    # -----------------------------------------

    junction_xy = np.column_stack([
        junctions_m.geometry.x.to_numpy(),
        junctions_m.geometry.y.to_numpy(),
    ])

    structure_xy = np.column_stack([
        structures_m.geometry.x.to_numpy(),
        structures_m.geometry.y.to_numpy(),
    ])

    tree = cKDTree(junction_xy)

    distances, indices = tree.query(
        structure_xy,
        k=1,
    )

    if max_distance is None:
        assigned = np.ones(
            len(structures),
            dtype=bool,
        )
    else:
        assigned = distances <= max_distance

    structures["distance_m"] = distances
    structures["assigned"] = assigned

    structures["nearest_junction"] = [
        str(nodes[int(index)]) if accepted else None
        for index, accepted in zip(
            indices, assigned
        )
    ]

    structures["junction_id"] = [
        (
            str(
                P.nodes[nodes[int(index)]].get(
                    "junction_id",
                    f"J_{nodes[int(index)]}",
                )
            )
            if accepted else None
        )
        for index, accepted in zip(
            indices, assigned
        )
    ]

    # -----------------------------------------
    # 5. Aggregate by junction
    # -----------------------------------------

    assigned_structures = structures.loc[
        structures["assigned"]
    ]

    totals = assigned_structures.groupby(
        "nearest_junction"
    )[
        ["population_night", "population_day"]
    ].sum()

    for node in nodes:
        node_key = str(node)

        if node_key in totals.index:
            night = float(
                totals.loc[
                    node_key, "population_night"
                ]
            )

            day = float(
                totals.loc[
                    node_key, "population_day"
                ]
            )

        else:
            night = 0.0
            day = 0.0

        P.nodes[node]["population_night"] = night
        P.nodes[node]["population_day"] = day

        # Main population attribute:
        # nighttime population.
        P.nodes[node]["population"] = night

    # -----------------------------------------
    # 6. Conservation checks
    # -----------------------------------------

    source_night = float(
        structures["population_night"].sum()
    )

    source_day = float(
        structures["population_day"].sum()
    )

    assigned_night = float(
        sum(
            P.nodes[n]["population_night"]
            for n in nodes
        )
    )

    assigned_day = float(
        sum(
            P.nodes[n]["population_day"]
            for n in nodes
        )
    )

    unassigned_night = float(
        structures.loc[
            ~structures["assigned"],
            "population_night",
        ].sum()
    )

    unassigned_day = float(
        structures.loc[
            ~structures["assigned"],
            "population_day",
        ].sum()
    )

    for source, allocated, unallocated in [
        (
            source_night,
            assigned_night,
            unassigned_night,
        ),
        (
            source_day,
            assigned_day,
            unassigned_day,
        ),
    ]:
        if not np.isclose(
            source,
            allocated + unallocated,
            rtol=1e-9,
            atol=1e-6,
        ):
            raise ValueError(
                "Population conservation failed."
            )

    assigned_distances = distances[assigned]

    info = {
        "total_junctions": len(nodes),
        "total_structures": len(structures),
        "assigned_structures": int(
            assigned.sum()
        ),
        "unassigned_structures": int(
            (~assigned).sum()
        ),
        "source_population_night": source_night,
        "source_population_day": source_day,
        "assigned_population_night": assigned_night,
        "assigned_population_day": assigned_day,
        "unassigned_population_night": unassigned_night,
        "unassigned_population_day": unassigned_day,
        "populated_junctions": sum(
            P.nodes[n]["population_night"] > 0
            for n in nodes
        ),
        "mean_distance_m": (
            float(assigned_distances.mean())
            if len(assigned_distances) else None
        ),
        "max_distance_m": (
            float(assigned_distances.max())
            if len(assigned_distances) else None
        ),
    }

    print("\nNSI population assignment")
    print("--------------------------------------")
    print(
        f"Structures: "
        f"{info['total_structures']:,}"
    )
    print(
        f"Assigned structures: "
        f"{info['assigned_structures']:,}"
    )
    print(
        f"Unassigned structures: "
        f"{info['unassigned_structures']:,}"
    )
    print(
        f"Night population: "
        f"{assigned_night:,.0f}"
    )
    print(
        f"Day population: "
        f"{assigned_day:,.0f}"
    )
    print("Population conservation: PASSED")

    return P, structures, info
