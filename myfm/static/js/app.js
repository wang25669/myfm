/**
 * 兼容 Android 4.0 的 ES5 JavaScript
 * 不使用 fetch, Promise, const/let, 箭头函数等现代特性
 */

// 简单的 Ajax 封装，替代 fetch
function ajax(method, url, data, callback, errorCallback) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    var res = JSON.parse(xhr.responseText);
                    callback(res);
                } catch (e) {
                    if (errorCallback) errorCallback(e);
                }
            } else {
                if (errorCallback) errorCallback(new Error('Network error: ' + xhr.status));
            }
        }
    };
    
    xhr.onerror = function() {
        if (errorCallback) errorCallback(new Error('Network error'));
    };
    
    if (data) {
        xhr.send(JSON.stringify(data));
    } else {
        xhr.send();
    }
}

// 缓存 DOM 节点
var dom = {
    loginPanel: document.getElementById('loginPanel'),
    songsPanel: document.getElementById('songsPanel'),
    phoneInput: document.getElementById('phoneInput'),
    captchaInput: document.getElementById('captchaInput'),
    sendCaptchaBtn: document.getElementById('sendCaptchaBtn'),
    loginBtn: document.getElementById('loginBtn'),
    loginMessage: document.getElementById('loginMessage'),
    systemMessage: document.getElementById('systemMessage'),
    refreshBtn: document.getElementById('refreshBtn'),
    updateEndpointsBtn: document.getElementById('updateEndpointsBtn'),
    loadingIndicator: document.getElementById('loadingIndicator'),
    songList: document.getElementById('songList'),
    
    // 导航按钮
    dailyBtn: document.getElementById('dailyBtn'),
    fmBtn: document.getElementById('fmBtn'),
    hotBtn: document.getElementById('hotBtn'),
    toggleLoginBtn: document.getElementById('toggleLoginBtn'),
    
    // 播放器节点
    player: document.getElementById('player'),
    audioPlayer: document.getElementById('audioPlayer'),
    playerCover: document.getElementById('playerCover'),
    playerName: document.getElementById('playerName'),
    playerArtist: document.getElementById('playerArtist'),
    playPauseBtn: document.getElementById('playPauseBtn'),
    prevBtn: document.getElementById('prevBtn'),
    nextBtn: document.getElementById('nextBtn')
};

// 状态
var state = {
    isPlaying: false,
    currentSongId: null,
    countdown: 0,
    countdownTimer: null,
    currentMode: 'hot', // 'daily', 'fm', 'hot'
    isLoggedIn: false
};

// 动态检测是否处于原生 App 环境
function checkNative() {
    return typeof window.AndroidPlayer !== 'undefined';
}

// 显示消息
function showMessage(msg, isError) {
    if (!dom.loginMessage) return;
    dom.loginMessage.textContent = msg;
    dom.loginMessage.style.color = isError ? '#ff4d4f' : '#4caf50';
}

function showSystemMessage(msg, isError) {
    if (!dom.systemMessage) return;
    dom.systemMessage.textContent = msg;
    dom.systemMessage.className = isError ? 'system-message error' : 'system-message success';
    dom.systemMessage.style.display = 'block';
}

// 自动定位到登录面板
function focusLogin() {
    dom.loginPanel.style.display = 'block';
    dom.phoneInput.focus();
    // 滚动到顶部
    window.scrollTo(0, 0);
    showMessage('请先登录账号以解锁更多功能', true);
}

// 更新导航按钮状态
function updateNavUI() {
    var btns = [dom.dailyBtn, dom.fmBtn, dom.hotBtn, dom.toggleLoginBtn];
    for (var i = 0; i < btns.length; i++) {
        btns[i].className = 'btn-nav';
    }
    
    if (state.currentMode === 'daily') dom.dailyBtn.className = 'btn-nav active';
    else if (state.currentMode === 'fm') dom.fmBtn.className = 'btn-nav active';
    else if (state.currentMode === 'hot') dom.hotBtn.className = 'btn-nav active';
    
    // 如果已登录，隐藏登录按钮和登录面板
    if (state.isLoggedIn) {
        dom.toggleLoginBtn.style.display = 'none';
        dom.loginPanel.style.display = 'none';
    } else {
        dom.toggleLoginBtn.style.display = 'table-cell';
    }
}

