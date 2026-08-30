package com.mosaicbudget.android;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public final class ServerOriginTest {
    @Test
    public void normalizesHttpsRootOrigins() {
        assertEquals("https://budget.example.com", ServerOrigin.normalize(" budget.example.com "));
        assertEquals("https://budget.example.com", ServerOrigin.normalize("HTTPS://BUDGET.EXAMPLE.COM/"));
        assertEquals("https://budget.example.com", ServerOrigin.normalize("https://budget.example.com:443"));
        assertEquals("https://budget.example.com:8443", ServerOrigin.normalize("https://budget.example.com:8443/"));
        assertEquals("https://[2001:db8::1]:8443", ServerOrigin.normalize("https://[2001:db8::1]:8443"));
    }

    @Test
    public void rejectsAnythingOutsideOneSecureRootOrigin() {
        assertNull(ServerOrigin.normalize(null));
        assertNull(ServerOrigin.normalize(""));
        assertNull(ServerOrigin.normalize("http://budget.example.com"));
        assertNull(ServerOrigin.normalize("https://user:secret@budget.example.com"));
        assertNull(ServerOrigin.normalize("https://budget.example.com/mosaic"));
        assertNull(ServerOrigin.normalize("https://budget.example.com?next=elsewhere"));
        assertNull(ServerOrigin.normalize("https://budget.example.com/#fragment"));
        assertNull(ServerOrigin.normalize("https://budget.example.com:0"));
        assertNull(ServerOrigin.normalize("https://budget.example.com:70000"));
        assertNull(ServerOrigin.normalize("https://budget.example.com bad.example"));
        assertNull(ServerOrigin.normalize("javascript:alert(1)"));
    }
}
