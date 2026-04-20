import inspect

class FoxObject:
    pass


class FoxObject(dict):
    """
    Universal wrapper for any kind of dict item
    if the data structure change I won't have to do
    massive change in the code

    def __init__(self, dico: dict):
        for k, v in dico.items():
            if not isinstance(v, dict):
                setattr(self, k, v)
            else:
                setattr(self, k, FoxObject(v))
    """

    def __repr__(self):
        return str({k: v for k, v in self.__dict__.items()})

    def __getitem__(self, x: str | int):
        print("FoxAPI is moving toward objects for API endpoints, please start using object.attribute instead of object['attribute']")
        print("You can also use object.json['attribute'] for JSON manpulations (like saving to JSON)")

        caller = inspect.stack()[1]
        code = inspect.getsource(caller.frame).split("\n")[caller.lineno-1]

        print(f"Line using it ({caller.lineno}) : {code}")

        if isinstance(x, str):
            data = getattr(self, x)

            if isinstance(data, list):
                if data and isinstance(data[0], FoxObject):

                    if "]." not in code:
                        return [d.json for d in data]
            
            return data

    def __setitem__(self, k, v):
        setattr(self, k, v)

    def __iter__(self):
        for k, v in self.__dict__.items():
            yield str(k), v

    def items(self):
        return self.__dict__.items()
    
    @property
    def json(self):
        dico: dict = {}

        for k, v in self.__dict__.items():
            if isinstance(v, list):
                if v and isinstance(v[0], FoxObject):
                    dico[k] = [d.json for d in v]
                
                else:
                    dico[k] = v
            
            else:
                dico[k] = v

        return dico


class APIObject(FoxObject):
    def __init__(self, api_response):
        self.response = api_response
        self.json: FoxObject = FoxObject(api_response.json)


class WarObject(FoxObject):
    def __init__(self,
            warId: str,
            warNumber: int,
            winner: str,
            conquestStartTime: str,
            conquestEndTime: str,
            resistanceStartTime: str,
            scheduledConquestEndTime: str,
            requiredVictoryTowns: int,
            shortRequiredVictoryTowns: int,
            **kwargs
        ):
        
        self.warId: str = warId
        self.warNumber: int = warNumber
        self.winner: str = winner
        self.conquestStartTime: str = conquestStartTime
        self.conquestEndTime: str = conquestEndTime
        self.resistanceStartTime: str = resistanceStartTime
        self.scheduledConquestEndTime: str = scheduledConquestEndTime
        self.requiredVictoryTowns: str = requiredVictoryTowns
        self.shortRequiredVictoryTowns: str = shortRequiredVictoryTowns


class WarReportObject(FoxObject):
    def __init__(self,
            totalEnlistments: int,
            colonialCasualties: int,
            wardenCasualties: int,
            dayOfWar: int,
            version: int,
            **kwargs
        ):

        self.totalEnlistments: int = totalEnlistments
        
        self.colonialCasualties: int = colonialCasualties
        self.wardenCasualties: int = wardenCasualties
        
        self.dayOfWar: int = dayOfWar
        self.version: int = version


class MapItemsObject(FoxObject):
    def __init__(self,
            teamId: str,
            iconType: int,
            x: float,
            y: float,
            flags: int,
            viewDirection: int,
            **kwargs
        ):

        self.teamId: str = teamId
        self.iconType: int = iconType
        
        self.x: float = x
        self.y: float = y

        self.flags: int = flags
        self.viewDirection: int = viewDirection


class MapTextItemsObject(FoxObject):
    def __init__(self,
            text: str,
            x: float,
            y: float,
            mapMarkerType: str,
            **kwargs
        ):

        self.text: str = text
        self.x: float = x
        self.y: float = y
        self.mapMarkerType: str = mapMarkerType


class SDObject(FoxObject):
    def __init__(self,
            regionId: int,
            scorchedVictoryTowns: int,
            mapItems: list,
            mapItemsC: list,
            mapItemsW: list,
            mapTextItems: list,
            lastUpdated: int,
            version: int,
            **kwargs
        ):
        
        self.regionId: int = regionId
        self.scorchedVictoryTowns: int = scorchedVictoryTowns

        self.mapItems: list[MapItemsObject] = [MapItemsObject(**elem) for elem in mapItems]
        self.mapItemsC: list[MapItemsObject] = [MapItemsObject(**elem) for elem in mapItemsC]
        self.mapItemsW: list[MapItemsObject] = [MapItemsObject(**elem) for elem in mapItemsW]
        
        self.mapTextItems: list[MapTextItemsObject] = [MapTextItemsObject(**elem) for elem in mapTextItems]
        
        self.lastUpdated: int = lastUpdated
        self.version: int = version