// 验证手机号
function isValidPhone(phone) {
    return /^1\d{10}$/.test(phone);
}

// 开始倒计时
function startCountdown() {
    state.countdown = 60;
    dom.sendCaptchaBtn.disabled = true;
    
    state.countdownTimer = setInterval(function() {
        state.countdown--;
        if (state.countdown <= 0) {
            clearInterval(state.countdownTimer);
            dom.sendCaptchaBtn.textContent = "获取验证码";
            dom.sendCaptchaBtn.disabled = false;
        } else {
            dom.sendCaptchaBtn.textContent = state.countdown + "s";
        }
    }, 1000);
}

// 发送验证码
dom.sendCaptchaBtn.onclick = function() {
    if (state.countdown > 0) return;
    
    var phone = dom.phoneInput.value.trim();
    if (!isValidPhone(phone)) {
        showMessage('请输入正确的11位手机号', true);
        return;
    }
    
    showMessage('正在发送...', false);
    dom.sendCaptchaBtn.disabled = true;
    
    ajax('POST', '/api/send_captcha', { phone: phone }, function(res) {
        if (res.code === 200) {
            showMessage('验证码已发送，请查收', false);
            startCountdown();
        } else {
            showMessage(res.msg || '发送失败', true);
            dom.sendCaptchaBtn.disabled = false;
        }
    }, function(err) {
        showMessage('网络异常，请重试', true);
        dom.sendCaptchaBtn.disabled = false;
    });
};

// 登录
dom.loginBtn.onclick = function() {
    var phone = dom.phoneInput.value.trim();
    var captcha = dom.captchaInput.value.trim();
    
    if (!isValidPhone(phone)) {
        showMessage('请输入正确的手机号', true);
        return;
    }
    if (!captcha) {
        showMessage('请输入验证码', true);
        return;
    }
    
    showMessage('正在登录...', false);
    dom.loginBtn.disabled = true;
    
    ajax('POST', '/api/login', { phone: phone, captcha: captcha }, function(res) {
        dom.loginBtn.disabled = false;
        if (res.code === 200) {
            showMessage('登录成功！', false);
            state.isLoggedIn = true;
            state.currentMode = 'fm';
            updateNavUI();
            setTimeout(function() {
                loadSongs(true);
            }, 1000);
        } else {
            showMessage(res.msg || '登录失败', true);
        }
    }, function() {
        dom.loginBtn.disabled = false;
        showMessage('网络异常，请重试', true);
    });
};

// 检查登录状态
function checkStatus() {
    ajax('GET', '/api/status', null, function(res) {
        if (res.code === 200) {
            state.isLoggedIn = true;
            state.currentMode = 'fm';
            loadSongs(true);
        } else {
            state.isLoggedIn = false;
            state.currentMode = 'hot';
            loadSongs(false);
        }
        updateNavUI();
    }, function() {
        state.isLoggedIn = false;
        state.currentMode = 'hot';
        loadSongs(false);
        updateNavUI();
    });
}

// 导航按钮点击事件
dom.dailyBtn.onclick = function() {
    if (!state.isLoggedIn) {
        focusLogin();
        return;
    }
    state.currentMode = 'daily';
    updateNavUI();
    loadSongs(false);
};

dom.fmBtn.onclick = function() {
    if (!state.isLoggedIn) {
        focusLogin();
        return;
    }
    state.currentMode = 'fm';
    updateNavUI();
    loadSongs(false);
};

dom.hotBtn.onclick = function() {
    state.currentMode = 'hot';
    updateNavUI();
    loadSongs(false);
};

dom.toggleLoginBtn.onclick = function() {
    if (dom.loginPanel.style.display === 'none') {
        dom.loginPanel.style.display = 'block';
        dom.phoneInput.focus();
    } else {
        dom.loginPanel.style.display = 'none';
    }
};

