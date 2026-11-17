# Changelog

## 3.0.0

This release fixes a crash that made every method unusable in 2.1.0, reworks the event listener
and speeds up map generation. Some behaviors changed: read **Breaking changes** before upgrading.

### Breaking changes

- **HTTP errors raise `FoxAPIError`.** `get_war`, `get_static`, `get_dynamic`, `get_war_report`, `get_maps`
  (sync and async) raise `FoxAPIError` with the HTTP status (404, 429, 503...) instead of failing with a
  `TypeError` or returning empty data. The constructor raises it too if `/maps` can't be fetched.
- **Invalid hexagon names raise `HexagonError`** (in safe mode). An unknown, empty or ambiguous name
  (`"home"` matches `HomeRegionC` and `HomeRegionW`) used to return `None` or the first partial match.
- **Async callbacks no longer block the listener.** They are scheduled on a background event loop and the
  next check does not wait for them: a slow callback can run while the next one starts.
- `on_api_update()` without endpoints raises `EndpointError` (it used to fail later with a `TypeError`).
- Missing attributes on API objects raise `AttributeError` instead of returning `None`
  (`hasattr` and `getattr(obj, name, default)` now work as expected).
- `FoxAPI.cache_img` stores `(state, image)` pairs keyed by `(hexagon, icons, colored)`.
  `make_map_png` and `load_hexagon_map` return copies of the cached images.
- `run_task` empties `waiting_list` before running the tasks: a failing task is not run again on the next call.
- Removed `APIObject` (unused). Removed the private attributes `_cpt_rate`, `_cpt_rate_total`, `_hex_call`
  and the private coroutine `_listener`; `_check_listener` no longer takes `run_async`.
- Importing the package no longer prints the version. A `warnings.warn` is emitted only when a newer version
  exists on PyPI. Set `FOXAPI_NO_VERSION_CHECK=1` to skip the check.
- Python 3.10 or newer is required (it was already the case in practice because of the `str | list` syntax).

### Deprecated

- **Async `on_api_update` callbacks should take one argument**, the JSON of the endpoint, like sync callbacks.
  In 2.x the JSON was unpacked as keyword arguments (`callback(**data)`). Those callbacks still work:
  FoxAPI detects them from their signature and logs a deprecation warning once per callback.

  ```python
  # 2.x style, still supported but deprecated
  @api.on_api_update("/war")
  async def on_war(**data): ...

  # 3.0 style
  @api.on_api_update("/war")
  async def on_war(data): ...
  ```

  A callback whose first parameter is named like a key of the data (`async def on_war(warId, warNumber, ...)`)
  is treated as 2.x style. `on_hexagon_update` callbacks are unchanged (they receive a `HexagonObject`).

### Fixed

- `FoxObject` wrapped every value as a dict, so creating any API object crashed
  (`'str' object has no attribute 'items'`).
- `on_hexagon_update("DeadLands")` (positional) listened to every hexagon.
- Sync and async callbacks can be mixed: the first registered callback no longer decides the listener mode.
- An exception in a callback or a network error no longer stops the listener; it is logged with the
  `foxapi` logger.
- The listener no longer misses updates already fetched by the user's own calls (separate ETags).
- `/war` and `/maps`, which the server sends without ETag, no longer trigger the callbacks on every check:
  callbacks run only when the content changed.
- A hexagon callback runs once per check, even when several endpoints of the hexagon changed.
- Async requests with a `session`: a `304` answer no longer crashes while reading an empty body.
- A `304` answer with nothing in the cache (custom `etag`) now fetches the full data.
- `make_map_png(icons=None)` without `colored` no longer crashes.
- The image cache takes `icons` and `colored` into account.
- `calculate_death_rate(war_report=...)` works without `hexagon`.
- The casualty baseline is renewed every hour for each hexagon (it was reset for one hexagon only).
- `associate_towns` no longer crashes on a hexagon without town hall (towns are marked `"NONE"`).
- Icons are centered on their position.
- The version check compares numbers (`2.10.0` is newer than `2.9.0`) and can no longer break the import.
- `create_bg_loop` used `asyncio.Task.all_tasks()`, removed in Python 3.9.

### Added

- `FoxAPI(timeout=10)`: timeout in seconds of every HTTP request.
- `FoxAPI(refresh=60)` and the `api.refresh` property: interval of the listener, measured between the
  start of two checks.
- `FoxAPI(workers=8)`: number of requests sent in parallel by the listener.
- `stop_listener()`; `close_session()` also stops the listener.
- The listener waits when the server answers `429` or `503` (`Retry-After` header).
- Several callbacks can listen to the same endpoint or hexagon.
- `decode_flags(flags)` and `MAP_FLAGS` to read the `flags` field of map items.
- `foxapi.check_version()`.
- `pyproject.toml` and offline tests (`python -m unittest discover tests`).

### Performance

- Colored maps: regions computed on a reduced grid (4 px blocks) and cached per hexagon, coloring done
  with PIL operations instead of a Python loop on every pixel.
- Icons are loaded and colored once per team, base maps are kept in memory.
- Async methods that make several requests share one `aiohttp` session.
- `make_map_png` (async) draws in a thread and no longer blocks the event loop.
- The listener checks all the endpoints in about 2 s instead of 14 s (parallel requests).
