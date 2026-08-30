package com.mosaicbudget.android;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.ClientCertRequest;
import android.webkit.CookieManager;
import android.webkit.HttpAuthHandler;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/**
 * A deliberately small, hardened shell around a self-hosted Mosaic Budget server.
 * Credentials are entered into the server's own login page; this activity stores only
 * the normalized HTTPS origin and never exposes a JavaScript bridge.
 */
public final class MainActivity extends Activity {
    private static final String PREFERENCES = "mosaic_android";
    private static final String SERVER_ORIGIN_KEY = "server_origin";
    private static final long BACK_RESULT_TIMEOUT_MS = 900L;

    private View root;
    private View setupScreen;
    private EditText serverInput;
    private TextView serverError;
    private Button connectButton;
    private View webContainer;
    private WebView webView;
    private ProgressBar progress;
    private View errorPanel;
    private TextView errorTitle;
    private TextView errorMessage;
    private Button retryButton;
    private Button changeServerButton;

    private ViewGroup webViewParent;
    private ViewGroup.LayoutParams webViewLayoutParams;
    private int webViewIndex;

    private SharedPreferences preferences;
    private String serverOrigin;
    private boolean pageFailed;
    private boolean backResultPending;
    private int backRequestId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        bindViews();
        applyEdgeToEdgeInsets();
        preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE);
        configureWebView(webView);
        bindActions();
        registerPredictiveBackHandler();

        String savedOrigin = preferences.getString(SERVER_ORIGIN_KEY, null);
        String validatedOrigin = ServerOrigin.normalize(savedOrigin);
        if (validatedOrigin == null) {
            if (savedOrigin != null) {
                preferences.edit().remove(SERVER_ORIGIN_KEY).apply();
            }
            showSetup(false);
            return;
        }

        serverOrigin = validatedOrigin;
        serverInput.setText(serverOrigin);
        showLoading();
        boolean restored = savedInstanceState != null && webView.restoreState(savedInstanceState) != null;
        if (!restored) {
            loadServerRoot();
        }
    }

    private void bindViews() {
        root = requireView(R.id.root);
        setupScreen = requireView(R.id.setup_screen);
        serverInput = requireView(R.id.server_input);
        serverError = requireView(R.id.server_error);
        connectButton = requireView(R.id.connect_button);
        webContainer = requireView(R.id.web_container);
        webView = requireView(R.id.web_view);
        progress = requireView(R.id.progress);
        errorPanel = requireView(R.id.error_panel);
        errorTitle = requireView(R.id.error_title);
        errorMessage = requireView(R.id.error_message);
        retryButton = requireView(R.id.retry_button);
        changeServerButton = requireView(R.id.change_server_button);

        if (!(webView.getParent() instanceof ViewGroup)) {
            throw new IllegalStateException("web_view must have a ViewGroup parent");
        }
        webViewParent = (ViewGroup) webView.getParent();
        webViewIndex = webViewParent.indexOfChild(webView);
        webViewLayoutParams = webView.getLayoutParams();
    }

    @SuppressWarnings("unchecked")
    private <T extends View> T requireView(int id) {
        T view = (T) findViewById(id);
        if (view == null) {
            throw new IllegalStateException("Missing required view: " + id);
        }
        return view;
    }

    private void bindActions() {
        connectButton.setOnClickListener(ignored -> connectToEnteredServer());
        serverInput.setSingleLine(true);
        serverInput.setImeOptions(EditorInfo.IME_ACTION_GO);
        serverInput.setOnEditorActionListener((view, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_GO) {
                connectToEnteredServer();
                return true;
            }
            return false;
        });
        retryButton.setOnClickListener(ignored -> loadServerRoot());
        changeServerButton.setOnClickListener(ignored -> showSetup(true));
    }

    private void registerPredictiveBackHandler() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    this::handleBackPressed);
        }
    }

    /** API 35+ enforces edge-to-edge. Apply each inset once at the root. */
    private void applyEdgeToEdgeInsets() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return;
        }

        getWindow().setDecorFitsSystemWindows(false);
        final int baseLeft = root.getPaddingLeft();
        final int baseTop = root.getPaddingTop();
        final int baseRight = root.getPaddingRight();
        final int baseBottom = root.getPaddingBottom();
        root.setOnApplyWindowInsetsListener((view, windowInsets) -> {
            android.graphics.Insets bars = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            android.graphics.Insets ime = windowInsets.getInsets(WindowInsets.Type.ime());
            view.setPadding(
                    baseLeft + Math.max(bars.left, ime.left),
                    baseTop + Math.max(bars.top, ime.top),
                    baseRight + Math.max(bars.right, ime.right),
                    baseBottom + Math.max(bars.bottom, ime.bottom));
            return WindowInsets.CONSUMED;
        });
        root.requestApplyInsets();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView(WebView view) {
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = view.getSettings();
        settings.setUserAgentString(
                settings.getUserAgentString() + " MosaicBudgetAndroid/" + BuildConfig.VERSION_NAME);
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setGeolocationEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        // The server login form opts into Android Autofill. Mosaic itself never
        // persists the password in this companion's preferences.
        settings.setSaveFormData(true);
        settings.setSafeBrowsingEnabled(true);

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(view, false);

        view.setWebViewClient(new MosaicWebViewClient());
        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView currentView, int newProgress) {
                progress.setProgress(newProgress);
                if (!pageFailed && errorPanel.getVisibility() != View.VISIBLE) {
                    progress.setVisibility(newProgress < 100 ? View.VISIBLE : View.GONE);
                }
            }

            @Override
            public boolean onCreateWindow(
                    WebView currentView,
                    boolean isDialog,
                    boolean isUserGesture,
                    android.os.Message resultMsg) {
                return false;
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.deny();
            }
        });
    }

    @SuppressLint("SetTextI18n")
    private void connectToEnteredServer() {
        String candidate = ServerOrigin.normalize(serverInput.getText().toString());
        if (candidate == null) {
            serverError.setText("Enter a root HTTPS address, such as https://budget.example.com");
            serverError.setVisibility(View.VISIBLE);
            return;
        }

        hideKeyboard();
        serverError.setVisibility(View.GONE);
        boolean serverChanged = serverOrigin == null || !serverOrigin.equals(candidate);
        serverOrigin = candidate;
        serverInput.setText(serverOrigin);
        preferences.edit().putString(SERVER_ORIGIN_KEY, serverOrigin).apply();
        showLoading();

        if (serverChanged) {
            clearBrowserData(this::loadServerRoot);
        } else {
            loadServerRoot();
        }
    }

    private void clearBrowserData(Runnable afterClear) {
        WebStorage.getInstance().deleteAllData();
        if (webView != null) {
            webView.stopLoading();
            webView.clearHistory();
            webView.clearFormData();
            webView.clearCache(true);
        }

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.removeAllCookies(removed -> {
            cookieManager.flush();
            root.post(afterClear);
        });
    }

    private void loadServerRoot() {
        if (serverOrigin == null) {
            showSetup(false);
            return;
        }
        ensureWebView();
        showLoading();
        webView.loadUrl(serverOrigin + "/");
    }

    private void ensureWebView() {
        if (webView != null) {
            return;
        }
        WebView replacement = new WebView(this);
        replacement.setId(R.id.web_view);
        int safeIndex = Math.max(0, Math.min(webViewIndex, webViewParent.getChildCount()));
        webViewParent.addView(replacement, safeIndex, webViewLayoutParams);
        webView = replacement;
        configureWebView(replacement);
    }

    private void showSetup(boolean includeCurrentServer) {
        if (includeCurrentServer && serverOrigin != null) {
            serverInput.setText(serverOrigin);
        }
        pageFailed = false;
        progress.setVisibility(View.GONE);
        errorPanel.setVisibility(View.GONE);
        webContainer.setVisibility(View.GONE);
        setupScreen.setVisibility(View.VISIBLE);
        serverError.setVisibility(View.GONE);
        serverInput.requestFocus();
    }

    private void showLoading() {
        pageFailed = false;
        setupScreen.setVisibility(View.GONE);
        webContainer.setVisibility(View.VISIBLE);
        errorPanel.setVisibility(View.GONE);
        if (webView != null) {
            webView.setVisibility(View.VISIBLE);
        }
        progress.setProgress(0);
        progress.setVisibility(View.VISIBLE);
    }

    private void showPage() {
        pageFailed = false;
        setupScreen.setVisibility(View.GONE);
        webContainer.setVisibility(View.VISIBLE);
        errorPanel.setVisibility(View.GONE);
        progress.setVisibility(View.GONE);
        if (webView != null) {
            webView.setVisibility(View.VISIBLE);
        }
    }

    private void showLoadError(String title, String message) {
        pageFailed = true;
        setupScreen.setVisibility(View.GONE);
        webContainer.setVisibility(View.VISIBLE);
        progress.setVisibility(View.GONE);
        if (webView != null) {
            webView.setVisibility(View.INVISIBLE);
        }
        errorTitle.setText(title);
        errorMessage.setText(message);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private final class MosaicWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri target = request.getUrl();
            if (isAllowedServerOrigin(target)) {
                return false;
            }
            if (request.isForMainFrame()) {
                openExternal(target);
            }
            return true;
        }

        @Override
        @SuppressWarnings("deprecation")
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            Uri target = Uri.parse(url);
            if (isAllowedServerOrigin(target)) {
                return false;
            }
            openExternal(target);
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            pageFailed = false;
            showLoading();
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            CookieManager.getInstance().flush();
            if (!pageFailed) {
                showPage();
            }
        }

        @Override
        public void onReceivedError(
                WebView view,
                WebResourceRequest request,
                WebResourceError error) {
            if (!request.isForMainFrame()) {
                return;
            }
            int code = error.getErrorCode();
            if (code == ERROR_HOST_LOOKUP
                    || code == ERROR_CONNECT
                    || code == ERROR_TIMEOUT
                    || code == ERROR_IO) {
                showLoadError(
                        "Server unavailable",
                        "Check your connection and server address, then try again.");
            } else {
                showLoadError("Couldn't open Mosaic Budget", "The server could not be loaded.");
            }
        }

        @Override
        public void onReceivedHttpError(
                WebView view,
                WebResourceRequest request,
                WebResourceResponse errorResponse) {
            if (request.isForMainFrame() && errorResponse.getStatusCode() >= 400) {
                showLoadError(
                        "Server error",
                        "The server returned HTTP " + errorResponse.getStatusCode() + ". Try again shortly.");
            }
        }

        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
            handler.cancel();
            showLoadError(
                    "Secure connection failed",
                    "The server certificate could not be verified. Check the address or contact the server administrator.");
        }

        @Override
        public void onReceivedClientCertRequest(WebView view, ClientCertRequest request) {
            request.cancel();
        }

        @Override
        public void onReceivedHttpAuthRequest(
                WebView view,
                HttpAuthHandler handler,
                String host,
                String realm) {
            handler.cancel();
        }

        @Override
        public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            if (view.getParent() == webViewParent) {
                webViewParent.removeView(view);
            }
            view.setWebChromeClient(null);
            view.setWebViewClient(null);
            view.destroy();
            if (view == webView) {
                webView = null;
            }
            showLoadError(
                    "Web view restarted",
                    "The page stopped unexpectedly. Tap Retry to reconnect safely.");
            return true;
        }
    }

    private boolean isAllowedServerOrigin(Uri target) {
        if (serverOrigin == null || target == null) {
            return false;
        }
        try {
            URI allowed = new URI(serverOrigin);
            URI candidate = new URI(target.toString());
            if (!"https".equalsIgnoreCase(candidate.getScheme())
                    || candidate.getRawUserInfo() != null
                    || candidate.getHost() == null) {
                return false;
            }
            return ServerOrigin.normalizeHost(allowed.getHost()).equals(ServerOrigin.normalizeHost(candidate.getHost()))
                    && ServerOrigin.effectiveHttpsPort(allowed) == ServerOrigin.effectiveHttpsPort(candidate);
        } catch (IllegalArgumentException | URISyntaxException exception) {
            return false;
        }
    }

    private void openExternal(Uri target) {
        if (target == null || target.getScheme() == null) {
            return;
        }
        String scheme = target.getScheme().toLowerCase(Locale.US);
        if (!scheme.equals("https")
                && !scheme.equals("http")
                && !scheme.equals("mailto")
                && !scheme.equals("tel")) {
            return;
        }

        Intent intent = new Intent(Intent.ACTION_VIEW, target);
        intent.addCategory(Intent.CATEGORY_BROWSABLE);
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException exception) {
            new AlertDialog.Builder(this)
                    .setTitle("No app can open this link")
                    .setMessage(target.toString())
                    .setPositiveButton("OK", null)
                    .show();
        }
    }

    private void hideKeyboard() {
        InputMethodManager manager =
                (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        View focused = getCurrentFocus();
        if (manager != null && focused != null) {
            manager.hideSoftInputFromWindow(focused.getWindowToken(), 0);
        }
        serverInput.clearFocus();
    }

    @Override
    @SuppressLint("GestureBackNavigation") // API 33+ uses registerPredictiveBackHandler; this covers API 26–32.
    public void onBackPressed() {
        handleBackPressed();
    }

    private void handleBackPressed() {
        if (setupScreen.getVisibility() == View.VISIBLE) {
            if (serverOrigin != null) {
                showLoading();
                if (webView != null && webView.getUrl() != null) {
                    showPage();
                } else {
                    loadServerRoot();
                }
            } else {
                showExitDialog();
            }
            return;
        }

        if (webView == null || backResultPending) {
            if (webView == null) {
                showExitDialog();
            }
            return;
        }

        backResultPending = true;
        int requestId = ++backRequestId;
        root.postDelayed(() -> {
            if (backResultPending && backRequestId == requestId) {
                backResultPending = false;
                showExitDialog();
            }
        }, BACK_RESULT_TIMEOUT_MS);

        try {
            webView.evaluateJavascript(
                    "(function(){try{return typeof window.mosaicAndroidBack==='function'"
                            + "?window.mosaicAndroidBack():'unhandled';}catch(e){return 'unhandled';}})()",
                    result -> handleAndroidBackResult(requestId, result));
        } catch (RuntimeException exception) {
            if (backResultPending && backRequestId == requestId) {
                backResultPending = false;
                showExitDialog();
            }
        }
    }

    private void handleAndroidBackResult(int requestId, String result) {
        if (!backResultPending || requestId != backRequestId) {
            return;
        }
        backResultPending = false;
        String normalized = result == null ? "" : result.trim();
        if (normalized.equals("true") || normalized.equals("\"handled\"")) {
            return;
        }
        if (normalized.equals("\"dirty\"")) {
            showDiscardDialog();
            return;
        }
        showExitDialog();
    }

    private void showDiscardDialog() {
        new AlertDialog.Builder(this)
                .setTitle("Discard unsaved changes?")
                .setMessage("Your changes on this screen have not been saved.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Discard", (dialog, which) -> {
                    if (webView != null) {
                        webView.evaluateJavascript(
                                "(function(){try{if(typeof window.mosaicAndroidDiscardChanges==='function')"
                                        + "{window.mosaicAndroidDiscardChanges();}}catch(e){}})()",
                                null);
                    }
                })
                .show();
    }

    private void showExitDialog() {
        new AlertDialog.Builder(this)
                .setTitle("Leave Mosaic Budget?")
                .setMessage("You can exit the app or connect to a different server.")
                .setNegativeButton("Cancel", null)
                .setNeutralButton("Change server", (dialog, which) -> showSetup(true))
                .setPositiveButton("Exit", (dialog, which) -> finishAndRemoveTask())
                .show();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) {
            webView.saveState(outState);
        }
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
    }

    @Override
    protected void onPause() {
        CookieManager.getInstance().flush();
        if (webView != null) {
            webView.onPause();
        }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            if (webView.getParent() instanceof ViewGroup) {
                ((ViewGroup) webView.getParent()).removeView(webView);
            }
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
