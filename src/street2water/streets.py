import osmnx as ox

def download_streets(city):
    """
    Download street networks from OpenStreetMap.
    """

    ox.settings.use_cache = True
    ox.settings.requests_timeout = 180

    G = ox.graph_from_place(
        city,
        network_type="drive",
        simplify=True
    )

    return G