// 加载歌曲数据
function loadSongs(autoPlayFirst) {
    dom.songList.innerHTML = '';
    dom.loadingIndicator.style.display = 'block';
    
    var url = '/api/hot_songs';
    if (state.currentMode === 'daily') url = '/api/daily_songs';
    else if (state.currentMode === 'fm') url = '/api/personal_fm';
    
    ajax('GET', url, null, function(res) {
        dom.loadingIndicator.style.display = 'none';
        
        if (res.code === 200 && res.data && res.data.length > 0) {
            renderSongs(res.data);
            if (autoPlayFirst) {
                var items = dom.songList.getElementsByClassName('song-item');
                if (items.length > 0) playSongItem(items[0], items);
            }
        } else if (res.code === 401) {
            state.isLoggedIn = false;
            updateNavUI();
            if (state.currentMode !== 'hot') {
                state.currentMode = 'hot';
                loadSongs(false);
                focusLogin();
            }
        } else {
            dom.songList.innerHTML = '<li style="text-align:center;padding:20px;color:#888;">' + (res.msg || '暂无可用歌曲') + '</li>';
        }
    }, function() {
        dom.loadingIndicator.style.display = 'none';
        dom.songList.innerHTML = '<li style="text-align:center;padding:20px;color:#888;">网络错误，请点击刷新重试</li>';
    });
}

// 渲染歌曲列表
function renderSongs(songs) {
    var html = '';
    for (var i = 0; i < songs.length; i++) {
        var song = songs[i];
        
        var reasonHtml = '';
        if (song.reason) {
            reasonHtml = '<span class="song-reason">' + song.reason + '</span>';
        } else if (song.tags && song.tags.length > 0) {
            reasonHtml = '<span class="song-reason">' + song.tags[0] + '</span>';
        }
        
        // 由于不支持模板字符串，使用传统字符串拼接
        html += '<li class="song-item" ' + 
                'data-id="' + song.id + '" ' + 
                'data-name="' + escapeHtml(song.name) + '" ' + 
                'data-artist="' + escapeHtml(song.artist) + '" ' + 
                'data-cover="' + escapeHtml(song.picUrl) + '">';
        html += '<div class="song-info">';
        html += '<div class="song-name">' + escapeHtml(song.name) + '</div>';
        html += '<div class="song-meta">' + reasonHtml + escapeHtml(song.artist) + ' - ' + escapeHtml(song.album) + '</div>';
        html += '</div></li>';
    }
    
    dom.songList.innerHTML = html;
    
    // 绑定点击事件
    var items = dom.songList.getElementsByClassName('song-item');
    for (var j = 0; j < items.length; j++) {
        items[j].onclick = function() {
            playSongItem(this, items);
        };
    }
}

// 提取点击项目播放的逻辑，避免使用部分老系统不支持的 .click()
function playSongItem(element, allItems) {
    // 移除其他项的 active 类
    for (var k = 0; k < allItems.length; k++) {
        allItems[k].className = 'song-item';
    }
    element.className = 'song-item active';
    
    var id = element.getAttribute('data-id');
    var name = element.getAttribute('data-name');
    var artist = element.getAttribute('data-artist');
    var cover = element.getAttribute('data-cover');
    
    playSong(id, name, artist, cover);
}

// XSS 防护
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

// 播放歌曲
function playSong(id, name, artist, cover) {
    if (state.currentSongId === id) {
        togglePlay();
        return;
    }
    
    dom.player.style.display = 'block';
    dom.playerName.textContent = "获取链接中...";
    dom.playerArtist.textContent = artist;
    if (cover) {
        dom.playerCover.src = cover;
    }
    
    // 停止当前播放
    dom.audioPlayer.pause();
    dom.playerCover.className = 'cover';
    state.isPlaying = false;
    updatePlayBtn();
    
    var encName = encodeURIComponent(name || '未知歌曲');
    var encArtist = encodeURIComponent(artist || '未知歌手');
    ajax('GET', '/api/song_url?id=' + id + '&name=' + encName + '&artist=' + encArtist, null, function(res) {
        if (res.code === 200 && res.data && res.data.url) {
            state.currentSongId = id;
            dom.playerName.textContent = name;
            
            var audioUrl = res.data.url;
            if (audioUrl.indexOf('http') !== 0) {
                // 拼接相对路径为绝对路径，供原生 Android MediaPlayer 识别
                audioUrl = window.location.origin + audioUrl;
            }
            
            if (checkNative()) {
                // 车机 App 专属：走底层原生播放器
                showMessage("✅ [原生底盘] " + name, false);
                window.AndroidPlayer.play(audioUrl);
                state.isPlaying = true;
                updatePlayBtn();
            } else {
                // 网页专属：走 HTML5 Audio
                showMessage("⚠️ [残废网页] " + name, true);
                dom.audioPlayer.src = audioUrl;
                var playPromise = dom.audioPlayer.play();
                if (playPromise !== undefined) {
                    playPromise.catch(function(error) {
                        console.log("Auto-play was prevented");
                        state.isPlaying = false;
                        updatePlayBtn();
                    });
                }
            }
        } else if (res.code === 401) {
            dom.playerName.textContent = "请先登录";
            focusLogin();
        } else {
            dom.playerName.textContent = "暂无版权或获取失败";
        }
    }, function() {
        dom.playerName.textContent = "网络错误，获取失败";
    });
}

