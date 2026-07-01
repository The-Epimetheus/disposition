package com.example.greet;

import java.util.List;

/** Greets a list of names, skipping blanks with an early return. */
public class Greeter {

    private final String salutation;

    public Greeter(String salutation) {
        this.salutation = salutation;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            return "";
        }
        return salutation + ", " + name.trim() + "!";
    }

    public void greetAll(List<String> names) {
        for (String name : names) {
            String line = greet(name);
            if (!line.isEmpty()) {
                System.out.println(line);
            }
        }
    }
}
