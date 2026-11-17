try:
    from .utils import HexagonObject, FoxAPIError, HexagonError, EndpointError, APIResponse, Task
    from .objects import WarObject, WarReportObject, SDObject
except ImportError:
    from utils import HexagonObject, FoxAPIError, HexagonError, EndpointError, APIResponse, Task
    from objects import WarObject, WarReportObject, SDObject

from PIL import Image, ImageChops
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import requests
import aiohttp
import asyncio
import inspect
import logging
import math
import time
import os


# hexagon shape (png) : 1024 x 888
# icon shape (png) : 48 x 48
# documentation at https://foxhole.fandom.com/wiki/War_API


logger = logging.getLogger("foxapi")


class FoxAPI():
    # the regions are computed on a grid reduced by this factor (much faster, 4 px blocks)
    _REGION_SCALE: int = 4

    def __init__(self, shard: str = "", image_dir: str = None, safe_mode: bool = True, timeout: float = 10, refresh: float = 60, workers: int = 8):
        if shard in ["", 1, "1", "-1"]:
            shard: str = "live"

        elif shard in [2, "2", "-2"]:
            shard: str = "live-2"

        elif shard in [3, "3", "-3"]:
            shard: str = "live-3"

        elif shard in ["dev", "devbranch"]:
            shard: str = "dev"

        self.base_api: str = f"https://war-service-{shard}.foxholeservices.com/api/worldconquest"
        self.session: requests.Session = requests.Session()
        self._timeout: float = timeout

        if image_dir is not None:
            self._img_dir: str = Path(image_dir)

        else:
            self._img_dir: str = os.path.join(Path(__file__).parent, "Images")

        self.cache: dict = {}
        self.cache_img: dict = {}
        self.etag: dict = {}

        # casualties baseline, kept per hexagon and renewed every _rate_period seconds
        self._death_rate_w: dict = {}
        self._death_rate_c: dict = {}
        self._death_rate_time: dict = {}
        self._rate_period: int = 3600

        self._refresh: float = 60
        self.refresh = refresh

        self._safe_mode: bool = safe_mode

        # images kept in memory (base maps, icons, regions of each hexagon)
        self._base_maps: dict = {}
        self._icon_cache: dict = {}
        self._regions_cache: dict = {}

        self.available_hexagons: list = self.get_maps_sync()
        self._available_hexagons: list = [h.lower() for h in self.available_hexagons]
        self._nb_hex: int = len(self.available_hexagons)

        self._valid_endpoints: list = self._get_valid_endpoints()

        # listener state
        self._run: bool = False
        self._lock: threading.Lock = threading.Lock()
        self._wake: threading.Event = threading.Event()
        self._listener_thread: threading.Thread = None
        self._bg_loop: asyncio.AbstractEventLoop = None

        self._to_call: dict = {}      # endpoint -> [callbacks]
        self._hex_to_call: dict = {}  # hexagon -> [callbacks]
        self.waiting_list: list = []

        # the listener keeps its own etags, so the calls made by the user can't hide an update from it
        self._listener_etag: dict = {}
        # last data seen by the listener : some endpoints (/war, /maps) have no etag
        # and always answer 200, the content is compared to detect a real change
        self._listener_seen: dict = {}

        # callback -> True if it takes the data as keyword arguments (FoxAPI 2.x style)
        self._legacy_callbacks: dict = {}

        # number of requests sent at the same time by the listener, each thread has its own session
        if not isinstance(workers, int) or workers < 1:
            raise ValueError("workers must be an integer greater than 0")

        self._workers: int = workers
        self._local: threading.local = threading.local()
        self._listener_sessions: list = []

        self._icon_size: tuple = (24, 24)

        self.img_height: int = 888
        self.img_width: int = 1024

    @property
    def refresh(self) -> float:
        """Time (in seconds) between two checks of the listener"""
        return self._refresh

    @refresh.setter
    def refresh(self, value: float):
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("refresh must be a number greater than 0")

        self._refresh = value

    def close_session(self):
        self.stop_listener()
        self.session.close()

    """
    ---------------------------------------- REQUESTS TOOLS ----------------------------------------
    """

    def _make_headers(self, endpoint: str, etag: str = None, etags: dict = None) -> dict:
        # etag == "" forces a full answer, etag is None uses the last known etag
        if etag is None:
            etag: str = (self.etag if etags is None else etags).get(endpoint)

        return {"If-None-Match": etag} if etag else {}

    def _retry_after(self, headers) -> float:
        try:
            return max(1.0, float(headers.get("Retry-After")))

        except (TypeError, ValueError):
            return max(60.0, self._refresh)

    def _json_or_raise(self, data: APIResponse, endpoint: str):
        if data.status_code not in (None, 200, 304) or data.json is None:
            raise FoxAPIError(f"The request to {endpoint} failed (HTTP status: {data.status_code})")

        return data.json

    """
    ---------------------------------------- REQUESTS SYNC ----------------------------------------
    """

    def get_data_sync(self, endpoint: str, etag: str = None, use_cache: bool = None) -> APIResponse:
        return self._fetch_sync(endpoint=endpoint, etag=etag, use_cache=use_cache, session=self.session, etags=self.etag)

    def _fetch_sync(self, endpoint: str, etag: str = None, use_cache: bool = None, session: requests.Session = None, etags: dict = None) -> APIResponse:
        hexagon: str = self._retrieve_hexagon_from_endpoint(endpoint)

        if use_cache == True:
            cached_data: dict = self.cache.get(endpoint)

            if cached_data is not None:
                return APIResponse(headers={}, json=cached_data, status_code=None, hexagon=hexagon, is_cache=True)

        headers: dict = self._make_headers(endpoint, etag, etags)

        with session.get(f"{self.base_api}{endpoint}", headers=headers, timeout=self._timeout) as data:
            etags[endpoint] = data.headers.get("ETag", etags.get(endpoint))

            if data.status_code == 200:
                data_json = data.json()
                self.cache[endpoint] = data_json
                return APIResponse(headers=data.headers, json=data_json, status_code=data.status_code, hexagon=hexagon, is_cache=False)

            elif data.status_code == 304:
                cached_data = self.cache.get(endpoint)

                if cached_data is not None or not headers:
                    return APIResponse(headers=data.headers, json=cached_data, status_code=data.status_code, hexagon=hexagon, is_cache=True)

            else:
                return APIResponse(headers=data.headers, json={}, status_code=data.status_code, hexagon=hexagon, is_cache=False)

        # 304 received but nothing in the cache (custom etag) : ask for the full data
        return self._fetch_sync(endpoint=endpoint, etag="", session=session, etags=etags)

    def get_headers_sync(self, endpoint: str):
        with self.session.head(f"{self.base_api}{endpoint}", timeout=self._timeout) as data:
            return data

    """
    ---------------------------------------- REQUESTS ASYNC ----------------------------------------
    """

    async def _request(self, session: aiohttp.ClientSession, endpoint: str, headers: dict, hexagon: str) -> APIResponse:
        timeout = aiohttp.ClientTimeout(total=self._timeout)

        async with session.get(f"{self.base_api}{endpoint}", headers=headers, timeout=timeout) as data:
            self.etag[endpoint] = data.headers.get("ETag", self.etag.get(endpoint))

            if data.status == 200:
                data_json = await data.json()
                self.cache[endpoint] = data_json
                return APIResponse(headers=data.headers, json=data_json, status_code=data.status, hexagon=hexagon, is_cache=False)

            elif data.status == 304:
                cached_data = self.cache.get(endpoint)

                if cached_data is not None or not headers:
                    return APIResponse(headers=data.headers, json=cached_data, status_code=data.status, hexagon=hexagon, is_cache=True)

                # 304 received but nothing in the cache (custom etag)
                return None

            return APIResponse(headers=data.headers, json={}, status_code=data.status, hexagon=hexagon, is_cache=False)

    async def get_data(self, endpoint: str, session: aiohttp.ClientSession = None, etag: str = None, use_cache: bool = None):
        hexagon: str = self._retrieve_hexagon_from_endpoint(endpoint)

        if use_cache == True:
            cached_data: dict = self.cache.get(endpoint)

            if cached_data is not None:
                return APIResponse(headers={}, json=cached_data, status_code=None, hexagon=hexagon, is_cache=True)

        if session is None:
            async with self._session_scope() as new_session:
                return await self.get_data(endpoint=endpoint, session=new_session, etag=etag, use_cache=use_cache)

        headers: dict = self._make_headers(endpoint, etag)
        answer: APIResponse = await self._request(session=session, endpoint=endpoint, headers=headers, hexagon=hexagon)

        if answer is None:
            answer: APIResponse = await self._request(session=session, endpoint=endpoint, headers={}, hexagon=hexagon)

        return answer

    @asynccontextmanager
    async def _session_scope(self, session: aiohttp.ClientSession = None):
        # one aiohttp session shared by all the requests of a method
        if session is not None:
            yield session
            return

        async with aiohttp.ClientSession() as new_session:
            yield new_session

    async def get_headers(self, endpoint: str):
        timeout = aiohttp.ClientTimeout(total=self._timeout)

        async with aiohttp.ClientSession() as session:
            async with session.head(f"{self.base_api}{endpoint}", timeout=timeout) as data:
                return data

    """
    ---------------------------------------- URL TOOLS ----------------------------------------
    """

    def _hexagon_endpoints(self, hexagon: str) -> list:
        return [f"/warReport/{hexagon}", f"/maps/{hexagon}/dynamic/public", f"/maps/{hexagon}/static"]

    def _get_valid_endpoints(self):
        valid: list = ["/war", "/maps"]

        for hexagon in self.available_hexagons:
            valid.append(f"/maps/{hexagon}/static")
            valid.append(f"/maps/{hexagon}/dynamic/public")
            valid.append(f"/warReport/{hexagon}")

        return valid

    def _is_valid_endpoint(self, endpoint: str):
        return endpoint in self._valid_endpoints

    def _is_valid_hexagon(self, hexagon: str):
        return hexagon in self.available_hexagons

    def _format_hexagon(self, hexagon: str):
        if not isinstance(hexagon, str) or not hexagon.strip():
            raise HexagonError(f"'{hexagon}' is not a valid hexagon (FoxAPI.available_hexagons)")

        key: str = hexagon.lower().strip().replace(" ", "")

        # exact name first ("deadlandshex" or "deadlands")
        for candidate in (key, f"{key}hex"):
            if candidate in self._available_hexagons:
                return self.available_hexagons[self._available_hexagons.index(candidate)]

        # then partial name, only if there is no doubt
        matches: list = [self.available_hexagons[i] for i in range(self._nb_hex) if key in self._available_hexagons[i]]

        if len(matches) == 1:
            return matches[0]

        if not matches:
            raise HexagonError(f"'{hexagon}' is not a valid hexagon (FoxAPI.available_hexagons)")

        raise HexagonError(f"'{hexagon}' is ambiguous, it matches: {', '.join(matches)}")

    def _retrieve_hexagon_from_endpoint(self, endpoint: str) -> str:
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]

        if "maps/" in endpoint or "warReport/" in endpoint:
            return endpoint.split("/")[1]

    def _format_endpoint(self, endpoint: str) -> str:
        if "maps/" in endpoint or "warReport/" in endpoint:
            old_hexa: str = self._retrieve_hexagon_from_endpoint(endpoint)

            try:
                hexagon: str = self._format_hexagon(old_hexa)

            except HexagonError as e:
                raise EndpointError(f"{endpoint} not valid! {e}") from None

            endpoint: str = endpoint.replace(old_hexa, hexagon)

        return endpoint

    """
    ---------------------------------------- ADDITIONAL TOOLS ----------------------------------------
    """

    def calc_distance(self, p1: tuple, p2: tuple) -> float:
        return math.sqrt((abs(p1[0] - p2[0]) ** 2) + (abs(p1[1] - p2[1]) ** 2))

    def bissectrice(self, p1: tuple, p2: tuple) -> tuple:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2

        dx, dy = p2[0] - p1[0], p2[1] - p1[1]

        if dx != 0:
            slope = -dy / dx
            intercept = my - slope * mx
            return slope, intercept
        else:
            return None, mx

    def _death_rate_hexagon(self, hexagon: str = None, war_report: WarReportObject = None) -> str:
        if hexagon is None and war_report is not None:
            response = getattr(war_report, "response", None)
            hexagon: str = getattr(response, "hexagon", None)

        if hexagon is None:
            raise FoxAPIError("Please pass the required parameters (hexagon or war_report)")

        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        return hexagon

    def _calc_death_rate(self, hexagon: str, war_report: dict) -> dict[str, int]:
        war_c: int = war_report.colonialCasualties
        war_w: int = war_report.wardenCasualties

        now: float = time.monotonic()
        start: float = self._death_rate_time.get(hexagon)

        if start is None or now - start > self._rate_period:
            self._death_rate_c[hexagon] = war_c
            self._death_rate_w[hexagon] = war_w
            self._death_rate_time[hexagon] = now

        return {"colonials": war_c - self._death_rate_c[hexagon], "wardens": war_w - self._death_rate_w[hexagon], "hexagon": hexagon}

    """
    ---------------------------------------- IMAGE TOOLS ----------------------------------------
    """

    def load_hexagon_map(self, hexagon: str) -> Image:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        base: Image = self._base_maps.get(hexagon)

        if base is None:
            img_path: str = os.path.join(self._img_dir, "MapsHex", f"Map{hexagon}.png")

            with Image.open(img_path) as file:
                base = file.convert("RGBA")

            self._base_maps[hexagon] = base

        # a copy is returned so the image kept in memory is never modified
        return base.copy()

    def _get_icon(self, icon, team: str, colored: bool) -> Image:
        key: tuple = (str(icon), team if colored else None, self._icon_size)
        img = self._icon_cache.get(key)

        if img is not None:
            return img

        try:
            img_path: str = os.path.join(self._img_dir, "MapIcons", f"{icon}.png")

            with Image.open(img_path) as file:
                img = file.convert("RGBA").resize(self._icon_size)

            if colored:
                self.color_icon(image=img, team=team)

        except Exception:
            img_path: str = os.path.join(self._img_dir, "MapIcons", "DebugIcon.png")

            with Image.open(img_path) as file:
                img = file.convert("RGBA").resize(self._icon_size)

        self._icon_cache[key] = img

        return img

    def color_icon(self, image: Image, team: str = None):
        f: int = 50
        g: int = 165

        if team == "COLONIALS":
            color: tuple = (101-f, 135-f, 94-f)

        elif team == "WARDENS":
            color: tuple = (45-f, 108-f, 161-f)

        else:
            return

        # channel by channel with PIL instead of a python loop on every pixel
        red, green, blue, alpha = image.split()

        shifted: list = [
            channel.point(lambda v, c=c: max(0, min(255, v - g + c)))
            for channel, c in zip((red, green, blue), color)
        ]

        # the alpha channel is kept so the edges of the icon stay smooth
        colored = Image.merge("RGBA", (*shifted, alpha))
        visible = alpha.point(lambda v: 255 if v > 10 else 0)

        image.paste(colored, (0, 0), visible)

    def _region_labels(self, size: tuple, points: tuple) -> Image:
        """Image where each pixel holds the index of the closest town (cached, towns never move)"""
        key: tuple = (size, points)
        small = self._regions_cache.get(key)

        if small is None:
            width, height = size
            scale: int = self._REGION_SCALE
            small_w, small_h = max(1, width // scale), max(1, height // scale)

            towns: list = [(px * width, py * height) for px, py in points]
            labels: list = []

            for y in range(small_h):
                cy: float = (y + .5) * height / small_h

                for x in range(small_w):
                    cx: float = (x + .5) * width / small_w

                    closest: int = 0
                    min_distance: float = float('inf')

                    for i, (px, py) in enumerate(towns):
                        distance: float = (cx - px) ** 2 + (cy - py) ** 2

                        if distance < min_distance:
                            min_distance = distance
                            closest = i

                    labels.append(closest)

            small = Image.new("L", (small_w, small_h))
            small.putdata(labels)
            self._regions_cache[key] = small

        return small.resize(size, Image.NEAREST)

    def color_regions(self, image: Image, dynamic: SDObject, static: SDObject):
        captured_towns: dict = self.get_captured_towns_sync(dynamic=dynamic, static=static)
        colors: dict = {"COLONIALS": (50, 66, 47), "WARDENS": (22, 54, 80)}

        # an "L" image can't hold more than 256 indexes
        towns: list = [p for p in static.mapTextItems if p.mapMarkerType == "Major"][:256]

        if not towns:
            return

        labels: Image = self._region_labels(image.size, tuple((p.x, p.y) for p in towns))

        red, green, blue, alpha = image.split()
        visible: Image = alpha.point(lambda v: 255 if v > 10 else 0)
        halves: list = [channel.point(lambda v: v // 2) for channel in (red, green, blue)]

        for team, color in colors.items():
            table: list = [255 if i < len(towns) and captured_towns.get(towns[i].text) == team else 0 for i in range(256)]
            mask: Image = labels.point(table)

            if mask.getbbox() is None:
                continue

            mask = ImageChops.multiply(mask, visible)

            colored = Image.merge("RGBA", [
                *(channel.point(lambda v, c=c: min(255, v + c)) for channel, c in zip(halves, color)),
                alpha
            ])

            image.paste(colored, (0, 0), mask)

    def add_icons(self, image: Image, icons: str | list, dynamic: SDObject, colored: bool = True):
        icon_size: tuple = self._icon_size

        if icons != "all":
            if isinstance(icons, (str, int)):
                icons: list = [icons]

            icons: list[str] = [str(i) for i in icons]

        for data in dynamic.mapItems:
            icon: str = data.iconType
            team: str = data.teamId.strip()

            if icons != "all" and str(icon) not in icons:
                continue

            img2: Image = self._get_icon(icon=icon, team=team, colored=colored)

            # the icon is centered on the position of the item
            position: tuple = (int(data.x * self.img_width) - icon_size[0] // 2, int(data.y * self.img_height) - icon_size[1] // 2)
            image.paste(img2, position, mask=img2)

    def associate_towns(self, dynamic: SDObject, static: SDObject) -> dict:
        captured_towns: dict = {}
        icons: list = [45, 46, 47, 56, 57, 58] # Town halls and relics

        bases: list = [d for d in dynamic.mapItems if d.iconType in icons]

        for s in static.mapTextItems:
            if s.mapMarkerType != 'Major':
                continue

            if not bases:
                captured_towns[s.text] = "NONE"
                continue

            closest = min(bases, key=lambda d: self.calc_distance((s.x, s.y), (d.x, d.y)))
            captured_towns[s.text] = closest.teamId

        return captured_towns

    def _map_cache_key(self, hexagon: str, icons: str | list, colored: bool) -> tuple:
        if not icons:
            icons_key = None

        elif isinstance(icons, (str, int)):
            icons_key = str(icons)

        else:
            icons_key = tuple(sorted(str(i) for i in icons))

        return (hexagon, icons_key, bool(colored))

    def _map_stamp(self, dynamic: SDObject = None):
        # identifies the state of the data used to draw the map
        if dynamic is None:
            return "static"

        last_updated = getattr(dynamic, "lastUpdated", None)

        if last_updated is None:
            return None

        return (last_updated, getattr(dynamic, "version", None))

    def _map_cache_lookup(self, key: tuple, stamp, force: bool = False):
        if force or stamp is None:
            return None

        cached = self.cache_img.get(key)

        if cached is not None and cached[0] == stamp:
            return cached[1].copy()

    def _map_cache_store(self, key: tuple, stamp, image: Image):
        if stamp is not None:
            self.cache_img[key] = (stamp, image.copy())

    def _render_map(self, hexagon: str, icons: str | list, colored: bool, dynamic: SDObject, static: SDObject) -> Image:
        img: Image = self.load_hexagon_map(hexagon)

        if colored:
            self.color_regions(image=img, dynamic=dynamic, static=static)

        if icons:
            self.add_icons(image=img, icons=icons, dynamic=dynamic, colored=colored)

        return img

    """
    ---------------------------------------- ASYNC METHODS ----------------------------------------
    """

    async def get_maps(self, use_cache: bool = True, session: aiohttp.ClientSession | None = None) -> list[str]:
        data: APIResponse = await self.get_data(endpoint="/maps", use_cache=use_cache, session=session)
        return self._json_or_raise(data, "/maps")

    async def get_war(self, use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> WarObject:
        data: APIResponse = await self.get_data(endpoint="/war", use_cache=use_cache, session=session)
        return WarObject(**self._json_or_raise(data, "/war"), response=data)

    async def get_static(self, hexagon: str, use_cache: bool = True, session: aiohttp.ClientSession | None = None) -> SDObject:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        endpoint: str = f"/maps/{hexagon}/static"
        data: APIResponse = await self.get_data(endpoint=endpoint, use_cache=use_cache, session=session)
        return SDObject(**self._json_or_raise(data, endpoint), response=data)

    async def get_dynamic(self, hexagon: str, use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> SDObject:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        endpoint: str = f"/maps/{hexagon}/dynamic/public"
        data: APIResponse = await self.get_data(endpoint=endpoint, use_cache=use_cache, session=session)
        return SDObject(**self._json_or_raise(data, endpoint), response=data)

    async def get_war_report(self, hexagon: str, use_cache: bool = None, session: aiohttp.ClientSession | None = None) -> WarReportObject:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        endpoint: str = f"/warReport/{hexagon}"
        data: APIResponse = await self.get_data(endpoint=endpoint, use_cache=use_cache, session=session)
        return WarReportObject(**self._json_or_raise(data, endpoint), response=data)

    """
    ---------------------------------------- ADDITIONAL ASYNC METHODS ----------------------------------------
    """

    async def get_captured_towns(self, hexagon: str = None, dynamic: SDObject = None, static: SDObject = None, session: aiohttp.ClientSession | None = None) -> dict[str, str]:
        if hexagon is not None and static is None and dynamic is None:
            async with self._session_scope(session) as session:
                static: SDObject = await self.get_static(hexagon, use_cache=True, session=session)
                dynamic: SDObject = await self.get_dynamic(hexagon, session=session)

        if static is None or dynamic is None:
            raise FoxAPIError("Please pass the required parameters (hexagon or (static and dynamic))")

        return self.associate_towns(dynamic=dynamic, static=static)

    async def make_map_png(self, hexagon: str, icons: str | list[int | str] = "all", colored: bool = False, dynamic: SDObject = None, static: SDObject = None, force: bool = False, session: aiohttp.ClientSession | None = None):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        need_dynamic: bool = bool(icons) or colored

        async with self._session_scope(session) as session:
            if dynamic is None and need_dynamic:
                dynamic: SDObject = await self.get_dynamic(hexagon=hexagon, session=session)

            if static is None and colored:
                static: SDObject = await self.get_static(hexagon=hexagon, use_cache=True, session=session)

        key: tuple = self._map_cache_key(hexagon, icons, colored)
        stamp = self._map_stamp(dynamic if need_dynamic else None)

        img = self._map_cache_lookup(key, stamp, force)

        if img is not None:
            return img

        # the drawing is slow, it is done in a thread to keep the event loop free
        img: Image = await asyncio.to_thread(self._render_map, hexagon, icons, colored, dynamic, static)
        self._map_cache_store(key, stamp, img)

        return img

    async def calculate_death_rate(self, hexagon: str = None, war_report: WarReportObject = None, session: aiohttp.ClientSession | None = None):
        hexagon: str = self._death_rate_hexagon(hexagon=hexagon, war_report=war_report)

        if war_report is None:
            war_report: WarReportObject = await self.get_war_report(hexagon, session=session)

        return self._calc_death_rate(hexagon=hexagon, war_report=war_report)

    async def get_hexagon_data(self, hexagon: str, use_cache: bool = None, session: aiohttp.ClientSession | None = None):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        async with self._session_scope(session) as session:
            war_report: WarReportObject = await self.get_war_report(hexagon=hexagon, use_cache=use_cache, session=session)
            static: SDObject = await self.get_static(hexagon=hexagon, use_cache=True, session=session)
            dynamic: SDObject = await self.get_dynamic(hexagon=hexagon, use_cache=use_cache, session=session)

        captured_towns: dict = await self.get_captured_towns(dynamic=dynamic, static=static, session=session)
        casualty_rate: dict = await self.calculate_death_rate(hexagon=hexagon, war_report=war_report, session=session)

        return HexagonObject(hexagon=hexagon, war_report=war_report, static=static, dynamic=dynamic, captured_towns=captured_towns, casualty_rate=casualty_rate)

    """
    ---------------------------------------- SYNC METHODS ----------------------------------------
    """

    def get_maps_sync(self, use_cache: bool = True) -> list[str]:
        data: APIResponse = self.get_data_sync(endpoint="/maps", use_cache=use_cache)
        return self._json_or_raise(data, "/maps")

    def get_war_sync(self, use_cache: bool = None) -> WarObject:
        data: APIResponse = self.get_data_sync(endpoint="/war", use_cache=use_cache)
        return WarObject(**self._json_or_raise(data, "/war"), response=data)

    def get_static_sync(self, hexagon: str, use_cache: bool = True) -> SDObject:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        endpoint: str = f"/maps/{hexagon}/static"
        data: APIResponse = self.get_data_sync(endpoint=endpoint, use_cache=use_cache)
        return SDObject(**self._json_or_raise(data, endpoint), response=data)

    def get_dynamic_sync(self, hexagon: str, use_cache: bool = None) -> SDObject:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        endpoint: str = f"/maps/{hexagon}/dynamic/public"
        data: APIResponse = self.get_data_sync(endpoint=endpoint, use_cache=use_cache)
        return SDObject(**self._json_or_raise(data, endpoint), response=data)

    def get_war_report_sync(self, hexagon: str, use_cache: bool = None) -> WarReportObject:
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        endpoint: str = f"/warReport/{hexagon}"
        data: APIResponse = self.get_data_sync(endpoint=endpoint, use_cache=use_cache)
        return WarReportObject(**self._json_or_raise(data, endpoint), response=data)

    """
    ---------------------------------------- ADDITIONAL SYNC METHODS ----------------------------------------
    """

    def get_captured_towns_sync(self, hexagon: str = None, dynamic: SDObject = None, static: SDObject = None) -> dict[str, str]:
        if hexagon is not None and static is None and dynamic is None:
            static: SDObject = self.get_static_sync(hexagon, use_cache=True)
            dynamic: SDObject = self.get_dynamic_sync(hexagon)

        if static is None or dynamic is None:
            raise FoxAPIError("Please pass the required parameters (static and dynamic or hexagon)")

        return self.associate_towns(dynamic=dynamic, static=static)

    def make_map_png_sync(self, hexagon: str, icons: str | list[int | str] = "all", colored: bool = False, dynamic: SDObject = None, static: SDObject = None, force: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        need_dynamic: bool = bool(icons) or colored

        if dynamic is None and need_dynamic:
            dynamic: SDObject = self.get_dynamic_sync(hexagon=hexagon)

        if static is None and colored:
            static: SDObject = self.get_static_sync(hexagon=hexagon, use_cache=True)

        key: tuple = self._map_cache_key(hexagon, icons, colored)
        stamp = self._map_stamp(dynamic if need_dynamic else None)

        img = self._map_cache_lookup(key, stamp, force)

        if img is not None:
            return img

        img: Image = self._render_map(hexagon, icons, colored, dynamic, static)
        self._map_cache_store(key, stamp, img)

        return img

    def calculate_death_rate_sync(self, hexagon: str = None, war_report: WarReportObject = None):
        hexagon: str = self._death_rate_hexagon(hexagon=hexagon, war_report=war_report)

        if war_report is None:
            war_report: WarReportObject = self.get_war_report_sync(hexagon)

        return self._calc_death_rate(hexagon=hexagon, war_report=war_report)

    def get_hexagon_data_sync(self, hexagon: str, use_cache: bool = None):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        war_report: WarReportObject = self.get_war_report_sync(hexagon=hexagon, use_cache=use_cache)
        static: SDObject = self.get_static_sync(hexagon=hexagon, use_cache=True)
        dynamic: SDObject = self.get_dynamic_sync(hexagon=hexagon, use_cache=use_cache)

        captured_towns: dict = self.get_captured_towns_sync(dynamic=dynamic, static=static)
        casualty_rate: dict = self.calculate_death_rate_sync(hexagon=hexagon, war_report=war_report)

        return HexagonObject(hexagon=hexagon, war_report=war_report, static=static, dynamic=dynamic, captured_towns=captured_towns, casualty_rate=casualty_rate)

    """
    ---------------------------------------- CRAWLER ----------------------------------------
    """

    def _uses_legacy_kwargs(self, callback: callable, answer) -> bool:
        """
        FoxAPI 2.x called the async callbacks of on_api_update with callback(**data).
        Those callbacks (async def f(**data) or async def f(warId, warNumber, ...)) keep working.
        """
        if not isinstance(answer, dict):
            return False

        key = getattr(callback, "__func__", callback)
        legacy = self._legacy_callbacks.get(key)

        if legacy is not None:
            return legacy

        legacy = False

        try:
            signature = inspect.signature(callback)

        except (TypeError, ValueError):
            signature = None

        if signature is not None:
            positional: list = [
                p for p in signature.parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]

            var_positional: bool = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in signature.parameters.values())

            # one argument : the new way, unless this argument is one of the keys of the data
            try:
                if positional and positional[0].name in answer:
                    raise TypeError

                if not positional and not var_positional:
                    raise TypeError

                signature.bind(answer)

            except TypeError:
                try:
                    signature.bind(**answer)
                    legacy = True

                except TypeError:
                    pass

        if legacy:
            logger.warning(
                "FoxAPI: the callback %s receives the data as keyword arguments (FoxAPI 2.x style), "
                "this is deprecated : use one argument, e.g. 'async def %s(data)'",
                getattr(callback, "__name__", callback), getattr(callback, "__name__", "callback")
            )

        self._legacy_callbacks[key] = legacy

        return legacy

    def _dispatch(self, callback: callable, answer):
        # sync callbacks are called directly, async ones are sent to the background loop
        try:
            if self._uses_legacy_kwargs(callback, answer):
                call = lambda: callback(**answer)

            else:
                call = lambda: callback(answer)

            if asyncio.iscoroutinefunction(callback):
                future = asyncio.run_coroutine_threadsafe(call(), self._get_bg_loop())
                future.add_done_callback(lambda f, cb=callback: self._callback_done(f, cb))

            else:
                call()

        except Exception:
            logger.exception("FoxAPI: error in the callback %s", getattr(callback, "__name__", callback))

    def _callback_done(self, future, callback: callable):
        if future.cancelled():
            return

        error = future.exception()

        if error is not None:
            logger.error("FoxAPI: error in the callback %s", getattr(callback, "__name__", callback), exc_info=error)

    def _listener_session(self) -> requests.Session:
        # one session per worker thread : a requests.Session is not made to be shared between threads
        session: requests.Session = getattr(self._local, "session", None)

        if session is None:
            session = self._local.session = requests.Session()

            with self._lock:
                self._listener_sessions.append(session)

        return session

    def _poll(self, session: requests.Session = None, executor: ThreadPoolExecutor = None) -> float:
        """One check of every listened endpoint, returns the time to wait if the server asks to slow down"""
        with self._lock:
            api_calls: dict = {endpoint: list(callbacks) for endpoint, callbacks in self._to_call.items()}
            hex_calls: dict = {hexagon: list(callbacks) for hexagon, callbacks in self._hex_to_call.items()}

        # every endpoint is requested only once per cycle
        endpoints: list = list(api_calls)

        for hexagon in hex_calls:
            for endpoint in self._hexagon_endpoints(hexagon):
                if endpoint not in api_calls:
                    endpoints.append(endpoint)

        updated: dict = {}
        backoff: float = None
        slow_down: threading.Event = threading.Event()

        def fetch(endpoint: str):
            # nothing more is requested once the server asked to slow down
            if not self._run or slow_down.is_set():
                return endpoint, None

            try:
                # own sessions and own etags : the listener never shares its state with the user's calls
                session: requests.Session = self._listener_session() if executor is not None else own_session
                data: APIResponse = self._fetch_sync(endpoint=endpoint, session=session, etags=self._listener_etag)

            except Exception:
                logger.exception("FoxAPI: the request to %s failed", endpoint)
                return endpoint, None

            if data.status_code in (429, 503):
                slow_down.set()

            return endpoint, data

        if executor is not None:
            # several requests at the same time (max self._workers)
            results = executor.map(fetch, endpoints)

        else:
            own_session: requests.Session = session or requests.Session()
            results = map(fetch, endpoints)

        for endpoint, data in results:
            if data is None:
                continue

            if data.status_code in (429, 503):
                delay: float = self._retry_after(data.headers)
                backoff = max(backoff or 0, delay)
                logger.warning("FoxAPI: %s answered %s, next check in %.0f s", endpoint, data.status_code, delay)
                continue

            if data.status_code == 200 and not data.is_cache:
                if self._listener_seen.get(endpoint) == data.json:
                    continue

                self._listener_seen[endpoint] = data.json
                updated[endpoint] = data

        for endpoint, callbacks in api_calls.items():
            if endpoint in updated:
                for callback in callbacks:
                    self._dispatch(callback, updated[endpoint].json)

        # one call per updated hexagon, even if several of its endpoints changed
        for hexagon, callbacks in hex_calls.items():
            if not self._run:
                return None

            if not any(endpoint in updated for endpoint in self._hexagon_endpoints(hexagon)):
                continue

            try:
                answer: HexagonObject = self.get_hexagon_data_sync(hexagon=hexagon, use_cache=True)

            except Exception:
                logger.exception("FoxAPI: unable to build the data of the hexagon %s", hexagon)
                continue

            for callback in callbacks:
                self._dispatch(callback, answer)

        return backoff

    def _listener_sync(self):
        # lets the time to register every callback before the first cycle
        time.sleep(.1)

        executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="FoxAPI-request")

        try:
            while self._run:
                self._wake.clear()
                start: float = time.monotonic()

                try:
                    backoff: float = self._poll(executor=executor)

                except Exception:
                    logger.exception("FoxAPI: error in the listener")
                    backoff = None

                # fixed interval between the start of two cycles, whatever the time taken by the requests
                delay: float = max(0.0, self._refresh - (time.monotonic() - start))

                if backoff:
                    delay = max(delay, backoff)

                self._wake.wait(delay)

        finally:
            executor.shutdown(wait=True)

            with self._lock:
                sessions, self._listener_sessions = self._listener_sessions, []

            for session in sessions:
                session.close()

    def _check_listener(self):
        with self._lock:
            if self._run and self._listener_thread is not None and self._listener_thread.is_alive():
                # new callbacks are taken into account without waiting the next cycle
                self._wake.set()
                return

            self._run: bool = True
            self._wake.clear()
            self._listener_thread = threading.Thread(target=self._listener_sync, name="FoxAPI-listener")
            self._listener_thread.start()

    def stop_listener(self):
        """Stops the listener started by on_api_update / on_hexagon_update"""
        self._run: bool = False
        self._wake.set()

        loop, self._bg_loop = self._bg_loop, None

        if loop is not None:
            self.stop_async_thread(loop)

    """
    ---------------------------------------- ASYNC TOOLS ----------------------------------------
    """
    def add_task(self, function: callable, args: any = "no_args"):
        self.waiting_list.append([function, args])

    async def run_task(self):
        tasks: list = []
        answers: list = []

        # the list is emptied first, so a failing task is not executed again
        waiting_list: list = self.waiting_list
        self.waiting_list: list = []

        for function, args in waiting_list:
            if isinstance(args, str) and args == "no_args":
                tasks.append([asyncio.create_task(function()), function, args])

            elif isinstance(args, list):
                tasks.append([asyncio.create_task(function(*args)), function, args])

            elif isinstance(args, dict):
                tasks.append([asyncio.create_task(function(**args)), function, args])

            else:
                tasks.append([asyncio.create_task(function(args)), function, args])

        for task, function, args in tasks:
            answers.append(Task(function=function, args=args, result=await task))

        return answers

    def run_task_sync(self, thread: bool = False):
        if thread:
            threading.Thread(target=self._exec).start()
        else:
            return asyncio.run(self.run_task())

    def _exec(self):
        return asyncio.run(self.run_task())

    def _get_bg_loop(self):
        with self._lock:
            if self._bg_loop is None or self._bg_loop.is_closed():
                self._bg_loop = self.create_bg_loop()

            return self._bg_loop

    # https://gist.github.com/ultrafunkamsterdam/8be3d55ac45759aa1bd843ab64ce876d#file-python-3-6-asyncio-multiple-async-event-loops-in-multiple-threads-running-and-shutting-down-gracefully-py-L15
    def create_bg_loop(self):
        def to_bg(loop):
            asyncio.set_event_loop(loop)

            try:
                loop.run_forever()

            finally:
                tasks = asyncio.all_tasks(loop)

                for task in tasks:
                    task.cancel()

                if tasks:
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        new_loop = asyncio.new_event_loop()
        t = threading.Thread(target=to_bg, args=(new_loop,), name="FoxAPI-loop", daemon=True)
        t.start()

        return new_loop

    def start_async_thread(self, awaitable):
        loop = self.create_bg_loop()

        coro = asyncio.run_coroutine_threadsafe(awaitable, loop)
        return loop, coro

    def stop_async_thread(self, loop):
        loop.call_soon_threadsafe(loop.stop)

    """
     ----------------------------------------EVENT WRAPPER ----------------------------------------
    """

    def _register(self, registry: dict, keys: list, func: callable):
        # several callbacks can listen to the same endpoint / hexagon
        with self._lock:
            for key in keys:
                callbacks: list = registry.setdefault(key, [])

                if func not in callbacks:
                    callbacks.append(func)

        self._check_listener()

        return func

    def on_api_update(self, callback: callable = None, endpoints: list = None):
        if isinstance(callback, (str, list, tuple)) and endpoints is None:
            endpoints: list = callback
            callback: callable = None

        if endpoints is None:
            raise EndpointError("Please enter the endpoints to listen (FoxAPI._valid_endpoints or 'all')")

        if endpoints == "all" or list(endpoints) == ["all"]:
            endpoints: list = list(self._valid_endpoints)

        elif isinstance(endpoints, str):
            endpoints: list = [endpoints]

        else:
            endpoints: list = list(endpoints)

        if self._safe_mode:
            for i in range(len(endpoints)):
                endpoints[i] = self._format_endpoint(endpoints[i])

        for i in range(len(endpoints)):
            if not self._is_valid_endpoint(endpoints[i]):
                raise EndpointError(f"{endpoints[i]} not valid! Please enter a valid endpoint (FoxAPI._valid_endpoints)")

        def add_debug(func):
            return self._register(self._to_call, endpoints, func)

        if callable(callback):
            return add_debug(callback)

        return add_debug

    def on_hexagon_update(self, callback: callable = None, hexagons: list = "all"):
        if isinstance(callback, (str, list, tuple)):
            hexagons: str = callback
            callback: callable = None

        if hexagons is None or hexagons == "all" or list(hexagons) == ["all"]:
            hexagons: list = list(self.available_hexagons)

        elif isinstance(hexagons, str):
            hexagons: list = [hexagons]

        else:
            hexagons: list = list(hexagons)

        for i in range(len(hexagons)):
            if self._safe_mode:
                hexagons[i] = self._format_hexagon(hexagons[i])

            if not self._is_valid_hexagon(hexagons[i]):
                raise HexagonError(f"'{hexagons[i]}' is not a valid hexagon (FoxAPI.available_hexagons)")

        def add_debug(func):
            return self._register(self._hex_to_call, hexagons, func)

        if callable(callback):
            return add_debug(callback)

        return add_debug
