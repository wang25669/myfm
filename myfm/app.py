from flask import Flask, request, jsonify, send_from_directory
import os
import requests
import re
import urllib.parse

from music_client import NeteaseMusicClient

app = Flask(__name__, static_folder='static', static_url_path='')

SONGS_DIR = os.path.join(os.path.dirname(__file__), 'songs')
os.makedirs(SONGS_DIR, exist_ok=True)

# 初始化客户端并设置 cookie 保存路径
client = NeteaseMusicClient()
client.cookies_file = os.path.join(os.path.dirname(__file__), 'cookies.json')

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/send_captcha', methods=['POST'])
def send_captcha():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({'code': 400, 'msg': '请输入手机号'})
    
    success = client.send_captcha(phone)
    if success:
        return jsonify({'code': 200, 'msg': '验证码发送成功'})
    else:
        return jsonify({'code': 500, 'msg': '验证码发送失败，请稍后再试'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    phone = data.get('phone')
    captcha = data.get('captcha')
    
    if not phone or not captcha:
        return jsonify({'code': 400, 'msg': '手机号或验证码不能为空'})
    
    success = client.login_with_captcha(phone, captcha)
    if success:
        return jsonify({'code': 200, 'msg': '登录成功'})
    else:
        return jsonify({'code': 500, 'msg': '登录失败，请检查验证码'})

@app.route('/api/daily_songs', methods=['GET'])
def get_daily_songs():
    if not client.load_cookies():
        return jsonify({'code': 401, 'msg': '未登录或登录已过期'})
    
    songs = client.get_daily_recommend()
    if not songs:
        return jsonify({'code': 401, 'msg': '登录已过期，请重新登录'})
        
    return process_song_list(songs)

@app.route('/api/hot_songs', methods=['GET'])
def get_hot_songs():
    # 热歌榜无需登录
    songs = client.get_hot_songs()
    if not songs:
        return jsonify({'code': 500, 'msg': '获取热歌榜失败'})
        
    return process_song_list(songs)

def process_song_list(songs):
    # 提取公共的歌曲详情获取和精简逻辑
    playable_songs = []
    song_ids = [song.get('id') for song in songs[:20] if song.get('id')]
    valid_song_ids = set(song_ids)
    
    if song_ids:
        try:
            url_result = client.get_song_url_items(song_ids)
            if url_result.get('code') == 200:
                valid_song_ids = {
                    item.get('id')
                    for item in url_result.get('data', [])
                    if is_full_playable_item(item)
                }
        except Exception as e:
            print("批量检查URL异常:", e)
            
        playable_songs = [s for s in songs[:20] if s.get('id') in valid_song_ids]
        
        song_details = client.get_song_detail(song_ids)
        details_map = {s.get('id'): s for s in song_details}
        for song in playable_songs:
            song_id = song.get('id')
            if song_id in details_map:
                detail = details_map[song_id]
                if 'tags' in detail and detail['tags']:
                    song['tags'] = detail['tags']
                alia = detail.get('alia', [])
                if alia and not song.get('tags'):
                    song['tags'] = alia[:2]
                    
    simplified_songs = []
    for s in playable_songs:
        artists = s.get('artists', [])
        artist_names = ' / '.join([a.get('name', '未知') for a in artists])
        simplified_songs.append({
            'id': s.get('id'),
            'name': s.get('name', '未知'),
            'artist': artist_names,
            'album': s.get('album', {}).get('name', ''),
            'reason': s.get('reason', ''),
            'tags': s.get('tags', []),
            'picUrl': s.get('album', {}).get('picUrl', '')
        })
        
    return jsonify({'code': 200, 'data': simplified_songs})

def sanitize_filename(name):
    # 替换掉 Windows/Linux 不能作为文件名的特殊字符
    return re.sub(r'[\\/*?:"<>|]', '_', name)

def is_full_playable_item(item):
    return (
        bool(item)
        and bool(item.get('url'))
        and item.get('code') == 200
        and item.get('freeTrialInfo') is None
    )

@app.route('/api/song_url', methods=['GET'])
def get_song_url():
    song_id = request.args.get('id')
    name = request.args.get('name', '未知歌曲')
    artist = request.args.get('artist', '未知歌手')
    playback_mode = request.args.get('mode', 'proxy')
    
    if not song_id:
        return jsonify({'code': 400, 'msg': '缺少歌曲ID'})
        
    # 如果没登录，加载一下 cookie 试试，加载失败也不强制拦截，让后续 API 尝试
    is_logged_in = client.load_cookies()
    
    # 强制转换为数字
    try:
        song_id = int(song_id)
    except:
        pass
        
    # 构建安全的文件名：歌手 - 歌名 (ID).mp3
    safe_name = sanitize_filename(name)
    safe_artist = sanitize_filename(artist)
    filename = f"{safe_artist} - {safe_name} ({song_id}).mp3"
        
    # 1. 检查本地是否已经有这首歌的缓存
    local_path = os.path.join(SONGS_DIR, filename)
    
    # URL 编码文件名，避免特殊字符在 URL 传递中出问题
    encoded_filename = urllib.parse.quote(filename)
    
    # 2. 如果没有缓存，去网易云获取真实URL
    try:
        result = client.get_song_url_items([song_id])
        
        print(f"\n[DEBUG] ==== 请求歌曲 ID: {song_id} ====", flush=True)
        print(f"[DEBUG] 网易云 API 原始返回: {result}", flush=True)
        print("[DEBUG] =======================================\n", flush=True)
        
        url = None
        if result.get('code') == 200:
            data = result.get('data', [])
            if data:
                item = data[0]
                if is_full_playable_item(item):
                    url = item.get('url')
                elif item.get('freeTrialInfo') is not None:
                    print(f"[DEBUG] 歌曲 {song_id} 仅返回试听片段，已过滤", flush=True)
    except Exception as e:
        print(f"\n[DEBUG] ==== 获取歌曲 ID: {song_id} 发生异常 ====", flush=True)
        print(f"[DEBUG] 异常信息: {str(e)}", flush=True)
        print("[DEBUG] =======================================\n", flush=True)
        url = client.get_song_url(song_id)

    if url:
        url_scheme = 'https'
        if isinstance(url, str) and url.startswith('http://'):
            url_scheme = 'http'

        if playback_mode == 'direct':
            return jsonify({'code': 200, 'data': {
                'url': url,
                'source': 'direct',
                'url_scheme': url_scheme,
                'fallback_available': True
            }})

        if playback_mode == 'auto' and isinstance(url, str) and url.startswith('http://'):
            return jsonify({'code': 200, 'data': {
                'url': url,
                'source': 'direct',
                'url_scheme': 'http',
                'fallback_available': True
            }})

        if os.path.exists(local_path):
            print(f"[DEBUG] 命中本地缓存: {local_path}", flush=True)
            return jsonify({'code': 200, 'data': {
                'url': f'/api/play/{encoded_filename}',
                'source': 'proxy',
                'url_scheme': 'http',
                'fallback_available': False
            }})

        # 3. 将真实URL下载到本地 songs 文件夹
        try:
            print(f"[DEBUG] 正在下载歌曲 {song_id} 到 NAS...", flush=True)
            r = requests.get(url, stream=True, timeout=15)
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"[DEBUG] 歌曲 {filename} 下载完成！", flush=True)
            
            # 返回相对于 NAS 的直链
            return jsonify({'code': 200, 'data': {
                'url': f'/api/play/{encoded_filename}',
                'source': 'proxy',
                'url_scheme': 'http',
                'fallback_available': False
            }})
        except Exception as e:
            print(f"[DEBUG] 下载失败: {str(e)}", flush=True)
            return jsonify({'code': 500, 'msg': f'下载音频失败: {str(e)}'})
    else:
        # 获取失败
        if not is_logged_in:
            return jsonify({'code': 401, 'msg': '由于版权保护，请登录后试听'})
        return jsonify({'code': 404, 'msg': '暂无版权或获取失败'})

@app.route('/api/play/<path:filename>', methods=['GET'])
def play_song(filename):
    # Flask 内置的 send_from_directory 原生支持 HTTP Range 请求，非常适合 MediaPlayer！
    return send_from_directory(SONGS_DIR, filename)

@app.route('/api/personal_fm', methods=['GET'])
def get_personal_fm():
    if not client.load_cookies():
        return jsonify({'code': 401, 'msg': '未登录或登录已过期'})
        
    try:
        # 网易云私人FM接口
        result = client.endpoint_request('personal_fm')
        if result.get('code') == 200:
            songs = result.get('data', [])
            
            # 复用过滤不可播放歌曲的逻辑
            song_ids = [song.get('id') for song in songs if song.get('id')]
            valid_song_ids = set(song_ids)
            if song_ids:
                try:
                    url_result = client.get_song_url_items(song_ids)
                    if url_result.get('code') == 200:
                        valid_song_ids = {
                            item.get('id')
                            for item in url_result.get('data', [])
                            if is_full_playable_item(item)
                        }
                except Exception:
                    pass
            
            playable_songs = [s for s in songs if s.get('id') in valid_song_ids]
            
            simplified_songs = []
            for s in playable_songs:
                artists = s.get('artists', [])
                artist_names = ' / '.join([a.get('name', '未知') for a in artists])
                simplified_songs.append({
                    'id': s.get('id'),
                    'name': s.get('name', '未知'),
                    'artist': artist_names,
                    'album': s.get('album', {}).get('name', ''),
                    'reason': '私人FM',
                    'picUrl': s.get('album', {}).get('picUrl', '')
                })
            return jsonify({'code': 200, 'data': simplified_songs})
        else:
            return jsonify({'code': 500, 'msg': '获取私人FM失败'})
    except Exception as e:
        return jsonify({'code': 500, 'msg': str(e)})

@app.route('/api/status', methods=['GET'])
def check_status():
    endpoint_status = client.endpoint_status()
    if client.load_cookies():
        return jsonify({'code': 200, 'msg': '已登录', 'endpoint_config': endpoint_status})
    return jsonify({'code': 401, 'msg': '未登录', 'endpoint_config': endpoint_status})

@app.route('/api/admin/update_endpoints', methods=['POST'])
def update_endpoints():
    success, message = client.refresh_endpoint_config()
    status = client.endpoint_status()
    if success:
        return jsonify({'code': 200, 'msg': message, 'endpoint_config': status})
    return jsonify({'code': 500, 'msg': message, 'endpoint_config': status})

if __name__ == '__main__':
    client.start_endpoint_auto_update()
    # 监听 0.0.0.0 以便局域网/DDNS访问
    app.run(host='0.0.0.0', port=5000, debug=True)
