package com.huk27.lostark_ai.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

@SpringBootApplication
@ComponentScan(basePackages = {"com.huk27.lostark_ai.api", "com.huk27.lostark_ai.core"}) // core 모듈 스캔
public class LostarkAiApplication {

    public static void main(String[] args) {
        SpringApplication.run(LostarkAiApplication.class, args);
    }
}
