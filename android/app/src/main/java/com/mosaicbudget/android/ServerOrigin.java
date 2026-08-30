package com.mosaicbudget.android;

import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Canonicalizes the one origin the companion is allowed to load. */
final class ServerOrigin {
    private ServerOrigin() {}

    static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String input = value.trim();
        if (input.isEmpty() || containsWhitespace(input) || input.contains("\\")) {
            return null;
        }
        if (!input.contains("://")) {
            input = "https://" + input;
        }

        try {
            URI parsed = new URI(input);
            String path = parsed.getRawPath();
            if (!"https".equalsIgnoreCase(parsed.getScheme())
                    || parsed.getHost() == null
                    || parsed.getHost().isEmpty()
                    || parsed.getRawUserInfo() != null
                    || parsed.getRawQuery() != null
                    || parsed.getRawFragment() != null
                    || (path != null && !path.isEmpty() && !path.equals("/"))
                    || parsed.getRawAuthority() == null
                    || parsed.getRawAuthority().endsWith(":")) {
                return null;
            }

            int port = parsed.getPort();
            if (port == 0 || port > 65535 || port < -1) {
                return null;
            }
            String host = normalizeHost(parsed.getHost());
            String displayHost = host.contains(":") && !host.startsWith("[")
                    ? "[" + host + "]"
                    : host;
            return "https://" + displayHost + (port == -1 || port == 443 ? "" : ":" + port);
        } catch (IllegalArgumentException | URISyntaxException exception) {
            return null;
        }
    }

    static String normalizeHost(String host) {
        String normalized = host.toLowerCase(Locale.US);
        if (normalized.startsWith("[") && normalized.endsWith("]")) {
            return normalized.substring(1, normalized.length() - 1);
        }
        return normalized.contains(":") ? normalized : IDN.toASCII(normalized);
    }

    static int effectiveHttpsPort(URI uri) {
        return uri.getPort() == -1 ? 443 : uri.getPort();
    }

    private static boolean containsWhitespace(String value) {
        for (int index = 0; index < value.length(); index++) {
            if (Character.isWhitespace(value.charAt(index))) {
                return true;
            }
        }
        return false;
    }
}
