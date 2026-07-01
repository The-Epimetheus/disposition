package com.example.concurrent;

import java.util.concurrent.atomic.AtomicLong;

/** Thread-safe counter used as a bootstrap fixture. */
public class Counter {

    private final AtomicLong value = new AtomicLong();

    public long increment() {
        return value.incrementAndGet();
    }

    public long current() {
        return value.get();
    }
}
