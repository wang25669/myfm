import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


DEFAULT_ENDPOINT_CONFIG = {
    "version": 1,
    "updated_at": "builtin",
    "endpoints": {
        "captcha_sent": {
            "type": "weapi",
            "endpoint": "/sms/captcha/sent",
            "defaults": {"ctcode": "86", "secrete": "music_middleuser_pclogin"},
        },
        "login_cellphone": {
            "type": "weapi",
            "endpoint": "/w/login/cellphone",
            "defaults": {"countrycode": "86", "remember": "true", "type": "1", "https": "true"},
        },
        "daily_recommend": {
            "type": "weapi",
            "endpoint": "/v3/discovery/recommend/songs",
            "defaults": {"afresh": "false"},
        },
        "personal_fm": {
            "type": "weapi",
            "endpoint": "/v1/radio/get",
            "defaults": {},
        },
        "song_detail": {
            "type": "weapi",
            "endpoint": "/v3/song/detail",
            "defaults": {},
        },
        "song_url_v1": {
            "type": "weapi",
            "endpoint": "/song/enhance/player/url/v1",
            "defaults": {"level": "exhigh", "encodeType": "flac"},
        },
        "song_url_legacy": {
            "type": "weapi",
            "endpoint": "/song/enhance/player/url",
            "defaults": {"br": 999000},
        },
        "playlist_detail_v6": {
            "type": "weapi",
            "endpoint": "/v6/playlist/detail",
            "defaults": {"n": 100000, "s": 8},
        },
        "hot_playlist_legacy": {
            "type": "raw_get",
            "url": "https://music.163.com/api/playlist/detail?id=3778678",
            "defaults": {},
        },
    },
}


REQUIRED_ENDPOINTS = set(DEFAULT_ENDPOINT_CONFIG["endpoints"].keys())
ALLOWED_UPDATE_HOSTS = {"raw.githubusercontent.com"}
DEFAULT_UPDATE_URL = (
    "https://raw.githubusercontent.com/wang25669/myfm/main/myfm/api_endpoints.json"
)


def utc_now_text():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EndpointConfigManager:
    def __init__(self, config_path=None, update_url=None, allowed_hosts=None):
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "api_endpoints.json")
        self.update_url = update_url or os.environ.get("MYFM_ENDPOINT_UPDATE_URL", DEFAULT_UPDATE_URL)
        self.allowed_hosts = set(allowed_hosts or ALLOWED_UPDATE_HOSTS)
        self.lock = threading.RLock()
        self.config = copy.deepcopy(DEFAULT_ENDPOINT_CONFIG)
        self.last_update = {
            "success": None,
            "time": None,
            "message": "not checked",
            "source": None,
        }
        self.load_local()

    def load_local(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                candidate = json.load(f)
            self.apply_config(candidate, source="local")
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            self.last_update = {
                "success": False,
                "time": utc_now_text(),
                "message": "local config ignored: %s" % e,
                "source": "local",
            }
            return False

    def get(self, name):
        with self.lock:
            return copy.deepcopy(self.config["endpoints"][name])

    def status(self):
        with self.lock:
            return {
                "version": self.config.get("version", "builtin"),
                "updated_at": self.config.get("updated_at", "builtin"),
                "last_update": copy.deepcopy(self.last_update),
            }

    def apply_config(self, candidate, source):
        self.validate(candidate)
        with self.lock:
            self.config = copy.deepcopy(candidate)
            self.last_update = {
                "success": True,
                "time": utc_now_text(),
                "message": "loaded",
                "source": source,
            }

    def refresh(self):
        try:
            self.ensure_allowed_update_url(self.update_url)
            response = requests.get(self.update_url, timeout=10)
            response.raise_for_status()
            candidate = response.json()
            self.validate(candidate)
            self.write_atomic(candidate)
            self.apply_config(candidate, source=self.update_url)
            return True, "接口配置已更新"
        except Exception as e:
            with self.lock:
                self.last_update = {
                    "success": False,
                    "time": utc_now_text(),
                    "message": str(e),
                    "source": self.update_url,
                }
            return False, str(e)

    def write_atomic(self, candidate):
        directory = os.path.dirname(self.config_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".api_endpoints.", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(candidate, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(temp_path, self.config_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def validate(self, candidate):
        if not isinstance(candidate, dict):
            raise ValueError("config must be an object")
        if "endpoints" not in candidate or not isinstance(candidate["endpoints"], dict):
            raise ValueError("missing endpoints")
        missing = REQUIRED_ENDPOINTS - set(candidate["endpoints"].keys())
        if missing:
            raise ValueError("missing endpoints: %s" % ", ".join(sorted(missing)))
        for name, endpoint in candidate["endpoints"].items():
            self.validate_endpoint(name, endpoint)

    def validate_endpoint(self, name, endpoint):
        if not isinstance(endpoint, dict):
            raise ValueError("%s must be an object" % name)
        request_type = endpoint.get("type")
        if request_type not in ("weapi", "raw_get"):
            raise ValueError("%s has unsupported type" % name)
        defaults = endpoint.get("defaults", {})
        if not isinstance(defaults, dict):
            raise ValueError("%s defaults must be an object" % name)
        if request_type == "weapi":
            path = endpoint.get("endpoint")
            if not isinstance(path, str) or not path.startswith("/") or "://" in path:
                raise ValueError("%s endpoint must be an absolute path" % name)
        if request_type == "raw_get":
            url = endpoint.get("url")
            if not isinstance(url, str) or not url.startswith("https://music.163.com/"):
                raise ValueError("%s raw URL must target music.163.com" % name)

    def ensure_allowed_update_url(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("update URL must use https")
        if parsed.netloc not in self.allowed_hosts:
            raise ValueError("update URL host is not allowed: %s" % parsed.netloc)
