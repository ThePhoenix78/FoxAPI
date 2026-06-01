import inspect

class FoxObject:
    pass


class FoxObject(dict):
    """
    Universal wrapper for any kind of dict item
    if the data structure change I won't have to do
    massive change in the code
    """
    def __init__(self, dico: dict):

        for k, v in dico.items():
            self.__setitem__(k, v)

    def __setattr__(self, k, v):
        super().__setitem__(k, FoxObject(v))

    def __getattr__(self, k):
        return super().get(k)
        
    def __setitem__(self, k, v):
        super().__setitem__(k, FoxObject(v))


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
            response=None,
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

        self.response = response


class WarReportObject(FoxObject):
    def __init__(self,
            totalEnlistments: int,
            colonialCasualties: int,
            wardenCasualties: int,
            dayOfWar: int,
            version: int,
            response=None,
            **kwargs
        ):

        self.totalEnlistments: int = totalEnlistments
        
        self.colonialCasualties: int = colonialCasualties
        self.wardenCasualties: int = wardenCasualties
        
        self.dayOfWar: int = dayOfWar
        self.version: int = version

        self.response = response


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
            mapItems: list[MapItemsObject],
            mapItemsC: list[MapItemsObject],
            mapItemsW: list[MapItemsObject],
            mapTextItems: list[MapTextItemsObject],
            lastUpdated: int,
            version: int,
            response=None,
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

        self.response = response
