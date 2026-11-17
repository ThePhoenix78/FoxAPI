from .foxapi import FoxAPI
from .utils import HexagonObject, FoxAPIError, HexagonError, EndpointError, APIResponse, Task, decode_flags, MAP_FLAGS, _images_relations, _map_flags
from .objects import FoxObject, WarObject, WarReportObject, SDObject, MapItemsObject, MapTextItemsObject

import os as _os
import warnings as _warnings


__title__ = 'FoxAPI'
__author__ = 'ThePhoenix78'
__license__ = 'MIT'
__copyright__ = 'Copyright 2024-2026 ThePhoenix78'
__url__ = 'https://github.com/ThePhoenix78/FoxAPI'
__newest__ = __version__ = '3.0.0'


def _version_tuple(version: str) -> tuple:
    parts: list = []

    for part in str(version).split("."):
        digits: str = ""

        for char in part:
            if not char.isdigit():
                break

            digits += char

        parts.append(int(digits) if digits else 0)

    return tuple(parts)


def check_version(timeout: float = 2) -> str:
    """Returns the newest version published on PyPI (the current one if PyPI can't be reached)"""
    import requests

    try:
        with requests.get("https://pypi.org/pypi/FoxAPI/json", timeout=timeout) as response:
            return str(response.json()["info"]["version"])

    except Exception:
        # the version check must never prevent the package from being used
        return __version__


if _os.environ.get("FOXAPI_NO_VERSION_CHECK", "").lower() not in ("1", "true", "yes"):
    __newest__ = check_version()

    if _version_tuple(__version__) < _version_tuple(__newest__):
        _warnings.warn(f"New version of {__title__} available: {__newest__} (Using {__version__})", stacklevel=2)
