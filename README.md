# street2water

**Generate synthetic water distribution networks from OpenStreetMap streets using Python.**

`street2water` constructs a street-aligned synthetic pipe network, assigns population from the U.S. Army Corps of Engineers National Structure Inventory (NSI), estimates junction water demand, retrieves USGS ground elevations, and exports an EPANET-compatible `.inp` file.

> **Important:** This package creates *synthetic* networks, not verified maps of buried utility infrastructure. The exported file has no automatically configured reservoirs, tanks, pumps, or other supply boundary conditions. It is not ready for hydraulic simulation without further model configuration and validation.

## Requirements and installation

Python 3.11 or newer is declared in the package metadata. The project has been tested locally with Python 3.14; other supported versions should be verified before release.

For local development, from the project directory:

```bash
python -m pip install -e .
```

After the public GitHub repository is created, the project can also be installed from a clone. Replace `YOUR_USERNAME` with the actual account name:

```bash
git clone https://github.com/YOUR_USERNAME/street2water.git
cd street2water
python -m pip install -e .
```

NSI and USGS downloads require an internet connection and availability of their respective services.

## Quick start: streets to an EPANET file

The following example demonstrates the full workflow. It may take time because it downloads NSI records and requests USGS elevations.

```python
from pathlib import Path
import street2water

city = "Bethlehem, Pennsylvania, USA"
road_types = ["primary", "secondary", "tertiary"]
consumption_lpd = 200.0  # liters per person per day

# 1. Download OpenStreetMap streets.
streets = street2water.download_streets(city)

# 2. Create a synthetic pipe network using selected roads only.
network = street2water.create_pipe_network(
    streets,
    road_types=road_types,
)

# 3. Clean the network, preserving disconnected components.
network = street2water.clean_pipe_network(
    network,
    keep_largest=False,
)

# 4. Download NSI structures for the same city.
structures = street2water.download_nsi_structures(
    city,
    cache_path="data/nsi/city_structures.geojson",
)

# 5. Assign NSI population to the nearest junctions.
network, assigned_structures, population_info = (
    street2water.assign_nsi_population(
        network,
        structures,
        max_distance=None,
    )
)

# 6. Calculate junction demand.
network, demand_info = street2water.calculate_junction_demand(
    network,
    liters_per_person_per_day=consumption_lpd,
)

# 7. Retrieve and cache USGS junction elevations.
network, elevation_info = street2water.assign_usgs_elevation(
    network,
    cache_path="data/elevation/city_elevations.csv",
)

# 8. Export the EPANET input file.
Path("outputs").mkdir(parents=True, exist_ok=True)
export_info = street2water.export_epanet_inp(
    pipe_network=network,
    output_file="outputs/city_network.inp",
    diameter_by_road={
        "primary": 300.0,
        "secondary": 250.0,
        "tertiary": 200.0,
    },
)

print("Junctions:", network.number_of_nodes())
print("Pipes:", network.number_of_edges())
print("Population summary:", population_info)
print("Demand summary:", demand_info)
print("Elevation summary:", elevation_info)
print("Export summary:", export_info)
```

By default, `create_pipe_network()` selects primary, secondary, and tertiary roads. Residential roads are excluded unless explicitly requested using `road_types`.

## User inputs and configuration

The package is currently a **Python library**. Users provide inputs as arguments to Python functions; there is no documented command-line interface or graphical interface in version 0.1.0.

### 1. Download streets

```python
streets = street2water.download_streets(
    "Bethlehem, Pennsylvania, USA"
)
```

| Parameter | Required | Description |
|---|---|---|
| `city` | Yes | Place-name query used to download an OpenStreetMap street graph. |

The public function currently accepts a city/place query, not a polygon, shapefile, or bounding-box argument.

### 2. Generate pipes and junctions

```python
network = street2water.create_pipe_network(
    streets,
    road_types=["primary", "secondary", "tertiary"],
)
```

| Parameter | Required | Description |
|---|---|---|
| `street_graph` | Yes | OSMnx street network (`networkx.MultiDiGraph`). |
| `road_types` | No | List of OpenStreetMap road classifications to retain. Defaults to primary, secondary, and tertiary. Users can explicitly include residential or other road types. |

The result is a `networkx.Graph` with node coordinates (`x`, `y`), junction identifiers, original OSM node identifiers, and pipe attributes including length (meters), road classification, and pipe identifier.

### 3. Clean the network

```python
network = street2water.clean_pipe_network(
    network,
    keep_largest=False,
)
```

| Parameter | Default | Description |
|---|---|---|
| `pipe_graph` | Required | Synthetic pipe network. |
| `keep_largest` | `False` | Preserve all connected components. Set to `True` to keep only the largest. |

**Note:** Preserving disconnected components does not make them hydraulically connected.

### 4. Download NSI structures

```python
structures = street2water.download_nsi_structures(
    city,
    cache_path="data/nsi/city_structures.geojson",
    refresh=False,
    timeout=180,
)
```

| Parameter | Default | Description |
|---|---|---|
| `city` | Required | Place-name query for the area of interest. |
| `cache_path` | `None` | Optional path for a local GeoJSON cache. |
| `refresh` | `False` | Download again even if cached data are available. |
| `timeout` | `180` | HTTP request timeout in seconds. |

Returns NSI structure points as a GeoPandas `GeoDataFrame` in EPSG:4326.

### 5. Assign population to junctions

```python
network, assigned_structures, population_info = (
    street2water.assign_nsi_population(
        network,
        structures,
        max_distance=500.0,
    )
)
```

