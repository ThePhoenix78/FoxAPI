
_images_relations: dict = {
    "5": "StaticBase1",
    "6": "StaticBase2",
    "7": "StaticBase3",
    "8": "ForwardBase1",
    "9": "ForwardBase2",
    "10": "ForwardBase3",
    "11": "Hospital",
    "12": "VehicleFactory",
    "13": "Armory",
    "14": "SupplyStation",
    "15": "Workshop",
    "16": "ManufacturingPlant",
    "17": "Refinery",
    "18": "Shipyard",
    "19": "TechCenter",
    "20": "SalvageField",
    "21": "ComponentField",
    "22": "FuelField",
    "23": "SulfurField",
    "24": "WorldMapTent",
    "25": "TravelTent",
    "26": "TrainingArea",
    "27": "SpecialBase",
    "28": "ObservationTower",
    "29": "Fort",
    "30": "TroopShip",
    "32": "SulfurMine",
    "33": "StorageFacility",
    "34": "Factory",
    "35": "GarrisonStation",
    "36": "AmmoFactory",
    "37": "RocketSite",
    "38": "SalvageMine",
    "39": "ConstructionYard",
    "40": "ComponentMine",
    "41": "OilWell",
    "45": "RelicBase1",
    "46": "RelicBase2",
    "47": "RelicBase3",
    "51": "MassProductionFactory",
    "52": "Seaport",
    "53": "CoastalGun",
    "54": "SoulFactory",
    "56": "TownBase1",
    "57": "TownBase2",
    "58": "TownBase3",
    "59": "StormCannon",
    "60": "IntelCenter",
    "61": "CoalField",
    "62": "OilField",
    "70": "RocketTarget",
    "71": "RocketGroundZero",
    "72": "RocketSiteWithRocket",
    "75": "FacilityMineOilRig",
    "83": "WeatherStation",
    "84": "MortarHouse",
    "88": "AircraftDepot",
    "89": "AircraftFactory",
    "90": "AircraftRadar",
    "91": "AircraftRunwayT1",
    "92": "AircraftRunwayT2"
}

_map_flags: dict = {
    "0x01": "IsVictoryBase",
    "0x02": "IsHomeBase",
    "0x04": "IsBuildSite",
    "0x10": "IsScorched",
    "0x20": "IsTownClaimed"
}

class EndpointError(Exception):
    pass


class HexagonError(Exception):
    pass


class FoxAPIError(Exception):
    pass


class Task:
    def __init__(self, function: callable, args: any = "no_args", result: any = None):
        self.function: callable = function
        self.args: any = args
        self.result: any = result


class APIResponse:
    def __init__(self, headers: dict, json: dict, status_code: int, hexagon: str, is_cache: bool):
        self.headers: dict = headers
        self.json: dict = json
        self.status_code: int = status_code
        self.hexagon: str = hexagon
        self.is_cache: bool = is_cache


class HexagonObject:
    def __init__(self, hexagon: str, war_report, static, dynamic, captured_towns: dict, casualty_rate: dict):
        self.hexagon: str = hexagon
        self.war_report = war_report
        self.static = static
        self.dynamic = dynamic
        self.captured_towns: dict = captured_towns
        self.casualty_rate: dict = casualty_rate