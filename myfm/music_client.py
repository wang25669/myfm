#!/usr/bin/env python3
"""
网易云音乐API - 支持登录获取个性化日推
实现了网易云weapi的加密逻辑
"""
import requests
import json
import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

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
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0',
            'Referer': 'https://music.163.com/',
            'Origin': 'https://music.163.com',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        self.crypto = NeteaseCrypto()
        self.cookies_file = './cookies.json'
        
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
    
    def send_captcha(self, phone):
        """发送验证码"""
        result = self.weapi_request('/sms/captcha/sent', {
            'cellphone': phone,
            'ctcode': '86'
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
        result = self.weapi_request('/login/cellphone', {
            'phone': phone,
            'captcha': captcha,
            'countrycode': '86',
            'rememberLogin': 'true'
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
        result = self.weapi_request('/v1/discovery/recommend/songs', {
            'offset': 0,
            'total': True,
            'limit': 20
        })
        
        if result.get('code') == 200:
            data = result.get('data', {})
            return data.get('dailySongs', [])
        return []

    def get_hot_songs(self):
        """获取热歌榜歌曲 (无需登录)"""
        url = 'https://music.163.com/api/playlist/detail?id=3778678'
        try:
            response = self.session.get(url, timeout=10)
            result = response.json()
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
        
        result = self.weapi_request('/v3/song/detail', {
            'c': json.dumps([{'id': int(id)} for id in ids.split(',')]),
            'ids': ids
        })
        
        if result.get('code') == 200:
            return result.get('songs', [])
        return []
    
    def get_song_url(self, song_id):
        """获取歌曲播放链接"""
        result = self.weapi_request('/song/enhance/player/url', {
            'ids': [song_id],
            'br': 320000
        })
        
        if result.get('code') == 200:
            data = result.get('data', [])
            if data:
                return data[0].get('url')
        return None
    
    def save_cookies(self):
        """保存登录状态"""
        os.makedirs(os.path.dirname(self.cookies_file) or '.', exist_ok=True)
        # 处理重复的cookie，只保留第一个
        cookies_dict = {}
        for cookie in self.session.cookies:
            if cookie.name not in cookies_dict:
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
                return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False
