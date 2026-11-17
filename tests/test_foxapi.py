"""
Offline tests of FoxAPI : the War API is replaced by a fake server.

Run them with : python -m unittest discover tests
"""
import os
import sys
import time
import asyncio
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FOXAPI_NO_VERSION_CHECK"] = "1"

import requests

import foxapi
from foxapi import FoxAPI, FoxAPIError, HexagonError, EndpointError, decode_flags


HEXES = ["DeadLandsHex", "HomeRegionC", "HomeRegionW", "MarbanHollow"]
WAR = dict(warId="abc", warNumber=1, winner="NONE", conquestStartTime=1, conquestEndTime=None,
           resistanceStartTime=None, scheduledConquestEndTime=None, requiredVictoryTowns=32,
           shortRequiredVictoryTowns=20)


def sd(items, texts, last=1):
    return dict(regionId=1, scorchedVictoryTowns=0, mapItems=items, mapItemsC=[], mapItemsW=[],
                mapTextItems=texts, lastUpdated=last, version=1)


def make_server() -> dict:
    server = {"/maps": ["1", HEXES], "/war": ["1", dict(WAR)]}

    for h in HEXES:
        server[f"/maps/{h}/static"] = ["1", sd([], [dict(text="Town", x=.5, y=.5, mapMarkerType="Major"),
                                                   dict(text="Other", x=.2, y=.8, mapMarkerType="Major")])]
        server[f"/maps/{h}/dynamic/public"] = ["1", sd([
            dict(teamId="WARDENS", iconType=56, x=.4, y=.4, flags=0x21, viewDirection=0),
            dict(teamId="COLONIALS", iconType=57, x=.2, y=.75, flags=0, viewDirection=0),
            dict(teamId="COLONIALS", iconType=11, x=.6, y=.6, flags=0, viewDirection=0),
        ], [])]
        server[f"/warReport/{h}"] = ["1", dict(totalEnlistments=5, colonialCasualties=10, wardenCasualties=20, dayOfWar=3, version=1)]

    server["/maps/HomeRegionC/dynamic/public"] = ["1", sd([], [])]  # no town hall
    return server


SERVER: dict = make_server()
STATE: dict = {"rate_limited": False, "no_etag": False}


def answer(endpoint: str, headers: dict):
    if STATE["rate_limited"]:
        return 429, {"Retry-After": "2"}, None

    if endpoint not in SERVER:
        return 404, {}, None

    etag, body = SERVER[endpoint]

    # like the real /war endpoint : no etag, always a full answer
    if STATE["no_etag"] and endpoint == "/war":
        return 200, {}, body

    if headers.get("If-None-Match") == etag:
        return 304, {"ETag": etag}, None

    return 200, {"ETag": etag}, body


class FakeResponse:
    def __init__(self, status, headers, body):
        self.status_code = self.status = status
        self.headers = headers
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeAsyncResponse(FakeResponse):
    async def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeAsyncSession:
    def get(self, url, headers=None, timeout=None):
        return FakeAsyncResponse(*answer(url.split("/worldconquest")[1], headers or {}))


def fake_get(self, url, headers=None, timeout=None):
    assert timeout is not None, "every request must have a timeout"
    return FakeResponse(*answer(url.split("/worldconquest")[1], headers or {}))


def wait_for(condition, timeout: float = 3) -> bool:
    end = time.time() + timeout

    while time.time() < end:
        if condition():
            return True
        time.sleep(.05)

    return condition()


