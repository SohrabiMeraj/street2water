
"""
street2water

Generate synthetic water distribution networks from
OpenStreetMap street networks.

Main features
-------------
- Download street networks from OpenStreetMap
- Generate synthetic pipe networks
- Assign population using the National Structure Inventory
- Calculate junction water demand
- Retrieve junction elevations from USGS
- Export networks to EPANET input files
"""

from .streets import download_streets

from .network import (
    DEFAULT_ROAD_TYPES,
    create_pipe_network,
    clean_pipe_network,
)

from .population import (
    download_nsi_structures,
    assign_nsi_population,
)

from .demand import calculate_junction_demand

from .elevation import assign_usgs_elevation

from .epanet import export_epanet_inp


__version__ = "0.1.0"


__all__ = [
    "DEFAULT_ROAD_TYPES",
    "download_streets",
    "create_pipe_network",
    "clean_pipe_network",
    "download_nsi_structures",
    "assign_nsi_population",
    "calculate_junction_demand",
    "assign_usgs_elevation",
    "export_epanet_inp",
]
