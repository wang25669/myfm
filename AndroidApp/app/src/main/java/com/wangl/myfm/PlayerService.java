package com.wangl.myfm;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

public class PlayerService extends Service {
    private PowerManager.WakeLock wakeLock;
    private ComponentName mediaButtonReceiver;
    private AudioManager audioManager;
    private MediaPlayer mediaPlayer;

    @Override
    public void onCreate() {
        super.onCreate();
        
        // 1. 锁死 CPU 唤醒锁，防止锁屏杀进程
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PersonalFM::WakeLock");
        wakeLock.acquire();

        // 2. 初始化底层 MediaPlayer
        mediaPlayer = new MediaPlayer();
        mediaPlayer.setAudioStreamType(AudioManager.STREAM_MUSIC);
        mediaPlayer.setOnCompletionListener(new MediaPlayer.OnCompletionListener() {
            @Override
            public void onCompletion(MediaPlayer mp) {
                // 播完一首后，伪装成按了“下一首”按键，通知 MainActivity 切歌
                sendBroadcast(new Intent("com.wangl.myfm.MEDIA_COMMAND").putExtra("command", "next"));
            }
        });
        mediaPlayer.setOnErrorListener(new MediaPlayer.OnErrorListener() {
            @Override
            public boolean onError(MediaPlayer mp, int what, int extra) {
                String err = "⚠️ 底层崩溃: 错误码(" + what + ", " + extra + ")";
                android.widget.Toast.makeText(PlayerService.this, err, android.widget.Toast.LENGTH_LONG).show();
                return true; // 拦截错误，防止直接奔溃
            }
        });

        // 3. 注册多媒体按键接收器
        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        mediaButtonReceiver = new ComponentName(getPackageName(), MediaButtonReceiver.class.getName());
        audioManager.registerMediaButtonEventReceiver(mediaButtonReceiver);

        // 3. 提升为前台服务
        createNotification();
    }

    private void createNotification() {
        String channelId = "fm_channel";
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(channelId, "Playback", NotificationManager.IMPORTANCE_LOW);
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            nm.createNotificationChannel(channel);
        }

        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent, 
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0));

        Notification.Builder builder = new Notification.Builder(this)
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle("私人FM 后台运行中")
                .setContentText("保持稳定的音频播放体验")
                .setContentIntent(pi);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder.setChannelId(channelId);
        }

        startForeground(1, builder.build());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            String action = intent.getAction();
            if ("PLAY".equals(action)) {
                String url = intent.getStringExtra("url");
                if (url != null) {
                    try {
                        mediaPlayer.reset();
                        mediaPlayer.setDataSource(url);
                        mediaPlayer.prepareAsync();
                        mediaPlayer.setOnPreparedListener(new MediaPlayer.OnPreparedListener() {
                            @Override
                            public void onPrepared(MediaPlayer mp) {
                                // 调试用：显示缓冲完成提示
                                // android.widget.Toast.makeText(PlayerService.this, "✅ 底层缓冲完毕，准备开搞", android.widget.Toast.LENGTH_SHORT).show();
                                mp.start();
                            }
                        });
                    } catch (Exception e) {
                        android.widget.Toast.makeText(PlayerService.this, "⚠️ 代码异常: " + e.getMessage(), android.widget.Toast.LENGTH_LONG).show();
                        e.printStackTrace();
                    }
                }
            } else if ("PAUSE".equals(action)) {
                if (mediaPlayer.isPlaying()) {
                    mediaPlayer.pause();
                } else {
                    mediaPlayer.start();
                }
            }
        }
        return START_STICKY; // 即使被系统强杀也会尝试自动重启
    }

    @Override
    public void onDestroy() {
        if (mediaPlayer != null) {
            mediaPlayer.release();
            mediaPlayer = null;
        }
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        if (audioManager != null) {
            audioManager.unregisterMediaButtonEventReceiver(mediaButtonReceiver);
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
