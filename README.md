# FoxAPI Documentation

### Join our discord : https://discord.gg/XJJkuDYZXw

## Installation
```bash
pip install foxapi
```


`FoxAPI` is a wrapper for the Official Foxhole API. It provides methods to interact with various endpoints related to maps, war data, dynamic/static map states, and more. The client supports data caching and etags natively to avoid overloading the Foxhole servers.

If you are new to the developer world or just like coding, it's the perfect tool!

Also, if you work with discord.py or any asynchronous API, this tool might be useful as well since it support async methods natively as well as synchronous


## Table of Contents
- [FoxAPI Documentation](#foxapi-documentation)
    - [Join our discord : https://discord.gg/XJJkuDYZXw](#join-our-discord--httpsdiscordggxjjkudyzxw)
  - [Installation](#installation)
  - [Table of Contents](#table-of-contents)
  - [Dependencies](#dependencies)
  - [Wrapper](#wrapper)
  - [Methods](#methods)
    - [API Interaction (async)](#api-interaction-async)
      - [Note : all of theses methods are async, to run the synchronous version, add \_sync at the end (see API example)](#note--all-of-theses-methods-are-async-to-run-the-synchronous-version-add-_sync-at-the-end-see-api-example)
    - [Map and War Data](#map-and-war-data)
    - [Hexagon Operations](#hexagon-operations)
    - [Listener Functions](#listener-functions)
    - [Queue Tasks](#queue-tasks)
  - [Error Handling](#error-handling)
  - [Tests](#tests)
  - [Objects](#objects)
  - [Example Usage](#example-usage)
    - [I am not responsible for what you are doing with it](#i-am-not-responsible-for-what-you-are-doing-with-it)


## Dependencies

   ```bash
   pip install pillow requests aiohttp
   ```

## Wrapper

```py
class FoxAPI(shard: str = "", image_dir: str = None, safe_mode: bool = True, timeout: float = 10, refresh: float = 60, workers: int = 8)
```

  - `timeout` (float): maximum delay in seconds of each HTTP request.
  - `refresh` (float): interval in seconds between the start of two polls of the event listener. It can also be changed through the `api.refresh` property (must be > 0).
  - `workers` (int): number of requests sent in parallel by the event listener (each thread has its own HTTP session). `ValueError` is raised if it is < 1.

### Version check

On import, FoxAPI queries PyPI (2 s timeout) and emits a `warnings.warn` only if a newer version exists (nothing is printed anymore). Disable it with the environment variable `FOXAPI_NO_VERSION_CHECK=1`. `foxapi.check_version()` returns the latest published version.

### Map flags

```py
decode_flags(flags: int) -> list[str]
```
  - Translates the `flags` field of a map item into names (`IsVictoryBase`, `IsHomeBase`, `IsBuildSite`, `IsScorched`, `IsTownClaimed`).
  - `MAP_FLAGS` is the dictionary (integer keys) used for the translation. Both are importable from `foxapi`.


## Methods

### API Interaction (async)

#### Note : all of theses methods are async, to run the synchronous version, add _sync at the end (see API example)

```py
get_data(endpoint: str, session: aiohttp.ClientSession | None = None, etag: str = None, use_cache: bool = None) -> APIResponse
```  
  Fetches data from the specified endpoint, you can choose to use cache instead of sending a request and you can pass ETag.

  - Parameters:
    - `endpoint` (str): The API endpoint to call.
    - `session` (aiohttp.ClientSession, optional) the async session (`get_data_sync` has no `session` parameter)
    - `etag` (str, optional): The ETag header for cache validation (not required since managed natively).
    - `use_cache` (bool, optional): Whether to use cached data (default: None, i.e. no cache).

  - Returns: The response data from the API as a APIResponse object.

### Map and War Data

```py
get_maps(use_cache: bool = True, session: aiohttp.ClientSession | None = None) -> list[str]
```
 - Retrieves a list of available hexagons (maps) in the game world.

```py
get_war(use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> WarObject
```
  - Retrieves the current war state (war data).

```py
get_static(hexagon: str, use_cache: bool = True, session: aiohttp.ClientSession | None = None) -> SDObject
```

  - Retrieves the static data for the specified hexagon.

```py
get_dynamic(hexagon: str, use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> SDObject
```
  - Retrieves the dynamic data for the specified hexagon.

```py
get_war_report(hexagon: str, use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> WarReportObject
```
  - Retrieves the war report for the specified hexagon.

```py
get_hexagon_data(hexagon: str, use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> HexagonObject
```

  - Retrieves all the data awailable for the specified hexagon.

### Hexagon Operations

```py
calc_distance(p1: tuple, p2: tuple) -> float
```

  - Calculates the Euclidean distance between two points `(x, y)` on the map.

```py
get_captured_towns(hexagon: str = None, dynamic: SDObject = None, static: SDObject = None, session: aiohttp.ClientSession | None = None) -> dict
```
  - Retrieves the captured towns for a given hexagon based on dynamic and static data.

```py
load_hexagon_map(hexagon: str) -> pillow.Image
```

 - Loads the PNG map for the specified hexagon.

```py
make_map_png(hexagon: str, icons: str | list = "all", colored: bool = False, dynamic: SDObject = None, static: SDObject = None, force: bool = False, session: aiohttp.ClientSession | None = None) -> pillow.Image
```
  - Generates a PNG image of the hexagon map with all the icons associated to each faction in their respective colors (included fields and town base). Only public data will be present.
  - colored -> display each region in the team's color
  - icons -> display selected building in their team's color
  - force -> bypass the cache and generate a new map
  - the image cache takes the options (icons, colored) into account
  - region coloring is computed on a reduced grid (4 px blocks), which is much faster
  - icons are centered on their position

```py
calculate_death_rate(hexagon: str = None, war_report: WarReportObject = None, session: aiohttp.ClientSession | None = None) -> dict
```
  - calculate the death rate between the first launch and the current one
  - `calculate_death_rate(war_report=...)` works without `hexagon` (the hexagon is deduced from the report)
  - the casualties reference is renewed every hour, per hexagon

### Listener Functions

```py
on_api_update(callback: callable = None, endpoints: list = None)
```
  - Registers a callback function to be called when the data for specified API endpoints is updated.

```py
on_hexagon_update(callback: callable = None, hexagons: list = "all")
```
  - Registers a callback function to be called when the data for specified hexagons is updated.
  - `on_hexagon_update("DeadLands")` (positional) listens to that hexagon only.

```py
stop_listener()
```
  - Stops the listener started by `on_api_update` / `on_hexagon_update`.

```py
close_session()
```
  - Stops the listener too, then closes the HTTP session.

#### Events behavior

  - Several callbacks can listen to the same endpoint/hexagon.
  - Sync and async callbacks can be mixed.
  - Each callback receives a single argument: the JSON for `on_api_update`, a `HexagonObject` for `on_hexagon_update`.
    Async `on_api_update` callbacks written for FoxAPI 2.x, which received the JSON as keyword arguments
    (`async def on_war(**data)`), still work but log a deprecation warning.
  - A hexagon callback is called once per cycle even if several endpoints of the hexagon changed.
  - An exception raised in a callback is logged through the standard logger `logging.getLogger("foxapi")` and does not stop the listening.
  - If the server answers 429/503, the listener waits (`Retry-After` header) before retrying.
  - The `refresh` interval is measured between the start of two cycles: the duration of the requests does not lengthen it anymore (the requests of a cycle are sent in parallel, up to `workers` at a time).
  - A callback is only called if the content really changed since the last cycle. This is useful for `/war` and `/maps`, which the server sends without ETag.


### Queue Tasks

This library also give the possibility to queue up some sync and async methods to run them simultaneously

```py
from foxapi import FoxAPI

api = FoxAPI()

for i in range(10):
    api.add_task(function=api.get_war) # or any other method

data = api.run_task_sync()

for elem in data:
    print(elem.result)
```

```py
from foxapi import FoxAPI
import asyncio

api = FoxAPI()

async def main():
    for i in range(10):
        api.add_task(function=api.get_war) # or any other method

    data = await api.run_task()

    for elem in data:
        print(elem.result)

asyncio.run(main())
```

## Error Handling

```EndpointError```: Raised if an invalid API endpoint is used.

```HexagonError```: Raised if a hexagon name is unknown, empty or ambiguous (e.g. "home" matches both HomeRegionC and HomeRegionW).

```FoxAPIError```: Raised when a request fails (HTTP code other than 200/304, including 429); the code is in the message.

## Tests

```bash
python -m unittest discover tests
```
Tests run offline against a fake server.


## Objects

```python
class APIResponse:
    headers: dict
    json: dict
    status_code: int
    hexagon: str
    is_cache: bool


class HexagonObject:
    hexagon: str
    war_report: WarReportObject
    static: SDObject
    dynamic: SDObject
    captured_towns: dict
    casualty_rate: dict


class WarObject:
    warId: str
    warNumber: int
    winner: str
    conquestStartTime: int
    conquestEndTime: int
    resistanceStartTime: int
    scheduledConquestEndTime: int
    requiredVictoryTowns: int
    shortRequiredVictoryTowns: int
    response: APIResponse


class WarReportObject:
    totalEnlistments: int
    colonialCasualties: int
    wardenCasualties: int
    dayOfWar: int
    version: int
    response: APIResponse


class MapItemsObject:
    teamId: str
    iconType: int
    x: float
    y: float
    flags: int
    viewDirection: int


class MapTextItemsObject:
    text: str
    x: float
    y: float
    mapMarkerType: str


class SDObject:
    regionId: int
    scorchedVictoryTowns: int

    mapItems: list[MapItemsObject]
    mapItemsC: list[MapItemsObject]
    mapItemsW: list[MapItemsObject]
    mapTextItems: list[MapTextItemsObject]
    
    lastUpdated: int
    version: int
    response: APIResponse
```


## Example Usage

```python
from foxapi import FoxAPI, WarObject, WarReportObject, SDObject
from foxapi.utils import HexagonObject

# Initialize the API client in safe mode

# if you are a developer and plane to use the exact hexagons name
# you can turn the safe_mode off, otherwise it will convert
# api calls and hexagons name into valid ones
# Ex: deadlands -> DeadLandsHex (Yes, I am *that* lazy)

fox = FoxAPI(shard="1")


def function(hexagon: str = "DeadLandsHex"):
    # Get the list of available hexagons (maps) and state of the current war
    maps: list = fox.get_maps_sync()
    war: WarObject = fox.get_war_sync()

    # Retrieve data for a specific hexagon
    dynamic_data: SDObject = fox.get_dynamic_sync(hexagon)
    static_data: SDObject = fox.get_static_sync(hexagon)
    war_report: WarReportObject = fox.get_war_report_sync(hexagon)

    # Create a map PNG for a hexagon with building informations on it
    map_image = fox.make_map_png_sync(hexagon)
    map_image.show()

    # to get all the data at once

    data: HexagonObject = fox.get_hexagon_data_sync(hexagon=hexagon, use_cache=True)

# Async equivalent

async def function(hexagon: str = "DeadLandsHex"):
    # Get the list of available hexagons (maps) and state of the current war
    maps: list = await fox.get_maps()
    war: WarObject = await fox.get_war()

    # Retrieve data for a specific hexagon
    dynamic_data: SDObject = await fox.get_dynamic(hexagon)
    static_data: SDObject = await fox.get_static(hexagon)
    war_report: WarReportObject = await fox.get_war_report(hexagon)

    # Create a map PNG for a hexagon with building informations on it
    map_image = await fox.make_map_png(hexagon)
    map_image.show()

    # to get all the data at once

    data: HexagonObject = await fox.get_hexagon_data(hexagon=hexagon, use_cache=True)


# Register a callback to listen for updates on all the hexagons
# it will run forever don't worry

@fox.on_hexagon_update("all")
def on_update(hexa: HexagonObject):
    print(f"Hexagon {hexa.hexagon} has been updated")


# The following async code works as well

@fox.on_hexagon_update("all")
async def on_update(hexa: HexagonObject):
    print(f"Hexagon {hexa.hexagon} has been updated")

```

### I am not responsible for what you are doing with it
