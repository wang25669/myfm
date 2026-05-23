#!/usr/bin/env python3
"""
网易云音乐API - 支持登录获取个性化日推
实现了网易云weapi的加密逻辑
"""
import requests
import json
import base64
import os
import threading
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from endpoint_config import EndpointConfigManager

class NeteaseCrypto:
    """网易云加密工具"""
    
    # 网易云固定密钥
    MODULUS = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
    NONCE = '0CoJUm6Qyw8W8jud'
    PUBKEY = '010001'
    IV = '0102030405060708'
    
    @staticmethod
    def aes_encrypt(text, key):
        """AES-CBC加密"""
        # PKCS7填充
        pad_len = 16 - len(text) % 16
        text = text + chr(pad_len) * pad_len
        
        cipher = Cipher(
            algorithms.AES(key.encode('utf-8')),
            modes.CBC(NeteaseCrypto.IV.encode('utf-8')),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(text.encode('utf-8')) + encryptor.finalize()
        return base64.b64encode(ciphertext).decode('utf-8')
    
    @staticmethod
    def rsa_encrypt(text, pubkey, modulus):
        """RSA加密"""
        text = text[::-1]  # 反转字符串
        text_bytes = text.encode('utf-8')
        text_int = int.from_bytes(text_bytes, 'big')
        
        pubkey_int = int(pubkey, 16)
        modulus_int = int(modulus, 16)
        
        result = pow(text_int, pubkey_int, modulus_int)
        return format(result, 'x').zfill(256)
    
    @staticmethod
    def encrypt(params):
        """网易云weapi加密"""
        # 生成随机密钥 (16位小写字母)
        sec_key = ''.join([chr(ord('a') + (os.urandom(1)[0] % 26)) for _ in range(16)])
        
        # 第一次AES加密
        text = json.dumps(params)
        enc_text = NeteaseCrypto.aes_encrypt(text, NeteaseCrypto.NONCE)
        
        # 第二次AES加密
        enc_text = NeteaseCrypto.aes_encrypt(enc_text, sec_key)
        
        # RSA加密密钥
        enc_sec_key = NeteaseCrypto.rsa_encrypt(sec_key, NeteaseCrypto.PUBKEY, NeteaseCrypto.MODULUS)
        
        return {
            'params': enc_text,
            'encSecKey': enc_sec_key
        }

class NeteaseMusicClient:
    """网易云音乐客户端"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
            'Referer': 'https://music.163.com/',
            'Origin': 'https://music.163.com',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        self.crypto = NeteaseCrypto()
        self.cookies_file = './cookies.json'
        self.endpoint_config = EndpointConfigManager()
        self._updater_started = False
        
        # 注入风控设备信息 Cookie，配合 weapi 认证登录状态
        device_cookies = {
            'os': 'pc',
            'appver': '3.1.17.204416',
            'osver': 'Microsoft-Windows-10-Professional-build-19045-64bit',
            'channel': 'netease',
            '__remember_me': 'true',
            'ntes_kaola_ad': '1'
        }
        self.session.cookies.update(device_cookies)
        
    def weapi_request(self, endpoint, params=None):
        """调用weapi接口"""
        url = f'https://music.163.com/weapi{endpoint}'
        params = params or {}
        
        # csrf_token
        cookies = self.session.cookies.get_dict()
        params['csrf_token'] = cookies.get('__csrf', '')
        
        # 加密参数
        data = self.crypto.encrypt(params)
        
        try:
            response = self.session.post(url, data=data, timeout=15)
            return response.json()
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return {'code': -1, 'msg': str(e)}

    def endpoint_request(self, name, params=None):
        """按命名接口读取配置并发起请求。"""
        endpoint = self.endpoint_config.get(name)
        params = params or {}
        merged = dict(endpoint.get('defaults', {}))
        merged.update(params)

        request_type = endpoint.get('type')
        if request_type == 'weapi':
            return self.weapi_request(endpoint.get('endpoint'), merged)
        if request_type == 'raw_get':
            try:
                response = self.session.get(endpoint.get('url'), timeout=10)
                return response.json()
            except Exception as e:
                print(f"❌ 请求失败: {e}")
                return {'code': -1, 'msg': str(e)}
        return {'code': -1, 'msg': 'unsupported endpoint type'}

    def refresh_endpoint_config(self):
        """手动刷新接口配置。"""
        return self.endpoint_config.refresh()

    def endpoint_status(self):
        return self.endpoint_config.status()

    def start_endpoint_auto_update(self):
        """启动后台接口配置刷新任务。"""
        if os.environ.get('MYFM_DISABLE_ENDPOINT_AUTO_UPDATE') == '1':
            return False
        if self._updater_started:
            return True
        self._updater_started = True
        interval = self.get_update_interval_seconds()

        def worker():
            self.refresh_endpoint_config()
            while True:
                time.sleep(interval)
                self.refresh_endpoint_config()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return True

    def get_update_interval_seconds(self):
        try:
            hours = float(os.environ.get('MYFM_ENDPOINT_UPDATE_INTERVAL_HOURS', '24'))
            if hours <= 0:
                hours = 24
        except ValueError:
            hours = 24
        return int(hours * 3600)
    
    def send_captcha(self, phone):
        """发送验证码"""
        result = self.endpoint_request('captcha_sent', {
            'cellphone': phone,
        })

        
        if result.get('code') == 200:
            print(f"✅ 验证码已发送到 {phone}")
            print("⏰ 验证码5分钟内有效，请查收短信")
            return True
        else:
            msg = result.get('message', result.get('msg', '未知错误'))
            print(f"❌ 发送失败: {msg}")
            return False
    
    def login_with_captcha(self, phone, captcha):
        """使用验证码登录"""
        result = self.endpoint_request('login_cellphone', {
            'phone': phone,
            'captcha': captcha,
        })

        
        if result.get('code') == 200:
            profile = result.get('profile', {})
            nickname = profile.get('nickname', '用户')
            print(f"✅ 登录成功！欢迎回来，{nickname}～")
            self.save_cookies()
            return True
        else:
            msg = result.get('message', result.get('msg', '未知错误'))
            print(f"❌ 登录失败: {msg}")
            return False
    
    def get_daily_recommend(self):
        """获取每日推荐歌曲"""
        result = self.endpoint_request('daily_recommend')

        
        if result.get('code') == 200:
            data = result.get('data', {})
            return data.get('dailySongs', [])
        return []

    def get_hot_songs(self):
        """获取热歌榜歌曲 (无需登录)"""
        try:
            result = self.endpoint_request('playlist_detail_v6', {'id': 3778678})
            if result.get('code') == 200:
                playlist = result.get('playlist', {})
                track_ids = [
                    item.get('id') for item in playlist.get('trackIds', [])
                    if item.get('id')
                ][:20]
                songs = self.get_song_detail(track_ids)
                if songs:
                    return songs

            result = self.endpoint_request('hot_playlist_legacy')
            if result.get('code') == 200:
                playlist = result.get('result', {})
                return playlist.get('tracks', [])[:10]
            return []
        except Exception as e:
            print(f"❌ 获取热歌榜失败: {e}")
            return []
    
    def get_song_detail(self, song_ids):
        """获取歌曲详情（包含风格标签）"""
        if isinstance(song_ids, list):
            ids = ','.join([str(id) for id in song_ids])
        else:
            ids = str(song_ids)
        
        if not ids:
            return []

        result = self.endpoint_request('song_detail', {
            'c': json.dumps([{'id': int(id)} for id in ids.split(',')]),
            'ids': ids
        })
        
        if result.get('code') == 200:
            return result.get('songs', [])
        return []
    
    def get_song_url_items(self, song_ids):
        """优先调用新版 URL 接口，失败时回退旧版。"""
        ids = song_ids if isinstance(song_ids, list) else [song_ids]
        result = self.endpoint_request('song_url_v1', {'ids': ids})
        data = result.get('data', []) if result.get('code') == 200 else []
        if isinstance(data, list) and any(item.get('url') for item in data if isinstance(item, dict)):
            return result
        return self.endpoint_request('song_url_legacy', {'ids': ids})

    def get_song_url(self, song_id):
        """获取歌曲播放链接"""
        result = self.get_song_url_items([song_id])
        if result.get('code') == 200:
            data = result.get('data', [])
            if data:
                return data[0].get('url')
        return None
    
    def save_cookies(self):
        """保存登录状态"""
        os.makedirs(os.path.dirname(self.cookies_file) or '.', exist_ok=True)
        # 处理重复的 cookie，以后出现的域名化 Cookie 为准。
        cookies_dict = {}
        for cookie in self.session.cookies:
            cookies_dict[cookie.name] = cookie.value
        with open(self.cookies_file, 'w') as f:
            json.dump(cookies_dict, f)
        print("💾 登录状态已保存")
    
    def load_cookies(self):
        """加载登录状态"""
        try:
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
                self.session.cookies.update(cookies)
                # 重新应用设备风控 Cookie，确保 weapi 正常鉴权
                device_cookies = {
                    'os': 'pc',
                    'appver': '3.1.17.204416',
                    'osver': 'Microsoft-Windows-10-Professional-build-19045-64bit',
                    'channel': 'netease',
                    '__remember_me': 'true',
                    'ntes_kaola_ad': '1'
                }
                self.session.cookies.update(device_cookies)
                return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False