// 切换播放/暂停
function togglePlay() {
    if (state.isPlaying) {
        if (checkNative()) window.AndroidPlayer.pause(); // 底层触发切换
        else dom.audioPlayer.pause();
        state.isPlaying = false;
    } else {
        if (checkNative()) window.AndroidPlayer.pause(); // 底层触发切换
        else dom.audioPlayer.play();
        state.isPlaying = true;
    }
    updatePlayBtn();
}

// 更新播放按钮UI
function updatePlayBtn() {
    if (state.isPlaying) {
        dom.playPauseBtn.textContent = '❚❚';
        dom.playPauseBtn.style.fontSize = '12px'; // 调整暂停符号大小
        dom.playerCover.className = 'cover playing';
    } else {
        dom.playPauseBtn.textContent = '▶';
        dom.playPauseBtn.style.fontSize = '14px';
        dom.playerCover.className = 'cover';
    }
}

// 切换到相邻的歌曲 (direction: 1 下一首, -1 上一首)
function skipSong(direction) {
    var items = dom.songList.getElementsByClassName('song-item');
    if (items.length === 0) return;
    
    var currentIndex = -1;
    for (var i = 0; i < items.length; i++) {
        if (items[i].className.indexOf('active') !== -1) {
            currentIndex = i;
            break;
        }
    }
    
    if (currentIndex !== -1) {
        var nextIndex = currentIndex + direction;
        // 如果是最后一首
        if (nextIndex >= items.length) {
            if (state.currentMode === 'fm') {
                // FM 模式下，播放完自动拉取下一批新歌并播放第一首
                loadSongs(true);
                return;
            } else {
                // 日推模式，循环回第一首
                nextIndex = 0;
            }
        }
        if (nextIndex < 0) nextIndex = items.length - 1;
        playSongItem(items[nextIndex], items);
    } else {
        // 如果没有正在播放的，默认播放第一首
        playSongItem(items[0], items);
    }
}

// 绑定播放器事件
dom.playPauseBtn.onclick = togglePlay;

dom.prevBtn.onclick = function() { skipSong(-1); };
dom.nextBtn.onclick = function() { skipSong(1); };

dom.audioPlayer.onplay = function() {
    state.isPlaying = true;
    updatePlayBtn();
};

dom.audioPlayer.onpause = function() {
    state.isPlaying = false;
    updatePlayBtn();
};

dom.audioPlayer.onended = function() {
    state.isPlaying = false;
    updatePlayBtn();
    
    // 自动播放下一首
    skipSong(1);
};

dom.refreshBtn.onclick = function() { loadSongs(false); };

if (dom.updateEndpointsBtn) {
    dom.updateEndpointsBtn.onclick = function() {
        dom.updateEndpointsBtn.disabled = true;
        showSystemMessage('正在更新接口配置...', false);
        ajax('POST', '/api/admin/update_endpoints', {}, function(res) {
            dom.updateEndpointsBtn.disabled = false;
            if (res.code === 200) {
                showSystemMessage(res.msg || '接口配置已更新', false);
                loadSongs(false);
            } else {
                showSystemMessage(res.msg || '接口配置更新失败', true);
            }
        }, function() {
            dom.updateEndpointsBtn.disabled = false;
            showSystemMessage('接口配置更新失败，请检查网络', true);
        });
    };
}

// 初始化检查
window.onload = function() {
    checkStatus();
};
