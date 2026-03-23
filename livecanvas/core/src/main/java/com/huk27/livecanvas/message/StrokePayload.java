package com.huk27.livecanvas.message;

public record StrokePayload(String strokeId,
                            int x,
                            int y,
                            String color,
                            int width) {

    public StrokePayload {
        if (strokeId == null || strokeId.isBlank()) {
            throw new IllegalArgumentException("strokeId must not be blank");
        }
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("x or y must not be negative");
        }
        if (color == null || color.isBlank()) {
            throw new IllegalArgumentException("color must not be blank");
        }
        if (width <= 0) {
            throw new IllegalArgumentException("width must be greater than 0");
        }
    }
}
