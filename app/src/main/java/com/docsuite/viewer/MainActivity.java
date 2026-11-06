package com.docsuite.viewer;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.content.ClipData;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;
import androidx.webkit.WebViewAssetLoader;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;

public class MainActivity extends AppCompatActivity {

    private static final String HOST = "appassets.androidplatform.net";
    private static final String START_URL = "https://" + HOST + "/assets/index.html";

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private ActivityResultLauncher<Intent> picker;
    private boolean pageReady = false;
    private View fullscreenView;
    private WebChromeClient.CustomViewCallback fullscreenCb;
    private int savedOrientation;
    private String pendingJs = null;
    private File sharedDir;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        sharedDir = new File(getCacheDir(), "shared");
        //noinspection ResultOfMethodCallIgnored
        sharedDir.mkdirs();

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        // Zooming is handled inside the page (document only), never the whole app
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setTextZoom(100);
        s.setMediaPlaybackRequiresUserGesture(true);

        // Serves the bundled app from assets/ and files opened from other apps from cache/shared/
        final WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
                .setDomain(HOST)
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .addPathHandler("/shared/", new WebViewAssetLoader.InternalStoragePathHandler(this, sharedDir))
                .build();

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return loader.shouldInterceptRequest(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (HOST.equals(u.getHost())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (ActivityNotFoundException ignored) { }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                pageReady = true;
                if (pendingJs != null) {
                    view.evaluateJavascript(pendingJs, null);
                    pendingJs = null;
                }
            }
        });

        // System file picker for the page's "Open" button
        picker = registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result -> {
            if (fileCallback == null) return;
            Uri[] uris = null;
            if (result.getResultCode() == RESULT_OK && result.getData() != null && result.getData().getData() != null) {
                uris = new Uri[]{result.getData().getData()};
            }
            fileCallback.onReceiveValue(uris);
            fileCallback = null;
        });

        web.setWebChromeClient(new WebChromeClient() {
            // HTML5 fullscreen (e.g. the video player's fullscreen button)
            @Override
            public void onShowCustomView(View customView, CustomViewCallback callback) {
                if (fullscreenView != null) { callback.onCustomViewHidden(); return; }
                fullscreenView = customView;
                fullscreenCb = callback;
                savedOrientation = getRequestedOrientation();
                web.setVisibility(View.GONE);
                FrameLayout decor = (FrameLayout) getWindow().getDecorView();
                decor.addView(customView, new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
                customView.setBackgroundColor(0xFF000000);
                getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                hideSystemBars(true);
                setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR);
            }

            @Override
            public void onHideCustomView() {
                if (fullscreenView == null) return;
                FrameLayout decor = (FrameLayout) getWindow().getDecorView();
                decor.removeView(fullscreenView);
                fullscreenView = null;
                web.setVisibility(View.VISIBLE);
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                hideSystemBars(false);
                setRequestedOrientation(savedOrientation);
                if (fullscreenCb != null) { fullscreenCb.onCustomViewHidden(); fullscreenCb = null; }
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                try {
                    picker.launch(i);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        // Back button: let the page go back first (close document / leave zip), then exit
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (fullscreenView != null) { web.getWebChromeClient().onHideCustomView(); return; }
                web.evaluateJavascript("window.docsuiteBack ? window.docsuiteBack() : false", value -> {
                    if (!"true".equals(value)) {
                        setEnabled(false);
                        getOnBackPressedDispatcher().onBackPressed();
                        setEnabled(true);
                    }
                });
            }
        });

        web.addJavascriptInterface(new ShareBridge(), "DocSuiteAndroid");
        web.loadUrl(START_URL);
        if (savedInstanceState == null) handleIntent(getIntent());
    }

    private void hideSystemBars(boolean hide) {
        View d = getWindow().getDecorView();
        if (hide) {
            d.setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        } else {
            d.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    /** Handles "Open with DocSuite" and "Share to DocSuite" from other apps. */
    @SuppressWarnings("deprecation")
    private void handleIntent(Intent intent) {
        if (intent == null) return;
        Uri uri = null;
        if (Intent.ACTION_VIEW.equals(intent.getAction())) {
            uri = intent.getData();
        } else if (Intent.ACTION_SEND.equals(intent.getAction())) {
            uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        }
        if (uri == null) return;
        final Uri src = uri;

        new Thread(() -> {
            try {
                String name = displayName(src);
                String mime = getContentResolver().getType(src);
                File[] old = sharedDir.listFiles();
                if (old != null) for (File f : old) //noinspection ResultOfMethodCallIgnored
                    f.delete();
                String safe = name.replaceAll("[^A-Za-z0-9._ -]", "_");
                File out = new File(sharedDir, safe);
                try (InputStream in = getContentResolver().openInputStream(src);
                     OutputStream os = new FileOutputStream(out)) {
                    if (in == null) throw new Exception("Cannot read file");
                    byte[] buf = new byte[64 * 1024];
                    int n;
                    while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
                }
                final String js = "window.docsuiteOpenUrl && window.docsuiteOpenUrl('/shared/' + encodeURIComponent("
                        + JSONObject.quote(safe) + "), " + JSONObject.quote(name) + ", "
                        + JSONObject.quote(mime == null ? "" : mime) + ")";
                runOnUiThread(() -> {
                    if (pageReady) web.evaluateJavascript(js, null);
                    else pendingJs = js;
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Couldn't open this file", Toast.LENGTH_LONG).show());
            }
        }).start();
    }

    /** Receives a file from the page in base64 chunks and opens the Android share menu. */
    private class ShareBridge {
        private File outFile;
        private OutputStream out;

        @JavascriptInterface
        public void begin(String name) {
            try {
                closeQuietly();
                File dir = new File(getCacheDir(), "out");
                //noinspection ResultOfMethodCallIgnored
                dir.mkdirs();
                File[] old = dir.listFiles();
                if (old != null) for (File f : old) //noinspection ResultOfMethodCallIgnored
                    f.delete();
                String safe = (name == null || name.trim().isEmpty()) ? "document" : name.replaceAll("[\\\\/:*?\"<>|]", "_");
                outFile = new File(dir, safe);
                out = new FileOutputStream(outFile);
            } catch (IOException e) {
                outFile = null;
                toast("Couldn't prepare file to share");
            }
        }

        @JavascriptInterface
        public void chunk(String b64) {
            if (out == null) return;
            try {
                out.write(Base64.decode(b64, Base64.DEFAULT));
            } catch (Exception e) {
                closeQuietly();
                outFile = null;
                toast("Couldn't prepare file to share");
            }
        }

        @JavascriptInterface
        public void finish(String mime) {
            if (out == null || outFile == null) return;
            closeQuietly();
            final File f = outFile;
            final String type = (mime == null || mime.isEmpty()) ? "application/octet-stream" : mime;
            runOnUiThread(() -> {
                try {
                    Uri uri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".files", f);
                    Intent send = new Intent(Intent.ACTION_SEND);
                    send.setType(type);
                    send.putExtra(Intent.EXTRA_STREAM, uri);
                    send.putExtra(Intent.EXTRA_SUBJECT, f.getName());
                    send.setClipData(ClipData.newRawUri(f.getName(), uri));
                    send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(Intent.createChooser(send, "Share " + f.getName()));
                } catch (Exception e) {
                    Toast.makeText(MainActivity.this, "Couldn't share this file", Toast.LENGTH_LONG).show();
                }
            });
        }

        private void closeQuietly() {
            if (out != null) {
                try { out.close(); } catch (IOException ignored) { }
                out = null;
            }
        }

        private void toast(String msg) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show());
        }
    }

    private String displayName(Uri uri) {
        String name = null;
        if ("content".equals(uri.getScheme())) {
            try (Cursor c = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                if (c != null && c.moveToFirst()) name = c.getString(0);
            } catch (Exception ignored) { }
        }
        if (name == null) name = uri.getLastPathSegment();
        if (name == null || name.isEmpty()) name = "document";
        return name;
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
