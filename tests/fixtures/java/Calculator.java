package com.example.util;

/** A tiny calculator used as a bootstrap fixture. */
public final class Calculator {

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }

    public int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException("denominator must be non-zero");
        }
        return numerator / denominator;
    }
}
