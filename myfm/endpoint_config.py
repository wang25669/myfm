import copy
import json
import os
import re
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
API_ENHANCED_MODULE_BASE = (
    "https://raw.githubusercontent.com/NeteaseCloudMusicApiEnhanced/api-enhanced/main/module/"
)
DEFAULT_UPDATE_URL = API_ENHANCED_MODULE_BASE

API_ENHANCED_MODULES = {
    "captcha_sent": "captcha_sent.js",
    "login_cellphone": "login_cellphone.js",
    "daily_recommend": "recommend_songs.js",
    "personal_fm": "personal_fm.js",
    "song_detail": "song_detail.js",
    "song_url_v1": "song_url_v1.js",
    "song_url_legacy": "song_url.js",
    "playlist_detail_v6": "playlist_detail.js",
}


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
            if self.update_url.endswith(".json"):
                candidate = self.fetch_json_config(self.update_url)
            else:
                candidate = self.build_config_from_api_enhanced(self.update_url)
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

    def fetch_json_config(self, url):
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def build_config_from_api_enhanced(self, module_base_url):
        candidate = copy.deepcopy(DEFAULT_ENDPOINT_CONFIG)
        candidate["updated_at"] = utc_now_text()
        candidate["source"] = "api-enhanced"

        for endpoint_name, module_file in API_ENHANCED_MODULES.items():
            module_url = module_base_url.rstrip("/") + "/" + module_file
            self.ensure_allowed_update_url(module_url)
            response = requests.get(module_url, timeout=10)
            response.raise_for_status()
            module_text = response.text
            api_path = self.extract_module_url(endpoint_name, module_text)
            candidate["endpoints"][endpoint_name]["endpoint"] = self.to_weapi_endpoint(api_path)

        return candidate

    def extract_module_url(self, endpoint_name, module_text):
        # 新格式：request(`/api/xxx`, ...)
        match = re.search(r"request\s*\(\s*`([^`]+)`", module_text)
        if not match:
            # 旧格式：url: '/api/xxx'
            match = re.search(r"url\s*:\s*['\"]([^'\"]+)['\"]", module_text)
        if not match:
            raise ValueError("api-enhanced module has no url: %s" % endpoint_name)
        return match.group(1)

    def to_weapi_endpoint(self, api_path):
        if not api_path.startswith("/api/"):
            raise ValueError("api-enhanced url must start with /api/: %s" % api_path)
        return api_path[len("/api"):]

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