| Parameter | Default | Description |
|---|---|---|
| `pipe_network` | Required | Graph with longitude/latitude node coordinates. |
| `structures` | Required | NSI structure-point `GeoDataFrame`. |
| `max_distance` | `None` | Maximum distance (meters) for assignment. `None` assigns all structures to their nearest junction. |

Returns three objects: a network with population attributes, the assigned structures `GeoDataFrame`, and an assignment-statistics dictionary. A distance threshold can reduce implausibly long assignments; choose it based on the study area.

### 6. Estimate water demand

```python
network, demand_info = street2water.calculate_junction_demand(
    network,
    liters_per_person_per_day=200.0,
    population_attr="population",
    demand_attr="demand_lps",
)
```

| Parameter | Default | Description |
|---|---|---|
| `pipe_network` | Required | Network with population assigned to junctions. |
| `liters_per_person_per_day` | Required | Assumed per-capita consumption (L/person/day). |
| `population_attr` | `"population"` | Node attribute containing population; the documented default is NSI nighttime population. |
| `demand_attr` | `"demand_lps"` | Node attribute where demand is stored. |

Average junction demand is calculated as:

```text
Demand (L/s) = Population × Consumption (L/person/day) / 86,400
```

For example, a junction serving 350 people at 200 L/person/day has an average demand of approximately 0.8102 L/s. The function returns the updated network and a summary dictionary.

To use another population estimate, specify its **existing node attribute name** with `population_attr`. Verify the available node attributes before doing so.

### 7. Retrieve junction elevations

```python
network, elevation_info = street2water.assign_usgs_elevation(
    network,
    max_workers=5,
    cache_path="data/elevation/usgs_elevations.csv",
    timeout=30,
    retries=3,
    refresh=False,
    progress_every=25,
)
```

| Parameter | Default | Description |
|---|---|---|
| `pipe_network` | Required | Network with `x` longitude and `y` latitude. |
| `max_workers` | `5` | Number of simultaneous elevation requests. |
| `cache_path` | `"data/elevation/usgs_elevations.csv"` | CSV cache path. |
| `timeout` | `30` | Timeout in seconds. |
| `retries` | `3` | Maximum attempts per junction. |
| `refresh` | `False` | Re-query elevations rather than relying on cached values. |
| `progress_every` | `25` | Progress-report interval. |

Returns a copied graph with `elevation_m` node attributes and a summary dictionary. Elevations are in meters.

### 8. Export EPANET input

```python
export_info = street2water.export_epanet_inp(
    pipe_network=network,
    output_file="outputs/network.inp",
    diameter_by_road={
        "primary": 300.0,
        "secondary": 250.0,
        "tertiary": 200.0,
    },
    default_diameter_mm=200.0,
    default_roughness=130.0,
    elevation_attr="elevation_m",
    demand_attr="demand_lps",
    road_type_attr="road_type",
)
```

| Parameter | Default | Description |
|---|---|---|
| `pipe_network` | Required | Network containing pipe and junction attributes. |
| `output_file` | Required | Destination `.inp` file path. |
| `diameter_by_road` | `None` | Optional mapping of road type to assumed diameter (millimeters). |
| `default_diameter_mm` | `200.0` | Diameter used for unrecognized road types. |
| `default_roughness` | `130.0` | Hazen–Williams roughness coefficient. |
| `elevation_attr` | `"elevation_m"` | Junction elevation attribute. |
| `demand_attr` | `"demand_lps"` | Junction demand attribute, in L/s. |
| `road_type_attr` | `"road_type"` | Pipe road-classification attribute. |

The documented default diameter assumptions are:

| Road class | Assumed diameter |
|---|---:|
| Primary | 300 mm |
| Secondary | 250 mm |
| Tertiary | 200 mm |

These diameters are **assumptions based on road class**, not measured pipe dimensions. The function returns an export-summary dictionary.

## Output files and objects

The workflow produces Python network graphs and, when requested, locally cached NSI GeoJSON data, USGS elevation CSV data, and an EPANET `.inp` file. The `.inp` includes synthetic junctions, pipes, lengths, diameters, elevation, demand, and coordinates.

The package does **not** automatically add reservoirs, tanks, pumps, or supply connections. Disconnected components are preserved by default. A model must have appropriate supply boundary conditions and connectivity before hydraulic simulation.

## Examples and tests

The `examples/` directory includes separate scripts for streets, network creation, population, demand, elevation, and EPANET export. These can be used as reference workflows.

To run the automated tests from the repository root:

```bash
python -m pytest tests/ -q
```

At the time of preparation, the local test suite contained 26 passing tests covering network generation, demand calculation, and EPANET export. Population assignment and elevation retrieval need dedicated automated coverage before broader compatibility claims.

## Scientific and engineering limitations

- Street alignment is not a verified representation of actual underground water mains.
- Selected road classes and synthetic pipe connections can omit real-world pipes or create unrealistic connections.
- NSI-derived population assignments and per-capita water consumption are estimates.
- Elevation data may contain errors, missing values, or resolution limitations.
- Pipe diameters and roughness are assumed, not calibrated.
- The exported network lacks automatically configured hydraulic supply infrastructure.
- The synthetic model requires validation and calibration before use in engineering design, operations, or quantitative hydraulic risk assessment.

## Data sources

- [OpenStreetMap](https://www.openstreetmap.org/)
- [USACE National Structure Inventory](https://nsi.sec.usace.army.mil/)
- [USGS Elevation Point Query Service](https://epqs.nationalmap.gov/)

Users are responsible for complying with the applicable terms and attribution requirements of upstream data providers.

## License

MIT License. See `LICENSE`.

## Version

`0.1.0` — Initial development release.
