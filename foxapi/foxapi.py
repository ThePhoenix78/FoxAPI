try:
    from .utils import HexagonObject, FoxAPIError, HexagonError, EndpointError, APIResponse, Task
except ImportError:
    from utils import HexagonObject, FoxAPIError, HexagonError, EndpointError, APIResponse, Task

from PIL import Image
from pathlib import Path
import threading
import requests
import aiohttp
import asyncio
import math
import time
import os


# hexagon shape (png) : 1024 x 888
# icon shape (png) : 48 x 48
# documentation at https://foxhole.fandom.com/wiki/War_API


class FoxAPI():
    def __init__(self, shard: str = "", image_dir: str = None, safe_mode: bool = True):
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

        if image_dir is not None:
            self._img_dir: str = Path(image_dir)

        else:
            self._img_dir: str = os.path.join(Path(__file__).parent, "Images")

        self.cache: dict = {}
        self.etag: dict = {}

        self._death_rate_w : dict = {}
        self._death_rate_c : dict = {}

        self._refresh: int = 60
        self._cpt_rate_total: int = 3600 // self._refresh
        self._cpt_rate: int = 0

        self._safe_mode: bool = safe_mode

        self.available_hexagons: list = self.get_maps_sync()
        self._available_hexagons: list = [h.lower() for h in self.available_hexagons]
        self._nb_hex: int = len(self.available_hexagons)

        self._valid_endpoints: list = self._get_valid_endpoints()

        self._run: bool = False

        self._to_call: dict = {}
        self._hex_call: list = []
        self.waiting_list: list = []

        self._icon_size: tuple = (24, 24)

        self.img_height: int = 888
        self.img_width: int = 1024

    def close_session(self):
        self.session.close()

    """
    REQUESTS SYNC
    """

    def get_data_sync(self, endpoint: str, etag: str = None, use_cache: bool = False) -> APIResponse:
        hexagon: str = self._retrieve_hexagon_from_endpoint(endpoint)

        if use_cache == True:
            cached_data: dict = self.cache.get(endpoint)

            if cached_data is not None:
                return APIResponse(headers={}, json=cached_data, status_code=None, hexagon=hexagon, is_cache=True)

        headers: dict = {"If-None-Match": etag} if etag is not None else {"If-None-Match": self.etag.get(endpoint)}

        if self.etag.get(endpoint) is None or etag == "":
            headers: dict = {"etag": ""}

        with self.session.get(f"{self.base_api}{endpoint}", headers=headers) as data:
            self.etag[endpoint]: str = data.headers.get("ETag", self.etag.get(endpoint))

            if data.status_code == 200:
                self.cache[endpoint] = data.json()
                return APIResponse(headers=data.headers, json=data.json(), status_code=data.status_code, hexagon=hexagon, is_cache=False)

            elif data.status_code == 304:
                return APIResponse(headers=data.headers, json=self.cache.get(endpoint), status_code=data.status_code, hexagon=hexagon, is_cache=True)

            return APIResponse(headers=data.headers, json={}, status_code=data.status_code, hexagon=hexagon, is_cache=False)

    def get_headers_sync(self, endpoint: str):
        with self.session.head(f"{self.base_api}{endpoint}") as data:
            return data

    """
    REQUESTS ASYNC
    """

    async def get_data(self, endpoint: str, session: aiohttp.ClientSession = None, etag: str = None, use_cache: bool = False):
        hexagon: str = self._retrieve_hexagon_from_endpoint(endpoint)

        if use_cache == True:
            cached_data: dict = self.cache.get(endpoint)

            if cached_data is not None:
                return APIResponse(headers={}, json=cached_data, status_code=None, hexagon=hexagon, is_cache=True)

        headers: dict = {"If-None-Match": etag} if etag is not None else {"If-None-Match": self.etag.get(endpoint)}

        if self.etag.get(endpoint) is None or etag == "":
            headers: dict = {"etag": ""}

        if session is None:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_api}{endpoint}", headers=headers) as data:
                    self.etag[endpoint]: str = data.headers.get("ETag", self.etag.get(endpoint))
                    data_json = await data.json()
                    
                    if data.status == 200:
                        self.cache[endpoint] = data_json
                        return APIResponse(headers=data.headers, json=data_json, status_code=data.status, hexagon=hexagon, is_cache=False)

                    elif data.status == 304:
                        return APIResponse(headers=data.headers, json=self.cache.get(endpoint), status_code=data.status, hexagon=hexagon, is_cache=True)

                    return APIResponse(headers=data.headers, json=data_json, status_code=data.status, hexagon=hexagon, is_cache=False)
        else:
            async with session.get(f"{self.base_api}{endpoint}", headers=headers) as data:
                self.etag[endpoint]: str = data.headers.get("ETag", self.etag.get(endpoint))
                data_json: dict = await data.json()

                if data.status == 200:
                    self.cache[endpoint]: dict = data_json
                    return APIResponse(headers=data.headers, json=data_json, status_code=data.status, hexagon=hexagon, is_cache=False)

                elif data.status == 304:
                    return APIResponse(headers=data.headers, json=self.cache.get(endpoint), status_code=data.status, hexagon=hexagon, is_cache=True)

                return APIResponse(headers=data.headers, json=data_json, status_code=data.status, hexagon=hexagon, is_cache=False)

    async def get_headers(self, endpoint: str):
        async with aiohttp.ClientSession() as session:
            async with session.head(f"{self.base_api}{endpoint}") as data:
                return data

    """
    TOOLS
    """

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
        hexagon: str = hexagon.lower().strip().replace(" ", "")

        for i in range(self._nb_hex):
            if hexagon in self._available_hexagons[i]:
                return self.available_hexagons[i]

        return None

    def _retrieve_hexagon_from_endpoint(self, endpoint: str):
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]

        if "maps/" in endpoint or "warReport/" in endpoint:
            return endpoint.split("/")[1]

    def _format_endpoint(self, endpoint: str):
        if "maps/" in endpoint or "warReport/" in endpoint:
            old_hexa: str = self._retrieve_hexagon_from_endpoint(endpoint)
            hexagon: str = self._format_hexagon(old_hexa)
            endpoint: str = endpoint.replace(old_hexa, hexagon)

        return endpoint

    def calc_distance(self, p1: tuple, p2: tuple):
        return math.sqrt((abs(p1[0] - p2[0]) ** 2) + (abs(p1[1] - p2[1]) ** 2))

    def bissectrice(self, p1: tuple, p2: tuple):
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        
        if dx != 0:
            slope = -dy / dx
            intercept = my - slope * mx
            return slope, intercept
        else:
            return None, mx

    def load_hexagon_map(self, hexagon: str):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        img_path: str = os.path.join(self._img_dir, "MapsHex", f"Map{hexagon}.png")

        return Image.open(img_path).convert("RGBA")

    def color_icon(self, image: Image, team: str = None) -> Image:
        f: int = 50
        g: int = 165

        if team == "COLONIALS":
            color: tuple = (101-f, 135-f, 94-f)
        
        elif team == "WARDENS":
            color: tuple = (45-f, 108-f, 161-f)
        
        else:
            return

        width, height = image.size

        pix = image.load()

        for x in range(width):
            for y in range(height):
                p = pix[x, y]

                if p[-1] >= 10:
                    continue
                
                new_color: tuple = (p[0]-g + color[0], p[1]-g + color[1], p[2]-g + color[2])
                image.putpixel((x, y), new_color)


    def color_regions(self, image: Image, dynamic: dict, static: dict) -> Image:
        captured_towns: dict = self.get_captured_towns_sync(dynamic=dynamic, static=static)
        map_info = [data for data in static["mapTextItems"] if data["mapMarkerType"] == "Major"]
        
        for i in range(len(map_info)):
            map_info[i]["team"] = captured_towns[map_info[i]["text"]]

        points = [(p["x"] * self.img_width, p["y"] * self.img_height, p["team"]) for p in map_info]
        
        for y in range(self.img_height):
            for x in range(self.img_width):
                current_pixel = image.getpixel((x, y))
                
                if current_pixel[3] <= 10:
                    continue

                closest_point_index = None
                min_distance = float('inf')
                
                for i, point in enumerate(points):
                    distance = math.sqrt((x - point[0])**2 + (y - point[1])**2)
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_point_index = i

                if points[closest_point_index][2] == "COLONIALS":
                    color: tuple = (50, 66, 47)
                
                elif points[closest_point_index][2] == "WARDENS":
                    color: tuple = (22, 54, 80)
                
                else:
                    continue

                new_color: tuple = (current_pixel[0]//2 + color[0], current_pixel[1]//2 + color[1], current_pixel[2]//2 + color[2])
                image.putpixel((x, y), new_color)

    def add_icons(self, image: Image, dynamic: dict):
        icon_size: tuple = self._icon_size

        for data in dynamic["mapItems"]:
            icon: str = data['iconType']
            team: str = data["teamId"].strip()

            try:
                img_path: str = os.path.join(self._img_dir, "MapIcons", f"{icon}.png")
                img2 = Image.open(img_path).convert("RGBA").resize(icon_size)
                self.color_icon(img2, team=team)

            except Exception:
                img_path: str = os.path.join(self._img_dir, "MapIcons", f"DebugIcon.png")
                img2 = Image.open(img_path).convert("RGBA").resize(icon_size)

            image.paste(img2, (int(data["x"] * self.img_width), int(data["y"] * self.img_height)), mask=img2)

    """
    ASYNC METHODS
    """

    async def get_maps(self, use_cache: bool = True):
        data: APIResponse = await self.get_data(endpoint="/maps", use_cache=use_cache)
        return data.json

    async def get_war(self, use_cache: bool = False):
        data: APIResponse = await self.get_data(endpoint="/war", use_cache=use_cache)
        return data.json

    async def get_static(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        data: APIResponse = await self.get_data(endpoint=f"/maps/{hexagon}/static", use_cache=use_cache)
        return data.json

    async def get_dynamic(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        data: APIResponse = await self.get_data(endpoint=f"/maps/{hexagon}/dynamic/public", use_cache=use_cache)
        return data.json

    async def get_war_report(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        data: APIResponse = await self.get_data(endpoint=f"/warReport/{hexagon}", use_cache=use_cache)
        return data.json

    """
    ADDITIONAL ASYNC METHODS
    """

    async def get_captured_towns(self, hexagon: str = None, dynamic: dict = None, static: dict = None):
        if hexagon is not None and static is None and dynamic is None:
            static: dict = await self.get_static(hexagon, use_cache=True)
            dynamic: dict = await self.get_dynamic(hexagon)

        if static is None or dynamic is None:
            raise FoxAPIError("Please pass the required parameters (hexagon or (static and dynamic))")

        captured_towns: dict = {}
        icons: list = [45, 46, 47, 56, 57, 58] # Town halls and relics

        for s in static['mapTextItems']:
            deltas: list = []
            faction: list = []

            if s['mapMarkerType'] == 'Major':
                for d in dynamic['mapItems']:
                    if d['iconType'] in icons:
                        faction.append(d['teamId'])
                        deltas.append(self.calc_distance((s['x'], s['y']), (d['x'], d['y'])))

                captured_towns[s['text']]: str = faction[deltas.index(min(deltas))]

        return captured_towns

    async def make_map_png(self, hexagon: str, show_icons: bool = True, colored: bool = False, dynamic: dict = None, static: dict = None):
        if dynamic is None and (show_icons or colored):
            dynamic: dict = await self.get_dynamic(hexagon=hexagon)
        
        if static is None and colored:
            static: dict = await self.get_static(hexagon=hexagon, use_cache=True)

        img1: Image = self.load_hexagon_map(hexagon)

        if colored:
            self.color_regions(image=img1, dynamic=dynamic, static=static)

        if show_icons:
            self.add_icons(image=img1, dynamic=dynamic)

        return img1

    async def calculate_death_rate(self, hexagon: str = None, war_report: dict = None):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        if war_report is None:
            war_report: dict = await self.get_war_report(hexagon)

        if war_report is None:
            raise FoxAPIError("Please pass the required parameters (hexagon or war_report)")

        war_c: int = war_report['colonialCasualties']
        war_w: int = war_report['wardenCasualties']

        if self._cpt_rate > self._cpt_rate_total or not self._death_rate_c.get(hexagon):
            self._death_rate_c[hexagon]: int = war_c
            self._death_rate_w[hexagon]: int = war_w
            self._cpt_rate: int = 0

        return {"colonials": war_c - self._death_rate_c[hexagon], "wardens": war_w - self._death_rate_w[hexagon], "hexagon": hexagon}

    async def get_hexagon_data(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        war_report: dict = await self.get_war_report(hexagon=hexagon, use_cache=use_cache)
        static: dict = await self.get_static(hexagon=hexagon, use_cache=use_cache)
        dynamic: dict = await self.get_dynamic(hexagon=hexagon, use_cache=use_cache)

        captured_towns: dict = await self.get_captured_towns(dynamic=dynamic, static=static)
        casualty_rate: dict = await self.calculate_death_rate(hexagon=hexagon, war_report=war_report)
        
        return HexagonObject(hexagon=hexagon, war_report=war_report, static=static, dynamic=dynamic, captured_towns=captured_towns, casualty_rate=casualty_rate)

    """
    SYNC METHODS
    """

    def get_maps_sync(self, use_cache: bool = True):
        return self.get_data_sync(endpoint="/maps", use_cache=use_cache).json

    def get_war_sync(self, use_cache: bool = False):
        return self.get_data_sync(endpoint="/war", use_cache=use_cache).json

    def get_static_sync(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        return self.get_data_sync(endpoint=f"/maps/{hexagon}/static", use_cache=use_cache).json

    def get_dynamic_sync(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        return self.get_data_sync(endpoint=f"/maps/{hexagon}/dynamic/public", use_cache=use_cache).json

    def get_war_report_sync(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon)

        return self.get_data_sync(endpoint=f"/warReport/{hexagon}", use_cache=use_cache).json

    """
    ADDITIONAL SYNC METHODS
    """

    def get_captured_towns_sync(self, hexagon: str = None, dynamic: dict = None, static: dict = None):
        if hexagon is not None and static is None and dynamic is None:
            static: dict = self.get_static_sync(hexagon, use_cache=True)
            dynamic: dict = self.get_dynamic_sync(hexagon)

        if static is None or dynamic is None:
            raise FoxAPIError("Please pass the required parameters (static and dynamic or hexagon)")

        captured_towns: dict = {}
        icons: list = [45, 46, 47, 56, 57, 58] # Town halls and relics

        for s in static['mapTextItems']:
            deltas: list = []
            faction: list = []

            if s['mapMarkerType'] == 'Major':
                for d in dynamic['mapItems']:
                    if d['iconType'] in icons:
                        faction.append(d['teamId'])
                        deltas.append(self.calc_distance((s['x'], s['y']), (d['x'], d['y'])))

                captured_towns[s['text']]: str = faction[deltas.index(min(deltas))]

        return captured_towns

    def make_map_png_sync(self, hexagon: str, show_icons: bool = True, colored: bool = False, dynamic: dict = None, static: dict = None):
        if dynamic is None and (show_icons or colored):
            dynamic: dict = self.get_dynamic_sync(hexagon=hexagon)
        
        if static is None and colored:
            static: dict = self.get_static_sync(hexagon=hexagon, use_cache=True)

        img1: Image = self.load_hexagon_map(hexagon)
        
        if colored:
            self.color_regions(image=img1, dynamic=dynamic, static=static)

        if show_icons:
            self.add_icons(image=img1, dynamic=dynamic)

        return img1

    def calculate_death_rate_sync(self, hexagon: str = None, war_report: dict = None):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        if war_report is None:
            war_report: dict = self.get_war_report_sync(hexagon)

        if war_report is None:
            raise FoxAPIError("Please pass the required parameters (hexagon or war_report)")

        war_c: int = war_report['colonialCasualties']
        war_w: int = war_report['wardenCasualties']

        dph_c: int = war_c
        dph_w: int  = war_w

        if self._cpt_rate > self._cpt_rate_total or not self._death_rate_c.get(hexagon):
            self._death_rate_c[hexagon]: int = war_c
            self._death_rate_w[hexagon]: int = war_w
            self._cpt_rate: int = 0

        return {"colonials": dph_c - self._death_rate_c[hexagon], "wardens": dph_w - self._death_rate_w[hexagon], "hexagon": hexagon}

    def get_hexagon_data_sync(self, hexagon: str, use_cache: bool = False):
        if self._safe_mode:
            hexagon: str = self._format_hexagon(hexagon=hexagon)

        war_report: dict = self.get_war_report_sync(hexagon=hexagon, use_cache=use_cache)
        static: dict = self.get_static_sync(hexagon=hexagon, use_cache=use_cache)
        dynamic: dict = self.get_dynamic_sync(hexagon=hexagon, use_cache=use_cache)

        captured_towns: dict = self.get_captured_towns_sync(dynamic=dynamic, static=static)
        casualty_rate: dict = self.calculate_death_rate_sync(hexagon=hexagon, war_report=war_report)

        return HexagonObject(hexagon=hexagon, war_report=war_report, static=static, dynamic=dynamic, captured_towns=captured_towns, casualty_rate=casualty_rate)

    """
    CRAWLER ASYNC
    """

    async def _listener(self):
        await asyncio.sleep(.1)

        while self._run:
            for url, callback in self._to_call.items():
                data = self.get_data_sync(endpoint=url)

                if data.is_cache == False:
                    answer: dict = data.json

                    if url in self._hex_call:
                        answer: HexagonObject = self.get_hexagon_data_sync(hexagon=data.hexagon, use_cache=True)

                    self.waiting_list.append([callback, answer])

            await self.run_task()
            self._cpt_rate += 1
            await asyncio.sleep(self._refresh)

    """
    CRAWLER SYNC
    """

    def _listener_sync(self):
        time.sleep(.1)

        while self._run:
            for url, callback in self._to_call.items():
                data: int = self.get_data_sync(endpoint=url)

                if data.is_cache == False:
                    answer: dict = data.json

                    if url in self._hex_call:
                        answer: HexagonObject = self.get_hexagon_data_sync(hexagon=data.hexagon, use_cache=True)

                    callback(answer)

            self._cpt_rate += 1
            time.sleep(self._refresh)

    def _check_listener(self, run_async: bool = True):
        if not self._run:
            self._run: bool = True
            # threading.Thread(target=self._listener).start()
            if run_async:
                self.start_async_thread(self._listener())
            else:
                threading.Thread(target=self._listener_sync).start()
            # threading.Thread(target=self.start_async_thread).start()

    """
    ASYNC TOOLS
    """
    def add_task(self, function: callable, args: any = "no_args"):
        self.waiting_list.append([function, args])

    async def run_task(self):
        tasks: list = []
        answers: list = []

        for function, args in self.waiting_list:
            if args == "no_args":
                tasks.append([asyncio.create_task(function()), function, args])

            elif isinstance(args, list):
                tasks.append([asyncio.create_task(function(*args)), function, args])

            elif isinstance(args, dict):
                tasks.append([asyncio.create_task(function(**args)), function, args])

            else:
                tasks.append([asyncio.create_task(function(args)), function, args])

        for task, function, args in tasks:
            answers.append(Task(function=function, args=args, result=await task))

        tasks.clear()
        self.waiting_list.clear()
        self.waiting_list: list = []

        return answers

    def run_task_sync(self, thread: bool = False):
        if thread:
            threading.Thread(target=self._exec).start()
        else:
            return asyncio.run(self.run_task())

    def _exec(self):
        return asyncio.run(self.run_task())

    # https://gist.github.com/ultrafunkamsterdam/8be3d55ac45759aa1bd843ab64ce876d#file-python-3-6-asyncio-multiple-async-event-loops-in-multiple-threads-running-and-shutting-down-gracefully-py-L15
    def create_bg_loop(self):
        def to_bg(loop):
            asyncio.set_event_loop(loop)

            try:
                loop.run_forever()

            except asyncio.CancelledError as e:
                print('CANCELLEDERROR {}'.format(e))

            finally:
                for task in asyncio.Task.all_tasks():
                    task.cancel()

                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.stop()
                loop.close()

        new_loop = asyncio.new_event_loop()
        t = threading.Thread(target=to_bg, args=(new_loop,))
        t.start()

        return new_loop

    def start_async_thread(self, awaitable):
        # old
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        threading.Thread(target=loop.run_forever).start()
        """
        # new
        loop = self.create_bg_loop()

        coro = asyncio.run_coroutine_threadsafe(awaitable, loop)
        return loop, coro

    def stop_async_thread(self, loop):
        loop.call_soon_threadsafe(loop.stop)

    """
    EVENT WRAPPER
    """

    def on_api_update(self, callback: callable = None, endpoints: list = None):
        if (isinstance(callback, str) or isinstance(callback, list)) and endpoints is None:
            endpoints: list = callback
            callback: callable = None

        if endpoints == "all" or endpoints == ["all"]:
            endpoints: list = self._valid_endpoints

        elif isinstance(endpoints, str):
            endpoints: list = [endpoints]

        if self._safe_mode:
            for i in range(len(endpoints)):
                endpoints[i]: str = self._format_endpoint(endpoints[i])

        for i in range(len(endpoints)):
            if not self._is_valid_endpoint(endpoints[i]):
                raise EndpointError(f"{endpoints[i]} not valid! Please enter a valid endpoint (FoxAPI._valid_endpoints)")

        def add_debug(func):
            self._check_listener(asyncio.iscoroutinefunction(func))

            for endpoint in endpoints:
                self._to_call[endpoint]: callable = func

            return func

        if callable(callback):
            return add_debug(callback)

        return add_debug

    def on_hexagon_update(self, callback: callable = None, hexagons: list = "all"):
        if (isinstance(callback, str) or isinstance(callback, list)) and hexagons is None:
            hexagons: str = callback
            callback: callable = None

        if hexagons == "all" or hexagons == ["all"]:
            hexagons: list = self.available_hexagons

        if isinstance(hexagons, str):
            hexagons: list = [hexagons]

        if self._safe_mode:
            for i in range(len(hexagons)):
                hexagons[i]: str = self._format_hexagon(hexagons[i])

                if not self._is_valid_hexagon(hexagons[i]):
                    raise HexagonError("Please enter a valid hexagon (FoxAPi.available_hexagons")

        def add_debug(func):
            self._check_listener(asyncio.iscoroutinefunction(func))

            for hexagon in hexagons:
                ends: list = [f"/warReport/{hexagon}", f"/maps/{hexagon}/dynamic/public", f"/maps/{hexagon}/static"]

                for hexa in ends:
                    self._to_call[hexa]: callable = func
                    self._hex_call.append(hexa)

            return func

        if callable(callback):
            return add_debug(callback)

        return add_debug
