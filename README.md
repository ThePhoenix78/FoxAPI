# FoxAPI Documentation

#### If you use the PyPi version, you might need to download manually the `Images` folder here and pass it as an argument like `fox = FoxAPI(image_dir="Images")`

## Installation
```bash
pip install foxapi
```


`FoxAPI` is a wrapper for the Official Foxhole API. It provides methods to interact with various endpoints related to maps, war data, dynamic/static map states, and more. The client supports data caching and etags natively to avoid overloading the Foxhole servers.

If you are new to the developer world (or lazy like me), it's the perfect tool!

Also, if you work with discord.py or any asynchronous API, this tool might be useful as well since it support async methods natively as well as synchronous


## Table of Contents
- [Dependencies](#dependencies)
- [Methods](#methods)
  - [API Interaction](#api-interaction)
  - [Map and War Data](#map-and-war-data)
  - [Hexagon Operations](#hexagon-operations)
  - [Listener Functions](#listener-functions)
- [Error Handling](#error-handling)
- [Objects](#Objects)
- [Example Usage](#example-usage)

## Dependencies

   ```bash
   pip install pillow requests
   ```

## Methods

### API Interaction (async)

#### Note : all of theses methods are async, to run the synchronous version, add _sync at the end (see API example)

- **get_data(endpoint: str, etag: str = None, cache: bool = False) -> requests.Response**  
  Fetches data from the specified endpoint with optional caching and ETag support.

  - Parameters:
    - `endpoint` (str): The API endpoint to call.
    - `etag` (str, optional): The ETag header for cache validation (not required since managed natively).
    - `cache` (bool, optional): Whether to use cached data (default: False).

  - Returns: The response data from the API as a requests.Response object.

### Map and War Data

- **get_maps(cache: bool = True) -> list**  
  Retrieves a list of available hexagons (maps) in the game world.

- **get_war(cache: bool = False) -> dict**  
  Retrieves the current war state (war data).

- **get_static(hexagon: str, cache: bool = False) -> dict**  
  Retrieves the static data for the specified hexagon.

- **get_dynamic(hexagon: str, cache: bool = False) -> dict**  
  Retrieves the dynamic data for the specified hexagon.

- **get_war_report(hexagon: str, cache: bool = False) -> dict**  
  Retrieves the war report for the specified hexagon.

- **get_hexagon_data(hexagon: str, cache: bool = False) -> HexagonObject**
    Retrieves all the data awailable for the specified hexagon.

### Hexagon Operations

- **await calc_distance(x1: float, y1: float, x2: float, y2: float) -> float**  
  Calculates the Euclidean distance between two points on the map.

- **await get_captured_towns(hexagon: str = None, dynamic: dict = None, static: dict = None) -> dict**
  Retrieves the captured towns for a given hexagon based on dynamic and static data.

- **load_hexagon_map(hexagon: str) -> pillow.Image**  
  Loads the PNG map for the specified hexagon.

- **make_map_png(hexagon: str, dynamic: dict = None, static: dict = None) -> pillow.Image**
  Generates a PNG image of the hexagon map with all the icons associated to each faction in their respective colors (included fields and town base). Only public data will be present.

- **calculate_death_rate(self, hexagon: str = None, war_report: dict = None): -> dict**  
    calculate the death rate between the first launch and the current one

### Listener Functions

- **on_api_update(callback: callable = None, endpoints: list = None)**  
  Registers a callback function to be called when the data for specified API endpoints is updated.

- **on_hexagon_update(callback: callable = None, hexagons: list = None)**  
  Registers a callback function to be called when the data for specified hexagons is updated.

## Error Handling

- **EndpointError**: Raised if an invalid API endpoint is used.
- **HexagonError**: Raised if an invalid hexagon is provided.
- **FoxAPIError**: A general error for issues within the FoxAPI class (e.g., missing data).


## Objects

```python
class APIResponse:
    def __init__(self, headers: dict, json: dict, status_code: int, hexagon: str, is_cache: bool):
        self.headers: dict = headers
        self.json: dict = json
        self.status_code: int = status_code
        self.hexagon: str = hexagon
        self.is_cache: bool = is_cache


class HexagonObject:
    def __init__(self, hexagon: str, war_report: dict, static: dict, dynamic: dict, captured_towns: dict, casualty_rate: dict, image: pillow.Image):
        self.hexagon: str = hexagon
        self.war_report: dict = war_report
        self.static: dict = static
        self.dynamic: dict = dynamic
        self.captured_towns: dict = captured_towns
        self.casualty_rate: dict = casualty_rate
        self.image: pillow.Image = image
```


## Example Usage

```python
from foxapi import FoxAPI

# Initialize the API client in safe mode

# if you are a developer and plane to use the exact hexagons name
# you can turn the safe_mod off, otherwise it will convert
# api calls and hexagons name into valid ones
# Ex: deadlands -> DeadLandsHex (Yes, I am *that* lazy)

fox = FoxAPI(safe_mod=False)

hexagon: str = "DeadLandsHex"

def retrieve():
    # Get the list of available hexagons (maps) and state of the current war
    maps: list = fox.get_maps_sync()
    war: dict = fox.get_war_sync()

    # Retrieve data for a specific hexagon
    dynamic_data: dict = fox.get_dynamic_sync(hexagon)
    static_data: dict = fox.get_static_sync(hexagon)
    war_report: dict = fox.get_war_report_sync(hexagon)

    # Create a map PNG for a hexagon with building informations on it
    map_image = fox.make_map_png_sync(hexagon)
    map_image.show()

    # to get all the data at once

    data: HexagonObject = fox.get_hexagon_data_sync(hexagon=hexagon, use_cache=True)

# Async equivalent

async def retrieve():
    # Get the list of available hexagons (maps) and state of the current war
    maps: list = await fox.get_maps()
    war: dict = await fox.get_war()

    # Retrieve data for a specific hexagon
    dynamic_data: dict = await fox.get_dynamic(hexagon)
    static_data: dict = await fox.get_static(hexagon)
    war_report: dict = await fox.get_war_report(hexagon)

    # Create a map PNG for a hexagon with building informations on it
    map_image = await fox.make_map_png(hexagon)
    map_image.show()

    # to get all the data at once

    data: HexagonObject = await fox.get_hexagon_data(hexagon=hexagon, use_cache=True)


# Register a callback to listen for updates on all the hexagons
# it will run forever don't worry

@on_hexagon_update("all")
def on_update(hexa: HexagonObject):
    print(f"Hexagon {hexa.hexagon} has been updated")
    hexa.image.save(f"{hexa.hexagon}.png")


# The following async code works as well

@on_hexagon_update("all")
async def on_update(hexa: HexagonObject):
    print(f"Hexagon {hexa.hexagon} has been updated")
    hexa.image.save(f"{hexa.hexagon}.png")

```
 (Yes, most of this documentation has been generated with ChatGPT, I am alone and too lazy to do that)

 #### I am not responsible for what you are doing with it
