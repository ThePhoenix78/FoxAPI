
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
    "75": "FacilityMineOilRig"
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
    def __init__(self, hexagon: str, war_report: dict, static: dict, dynamic: dict, captured_towns: dict, casualty_rate: dict, image):
        self.hexagon: str = hexagon
        self.war_report: dict = war_report
        self.static: dict = static
        self.dynamic: dict = dynamic
        self.captured_towns: dict = captured_towns
        self.casualty_rate: dict = casualty_rate
        self.image = image


class FoxObject:
    """
    Universal wrapper for any kind of dict item
    if the data structure change I won't have to do
    massive change in the code
    """
    def __init__(self, dico: dict):
        for k, v in dico.items():
            if not isinstance(v, dict):
                setattr(self, k, v)
            else:
                setattr(self, k, FoxObject(v))

    def __repr__(self):
        return str({k: v for k, v in self.__dict__.items()})

    def __getitem__(self, x: str | int):
        if isinstance(x, str):
            return getattr(self, x)

    def __setitem__(self, k, v):
        setattr(self, k, v)

    def items(self):
        return self.__dict__.items()


class APIObject:
    def __init__(self, api_response: APIResponse):
        self.response: APIResponse = api_response
        self.json: FoxObject = FoxObject(api_response.json)

    def __repr__(self):
        return str({k: v for k, v in self.json.__dict__.items()})

    def __getitem__(self, x: str | int):
        if isinstance(x, str):
            return getattr(self.json, x)

    def __setitem__(self, k, v):
        setattr(self.json, k, v)

    def items(self):
        return self.json.__dict__.items()
