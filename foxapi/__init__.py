from .foxapi import FoxAPI
from .utils import HexagonObject, FoxAPIError, HexagonError, EndpointError, APIResponse, Task

import requests, json


__title__ = 'FoxAPI'
__author__ = 'ThePhoenix78'
__license__ = 'MIT'
__copyright__ = 'Copyright 2024-2025 ThePhoenix78'
__url__ = 'https://github.com/ThePhoenix78/FoxAPI'
__newest__ = __version__ = '1.7.0'


try:
    with requests.get("https://pypi.python.org/pypi/FoxAPI/json") as response:
        __newest__ = json.loads(response.text)["info"]["version"]
except requests.RequestException:
    pass

finally:
    del json, requests

if __version__ < __newest__:
    print(f"New version of {__title__} available: {__newest__} (Using {__version__})")
else:
    print(f"version : {__version__}")