class FoxAPITest(unittest.TestCase):
    def setUp(self):
        SERVER.clear()
        SERVER.update(make_server())
        STATE["rate_limited"] = False
        STATE["no_etag"] = False

        self.patch = mock.patch.object(requests.Session, "get", fake_get)
        self.patch.start()

        self.api = FoxAPI(refresh=.3)

    def tearDown(self):
        self.api.close_session()

        if self.api._listener_thread is not None:
            self.api._listener_thread.join(3)

        self.patch.stop()

    # ---------------------------------------- objects / tools

    def test_version_and_flags(self):
        self.assertGreater(foxapi._version_tuple("2.10.0"), foxapi._version_tuple("2.9.0"))
        self.assertEqual(decode_flags(0x21), ["IsVictoryBase", "IsTownClaimed"])
        self.assertEqual(decode_flags(None), [])

    def test_refresh_validation(self):
        with self.assertRaises(ValueError):
            self.api.refresh = 0

        self.api.refresh = 5
        self.assertEqual(self.api.refresh, 5)

    def test_war_and_cache(self):
        war = self.api.get_war_sync()
        self.assertEqual(war.warId, "abc")
        self.assertIsInstance(war.requiredVictoryTowns, int)
        self.assertEqual(war.response.status_code, 200)

        war = self.api.get_war_sync()
        self.assertTrue(war.response.is_cache)

        self.api.cache.pop("/war")
        self.assertEqual(self.api.get_data_sync("/war", etag="1").status_code, 200)

    def test_format_hexagon(self):
        self.assertEqual(self.api._format_hexagon("deadlands"), "DeadLandsHex")
        self.assertEqual(self.api._format_hexagon("Marban Hollow"), "MarbanHollow")

        for bad in ("nope", "home", None, ""):
            with self.assertRaises(HexagonError):
                self.api._format_hexagon(bad)

    def test_http_error(self):
        self.api.available_hexagons.append("GhostHex")
        self.api._available_hexagons.append("ghosthex")
        self.api._nb_hex += 1

        with self.assertRaises(FoxAPIError):
            self.api.get_war_report_sync("Ghost")

    def test_death_rate(self):
        report = self.api.get_war_report_sync("deadlands")
        self.assertEqual(self.api.calculate_death_rate_sync(war_report=report)["hexagon"], "DeadLandsHex")

        with self.assertRaises(FoxAPIError):
            self.api.calculate_death_rate_sync()

        self.api.calculate_death_rate_sync("MarbanHollow")
        SERVER["/warReport/DeadLandsHex"] = ["2", dict(totalEnlistments=5, colonialCasualties=15, wardenCasualties=20, dayOfWar=3, version=2)]
        self.assertEqual(self.api.calculate_death_rate_sync("deadlands")["colonials"], 5)

        self.api._death_rate_time["DeadLandsHex"] -= 4000
        self.assertEqual(self.api.calculate_death_rate_sync("deadlands")["colonials"], 0)
        self.assertIn("MarbanHollow", self.api._death_rate_time)

    def test_captured_towns(self):
        self.assertEqual(self.api.get_captured_towns_sync("deadlands"), {"Town": "WARDENS", "Other": "COLONIALS"})
        self.assertEqual(self.api.get_captured_towns_sync("HomeRegionC"), {"Town": "NONE", "Other": "NONE"})

    # ---------------------------------------- maps

    def test_maps(self):
        api = self.api

        plain = api.make_map_png_sync("deadlands", icons=None)
        self.assertEqual(plain.size, (1024, 888))

        again = api.make_map_png_sync("deadlands", icons=None)
        self.assertIsNot(again, plain)
        self.assertEqual(again.tobytes(), plain.tobytes())

        icons = api.make_map_png_sync("deadlands")
        self.assertNotEqual(icons.tobytes(), plain.tobytes())
        self.assertNotEqual(api.make_map_png_sync("deadlands", icons=11).tobytes(), icons.tobytes())

        start = time.time()
        colored = api.make_map_png_sync("deadlands", colored=True)
        first = time.time() - start
        self.assertNotEqual(colored.tobytes(), icons.tobytes())
        self.assertLess(first, 5, "the colored map takes too long to draw")

        # both teams are visible on the colored map
        raw = colored.resize((64, 56)).tobytes()
        pixels = {tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)}
        self.assertTrue(any(p[2] > p[1] for p in pixels if p[3] > 10), "no warden region")
        self.assertTrue(any(p[1] > p[2] for p in pixels if p[3] > 10), "no colonial region")

        start = time.time()
        cached = api.make_map_png_sync("deadlands", colored=True)
        self.assertLess(time.time() - start, .5)
        self.assertEqual(cached.tobytes(), colored.tobytes())

        # the base map kept in memory is never modified by a drawing
        self.assertEqual(api.load_hexagon_map("deadlands").tobytes(), plain.tobytes())

    def test_hexagon_data(self):
        hexa = self.api.get_hexagon_data_sync("deadlands")
        self.assertEqual(hexa.captured_towns["Town"], "WARDENS")

    # ---------------------------------------- async

    def test_async(self):
        api = self.api

        async def main():
            session = FakeAsyncSession()
            w1 = await api.get_war(session=session)
            w2 = await api.get_war(session=session)
            self.assertEqual(w1.warId, "abc")
            self.assertTrue(w2.response.is_cache)

            api.cache.pop("/war")
            self.assertEqual((await api.get_data("/war", session=session, etag="1")).status_code, 200)

            img = await api.make_map_png("deadlands", icons=None, session=session)
            self.assertEqual(img.size, (1024, 888))

            data = await api.get_hexagon_data("deadlands", session=session)
            self.assertEqual(data.hexagon, "DeadLandsHex")

            api.add_task(api.get_war, {"session": session})
            result = await api.run_task()
            self.assertEqual(result[0].result.warId, "abc")
            self.assertEqual(api.waiting_list, [])

        asyncio.run(main())

    # ---------------------------------------- events

    def test_registration_errors(self):
        with self.assertRaises(EndpointError):
            self.api.on_api_update("/maps/nope/static")

        with self.assertRaises(HexagonError):
            self.api.on_hexagon_update("nope")

    def test_rate_limit_backoff(self):
        api = self.api
        api._to_call["/war"] = [lambda data: None]
        api._run = True
        STATE["rate_limited"] = True

        self.assertEqual(api._poll(requests.Session()), 2.0)

        # same with parallel requests
        from concurrent.futures import ThreadPoolExecutor
        api._hex_to_call["DeadLandsHex"] = [lambda data: None]

        with ThreadPoolExecutor(4) as executor:
            self.assertEqual(api._poll(executor=executor), 2.0)

        api._run = False

    def test_listener_parallel_and_interval(self):
        api = self.api
        api.refresh = 1
        delay = .2
        cycles = []

        def slow_get(session, url, headers=None, timeout=None):
            time.sleep(delay)
            return fake_get(session, url, headers, timeout)

        with mock.patch.object(requests.Session, "get", slow_get):
            t0 = time.monotonic()

            @api.on_hexagon_update("all")
            def cb(data):
                cycles.append(time.monotonic())

            # 4 hexagons x 3 endpoints = 12 requests of 0.2 s : 2.4 s one by one, 0.4 s with 8 workers
            self.assertTrue(wait_for(lambda: len(cycles) >= 4, timeout=3))
            self.assertLess(cycles[0] - t0, 1.5, "the requests are not sent in parallel")
            first = time.monotonic()

            SERVER["/war"] = ["9", dict(WAR, warNumber=9)]
            ticks = []
            api.on_api_update("/war")(lambda data: ticks.append(time.monotonic()))
            self.assertTrue(wait_for(lambda: ticks, timeout=3))
            self.assertLess(ticks[0] - first, 1.5)

            api.stop_listener()

        api._listener_thread.join(5)
        self.assertFalse(api._listener_thread.is_alive())
        self.assertEqual(api._listener_sessions, [])

    def test_legacy_kwargs_callbacks(self):
        api = self.api
        got = {}

        async def new_style(data):
            got["new"] = data["warNumber"]

        async def legacy_var(**data):
            got["legacy_var"] = data["warNumber"]

        async def legacy_named(warId, warNumber, **rest):
            got["legacy_named"] = warNumber

        def sync_style(data):
            got["sync"] = data["warNumber"]

        async def any_args(*args, **kwargs):
            got["any"] = args

        for cb in (new_style, legacy_var, legacy_named, sync_style, any_args):
            api.on_api_update("/war")(cb)

        self.assertTrue(wait_for(lambda: len(got) == 5))
        self.assertEqual(got["new"], 1)
        self.assertEqual(got["legacy_var"], 1)
        self.assertEqual(got["legacy_named"], 1)
        self.assertEqual(got["sync"], 1)
        self.assertEqual(got["any"][0]["warNumber"], 1)

        # hexagon callbacks always receive one HexagonObject
        self.assertFalse(api._uses_legacy_kwargs(legacy_var, object()))

    def test_listener_without_etag(self):
        api = self.api
        STATE["no_etag"] = True
        got = []

        @api.on_api_update("/war")
        def cb(data):
            got.append(data["warNumber"])

        self.assertTrue(wait_for(lambda: got == [1]))
        time.sleep(1)
        self.assertEqual(got, [1], "the callback must not be called when nothing changed")

        SERVER["/war"] = ["1", dict(WAR, warNumber=2)]
        self.assertTrue(wait_for(lambda: got == [1, 2]))

    def test_listener(self):
        api = self.api
        got = {"sync": [], "async": [], "hex": [], "boom": 0}

        @api.on_api_update("/war")
        def cb_sync(data):
            got["sync"].append(data)

        @api.on_api_update(endpoints=["/war"])
        async def cb_async(data):
            got["async"].append(data)

        @api.on_api_update("/war")
        def cb_boom(data):
            got["boom"] += 1
            raise RuntimeError("callback failure (expected)")

        @api.on_hexagon_update("deadlands")
        def cb_hex(hexagon):
            got["hex"].append(hexagon.hexagon)

        self.assertEqual(sorted(api._hex_to_call), ["DeadLandsHex"])

        # first cycle : everything is new for the listener
        self.assertTrue(wait_for(lambda: got["sync"] and got["async"] and got["hex"]))
        time.sleep(.5)
        n_sync, n_hex = len(got["sync"]), len(got["hex"])

        # two endpoints of the hexagon change : one call only
        SERVER["/war"] = ["2", dict(WAR, warNumber=2)]
        SERVER["/warReport/DeadLandsHex"] = ["3", dict(SERVER["/warReport/DeadLandsHex"][1], version=3)]
        SERVER["/maps/DeadLandsHex/dynamic/public"] = ["3", dict(SERVER["/maps/DeadLandsHex/dynamic/public"][1], version=3)]

        self.assertTrue(wait_for(lambda: len(got["sync"]) > n_sync))
        self.assertEqual(got["sync"][-1]["warNumber"], 2)
        self.assertTrue(wait_for(lambda: got["async"][-1]["warNumber"] == 2))
        time.sleep(.5)
        self.assertEqual(len(got["hex"]), n_hex + 1)
        self.assertTrue(got["boom"] >= 1 and api._listener_thread.is_alive())

        # an update fetched by the user first must still reach the listener
        SERVER["/war"] = ["3", dict(WAR, warNumber=3)]
        self.assertEqual(api.get_war_sync().warNumber, 3)
        self.assertTrue(wait_for(lambda: got["sync"][-1]["warNumber"] == 3))

        api.stop_listener()
        api._listener_thread.join(3)
        self.assertFalse(api._listener_thread.is_alive())


if __name__ == "__main__":
    unittest.main()
