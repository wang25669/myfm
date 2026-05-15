package com.wangl.myfm;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

public class MainActivity extends Activity {
    private WebView webView;
    private SharedPreferences prefs;

    // 接收从服务或广播中发来的媒体按键指令
    private BroadcastReceiver mediaCommandReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String command = intent.getStringExtra("command");
            if ("next".equals(command)) {
                webView.loadUrl("javascript:skipSong(1)");
            } else if ("prev".equals(command)) {
                webView.loadUrl("javascript:skipSong(-1)");
            } else if ("playpause".equals(command)) {
                webView.loadUrl("javascript:togglePlay()");
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        // setMediaPlaybackRequiresUserGesture 从 API 17 开始支持，保持 minSdk 14 时必须做版本保护。
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR1) {
            settings.setMediaPlaybackRequiresUserGesture(false); // 允许自动播放
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }
        
        // 注入 AndroidPlayer 桥接对象
        webView.addJavascriptInterface(new Object() {
            @android.webkit.JavascriptInterface
            public void play(String url) {
                Intent intent = new Intent(MainActivity.this, PlayerService.class);
                intent.setAction("PLAY");
                intent.putExtra("url", url);
                startService(intent);
            }
            @android.webkit.JavascriptInterface
            public void pause() {
                Intent intent = new Intent(MainActivity.this, PlayerService.class);
                intent.setAction("PAUSE");
                startService(intent);
            }
        }, "AndroidPlayer");
        
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                view.loadUrl(url);
                return true;
            }
        });

        // 启动后台保活服务
        startService(new Intent(this, PlayerService.class));
        
        // 注册接收器
        registerReceiver(mediaCommandReceiver, new IntentFilter("com.wangl.myfm.MEDIA_COMMAND"));

        // 第一步：检查 URL 配置
        checkAndShowUrlDialog();
    }

    private void checkAndShowUrlDialog() {
        prefs = getSharedPreferences("config", MODE_PRIVATE);
        String savedUrl = prefs.getString("server_url", "");

        if (savedUrl.isEmpty()) {
            showUrlDialog();
        } else {
            webView.loadUrl(savedUrl);
        }
    }

    private void showUrlDialog() {
        final EditText input = new EditText(this);
        input.setHint("http://192.168.x.x:5000");
        new AlertDialog.Builder(this)
            .setTitle("请输入 NAS 服务端地址")
            .setView(input)
            .setPositiveButton("确定", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    String url = input.getText().toString().trim();
                    if (!url.isEmpty()) {
                        if (!url.startsWith("http")) {
                            url = "http://" + url;
                        }
                        prefs.edit().putString("server_url", url).apply();
                        webView.loadUrl(url);
                    }
                }
            })
            .setCancelable(false)
            .show();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        unregisterReceiver(mediaCommandReceiver);
    }
}
