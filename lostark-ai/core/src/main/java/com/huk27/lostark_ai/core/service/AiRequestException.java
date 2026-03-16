package com.huk27.lostark_ai.core.service;

import org.springframework.http.HttpStatus;

public class AiRequestException extends RuntimeException {

    private final HttpStatus status;

    public AiRequestException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
