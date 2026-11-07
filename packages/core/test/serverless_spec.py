from __future__ import annotations

import json

from austial import Controller, Get, Injectable, Module, OnModuleInit, create_lambda_handler

LOG: list[str] = []


@Injectable()
class Clock(OnModuleInit):
    def on_module_init(self) -> None:
        LOG.append("init")


@Controller("hello")
class HelloController:
    def __init__(self, clock: Clock):
        self.clock = clock

    @Get()
    def hello(self):
        return {"hello": "lambda"}


@Module(controllers=[HelloController], providers=[Clock])
class LambdaApp:
    pass


def event(path: str) -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "x.example.com"},
        "requestContext": {
            "http": {"method": "GET", "path": path, "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4", "userAgent": "t"},
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


def test_lambda_handler_serves_http_api_events_and_runs_lifecycle_hooks() -> None:
    handler = create_lambda_handler(LambdaApp)
    response = handler(event("/hello"), None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"hello": "lambda"}
    assert LOG == ["init"]
    assert handler(event("/missing"), None)["statusCode"] == 404
