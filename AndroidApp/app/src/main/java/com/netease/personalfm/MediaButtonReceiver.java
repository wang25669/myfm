package com.netease.personalfm;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.view.KeyEvent;

public class MediaButtonReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_MEDIA_BUTTON.equals(intent.getAction())) {
            KeyEvent event = intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT);
            if (event != null && event.getAction() == KeyEvent.ACTION_DOWN) {
                String cmd = null;
                switch (event.getKeyCode()) {
                    case KeyEvent.KEYCODE_MEDIA_NEXT:
                        cmd = "next";
                        break;
                    case KeyEvent.KEYCODE_MEDIA_PREVIOUS:
                        cmd = "prev";
                        break;
                    case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE:
                    case KeyEvent.KEYCODE_MEDIA_PLAY:
                    case KeyEvent.KEYCODE_MEDIA_PAUSE:
                        cmd = "playpause";
                        break;
                }
                if (cmd != null) {
                    Intent localIntent = new Intent("com.netease.personalfm.MEDIA_COMMAND");
                    localIntent.putExtra("command", cmd);
                    context.sendBroadcast(localIntent);
                }
            }
        }
    }
}
