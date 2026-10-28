
"""
street2water.elevation

Retrieve ground elevations for water-network junctions
using the USGS Elevation Point Query Service (EPQS).

Features:
- Parallel API requests
- Automatic retries
- Persistent CSV cache
- Resume interrupted downloads
- Execution time measurement
- Validation of returned elevations

Elevation units: meters
Coordinates: longitude/latitude (EPSG:4326)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import csv
import math
import time

import networkx as nx
import requests


EPQS_URL = "https://epqs.nationalmap.gov/v1/json"


def _query_usgs_elevation(
    longitude,
    latitude,
    timeout=30,
    retries=3,
):
    """
    Query USGS EPQS for a single coordinate.

    Returns
    -------
    float
        Ground elevation in meters.
    """

    params = {
        "x": longitude,
        "y": latitude,
        "units": "Meters",
        "wkid": 4326,
        "includeDate": "false",
    }

    last_error = None

    for attempt in range(retries):

        try:
            response = requests.get(
                EPQS_URL,
                params=params,
                timeout=timeout,
            )

            response.raise_for_status()

            result = response.json()

            if "value" not in result:
                raise ValueError(
                    f"Unexpected USGS response: {result}"
                )

            elevation = float(result["value"])

            if not math.isfinite(elevation):
                raise ValueError(
                    "USGS returned a nonfinite elevation."
                )

            # Common missing-data sentinel in elevation services
            if elevation <= -999999:
                raise ValueError(
                    "USGS returned a missing elevation."
                )

            return elevation

        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ) as exc:

            last_error = exc

            if attempt < retries - 1:
                time.sleep(
                    min(2 ** attempt, 8)
                )

    raise RuntimeError(
        f"USGS query failed for "
        f"({longitude}, {latitude}): {last_error}"
    )


def _load_cache(cache_path):
    """
    Load previously retrieved elevations.

    Cache is keyed by original OSM node ID.
    Coordinates are checked before reusing values.
    """

    cache = {}

    if not cache_path.exists():
        return cache

    with cache_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            try:
                node_id = row["node_id"]

                cache[node_id] = {
                    "longitude": float(row["longitude"]),
                    "latitude": float(row["latitude"]),
                    "elevation_m": float(row["elevation_m"]),
                }

            except (KeyError, ValueError, TypeError):
                continue

    return cache


def _save_cache(cache_path, cache):
    """
    Save elevations to CSV.

    Uses a temporary file to reduce risk of
    corrupting the cache during an interrupted write.
    """

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = cache_path.with_suffix(
        cache_path.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "node_id",
                "longitude",
                "latitude",
                "elevation_m",
            ],
        )

        writer.writeheader()

        for node_id, record in sorted(cache.items()):
            writer.writerow({
                "node_id": node_id,
                **record,
            })

    temporary_path.replace(cache_path)


def assign_usgs_elevation(
    pipe_network,
    max_workers=5,
    cache_path="data/elevation/usgs_elevations.csv",
    timeout=30,
    retries=3,
    refresh=False,
    progress_every=25,
):
    """
    Assign USGS ground elevations to all network junctions.

    Parameters
    ----------
    pipe_network : networkx.Graph
        Network with x=longitude and y=latitude.

    max_workers : int
        Number of simultaneous USGS requests.
        Default: 5.

    cache_path : str
        Path for persistent elevation CSV cache.

    timeout : float
        Request timeout in seconds.

    retries : int
        Maximum attempts per junction.

    refresh : bool
        If True, request all elevations again.

    progress_every : int
        Print progress after this many completed queries.

    Returns
    -------
    P : networkx.Graph
        Copy of network with elevation_m attributes.

    info : dict
        Summary of elevation assignment and timing.
    """

    if max_workers < 1:
        raise ValueError("max_workers must be >= 1.")

    if retries < 1:
        raise ValueError("retries must be >= 1.")

    if progress_every < 1:
        raise ValueError("progress_every must be >= 1.")

    if pipe_network.number_of_nodes() == 0:
        raise ValueError("Network has no junctions.")

    start_time = time.perf_counter()

    P = pipe_network.copy()

    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)

    elevations = {}
    pending = []

    # ----------------------------------------------
    # 1. Determine cached and missing elevations
    # ----------------------------------------------

    for node, data in P.nodes(data=True):

        longitude = float(data["x"])
        latitude = float(data["y"])

        if not (
            math.isfinite(longitude)
            and math.isfinite(latitude)
            and -180 <= longitude <= 180
            and -90 <= latitude <= 90
        ):
            raise ValueError(
                f"Invalid coordinates at junction {node}"
            )

        key = str(node)

        cached = cache.get(key)

        cache_valid = (
            not refresh
            and cached is not None
            and abs(
                cached["longitude"] - longitude
            ) < 1e-8
            and abs(
                cached["latitude"] - latitude
            ) < 1e-8
            and math.isfinite(cached["elevation_m"])
            and cached["elevation_m"] > -999999
        )

        if cache_valid:
            elevations[node] = cached["elevation_m"]

        else:
            pending.append(
                (node, longitude, latitude)
            )

    print("\nUSGS elevation assignment")
    print("--------------------------------------")
    print(f"Total junctions: {P.number_of_nodes():,}")
    print(f"Cached elevations: {len(elevations):,}")
    print(f"API queries required: {len(pending):,}")
    print(f"Parallel workers: {max_workers}")

    # ----------------------------------------------
    # 2. Request missing elevations concurrently
    # ----------------------------------------------

    failures = {}
    completed = 0

    if pending:

        with ThreadPoolExecutor(
            max_workers=max_workers
        ) as executor:

            future_to_node = {
                executor.submit(
                    _query_usgs_elevation,
                    longitude,
                    latitude,
                    timeout,
                    retries,
                ): (node, longitude, latitude)

                for node, longitude, latitude in pending
            }

            for future in as_completed(future_to_node):

                node, longitude, latitude = (
                    future_to_node[future]
                )

                completed += 1

                try:
                    elevation = future.result()

                    elevations[node] = elevation

                    cache[str(node)] = {
                        "longitude": longitude,
                        "latitude": latitude,
                        "elevation_m": elevation,
                    }

                except Exception as exc:
                    failures[str(node)] = str(exc)

                # Save progress periodically
                if (
                    completed % progress_every == 0
                    or completed == len(pending)
                ):

                    _save_cache(cache_path, cache)

                    print(
                        f"Completed: "
                        f"{completed:,}/{len(pending):,} "
                        f"| Successful: "
                        f"{len(elevations):,} "
                        f"| Failed: {len(failures):,}"
                    )

    # ----------------------------------------------
    # 3. Assign elevations to network nodes
    # ----------------------------------------------

    for node, elevation in elevations.items():
        P.nodes[node]["elevation_m"] = float(elevation)

    elapsed = time.perf_counter() - start_time

    info = {
        "total_junctions": P.number_of_nodes(),
        "cached_elevations": (
            P.number_of_nodes() - len(pending)
        ),
        "requested_elevations": len(pending),
        "successful_elevations": len(elevations),
        "failed_elevations": len(failures),
        "elapsed_seconds": elapsed,
        "failures": failures,
        "cache_path": str(cache_path),
    }

    print("\nElevation assignment results")
    print("--------------------------------------")
    print(
        f"Successful elevations: "
        f"{len(elevations):,}"
    )
    print(f"Failed elevations: {len(failures):,}")
    print(f"Elapsed time: {elapsed:.2f} seconds")

    if elevations:
        values = list(elevations.values())

        print(
            f"Minimum elevation: "
            f"{min(values):.2f} m"
        )
        print(
            f"Maximum elevation: "
            f"{max(values):.2f} m"
        )

    if failures:
        print(
            "\nSome elevations could not be retrieved. "
            "Successful values have been cached. "
            "Rerun the script to retry missing junctions."
        )

    return P, info
