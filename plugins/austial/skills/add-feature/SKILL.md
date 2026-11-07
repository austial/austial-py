---
name: add-feature
description: Add one capability to an existing Austial app: authentication and roles, multi-tenancy, a database entity, background jobs, scheduled tasks, WebSockets or Socket.IO, GraphQL, microservices and message brokers, CQRS, events, caching, MongoDB, outbound HTTP, OpenAPI docs, health checks, file storage, i18n, or a CLI command. Use when the user asks for any of these in an Austial project.
argument-hint: <capability, e.g. "JWT auth with roles" or "websocket chat">
---

Add this capability: $ARGUMENTS

Load the `austial-framework` skill first. For each capability: install the extra if any, register the module, write the code, **write a test, run the verification loop**
(`ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`). If a signature below is not enough, fetch the linked doc page instead of guessing.

| Capability | Install | Register in `AppModule.imports` | Docs |
|---|---|---|---|
| Database entities | included | `OrmModule.for_root(type_=, url=, entities=[...])`; feature modules `OrmModule.for_feature([Entity])`; `austial g resource <name>` | /techniques/database |
| Migrations | included | `MigrationsModule.for_root(MigrationsConfig(...))`; `austial-migrate revision --autogenerate` | /techniques/migrations |
| JWT auth, passwords, TOTP | included | `AuthModule.for_root(AuthConfig(jwt_secret=<32+ chars from env>, issuer="app"))`; `@UseGuards(AuthGuard)`; `@Public()`; `CurrentUser()` | /techniques/authentication |
| Social login (OIDC) | included | `OAuth2Provider` / `GoogleOAuth(...)`, `verify_id_token` | /techniques/authentication |
| Custom strategies (API key, ...) | included | subclass `AuthStrategy`; `@UseGuards(StrategyGuard("jwt", "api-key"))` | /techniques/authentication |
| Roles and permissions | included | `AuthzModule.for_root()`; `@UseGuards(AuthGuard, RolesGuard)` + `@Roles("admin")` | /techniques/authorization |
| Multi-tenancy | included | `TenancyModule.for_root()`; entities extend `Tenanted`; filter every query by `TenantContext.require()` | /techniques/multi-tenancy |
| Security headers, rate limits, CSRF | included | `SecurityModule.for_root(SecurityConfig(...))`; `@RateLimit(...)` | /techniques/security |
| Background jobs (durable) | included | `JobsModule.for_root(JobsConfig())`; `@Job("name")`; `JobQueue.enqueue(...)` | /techniques/background-jobs |
| Scheduled tasks | included | `ScheduleModule.for_root()`; `@Cron("0 9 * * 1-5")`, `@Interval(60)`, `@Timeout(5)` | /techniques/task-scheduling |
| WebSockets | included | `WebSocketsModule.for_root()`; `@WebSocketGateway("/chat")`, `@SubscribeMessage("evt")`; `austial g gateway chat` | /techniques/websockets |
| Socket.IO | `austial add socketio` | `WebSocketsModule.for_root(adapter=SocketIoAdapter(cors_allowed_origins=...))` | /techniques/websockets |
| GraphQL | `austial add graphql` | `GraphQLModule.for_root(schema=strawberry_schema)`; resolvers use `inject(info, Service)` | /techniques/graphql |
| Microservices (TCP, Redis, NATS, Kafka, MQTT, RabbitMQ, gRPC) | `austial add redis` (etc.) | `app.connect_microservice(MicroserviceOptions(Transport.REDIS, url=...))`; `@MessagePattern`, `@EventPattern`; `ClientsModule.register([ClientOptions(...)])` | /techniques/microservices |
| gRPC with a `.proto` | `austial add grpc-proto` | `extra={"proto_path": "x.proto"}`; `@GrpcMethod("Service")` | /techniques/microservices |
| CQRS | included | `CqrsModule.for_root()`; `@CommandHandler`, `@QueryHandler`, `@EventsHandler`, `@Saga()` | /techniques/cqrs |
| Events | included | `EventEmitterModule.for_root()`; `@OnEvent("order.*")`; `EventEmitter.emit(...)` | /techniques/events |
| Caching | included | `CacheModule.register()`; `@UseInterceptors(CacheInterceptor)`; `CacheService` | /techniques/caching |
| MongoDB models | `austial add mongo` | `MongoModule.for_root(uri=, database=)` + `for_feature([Model])`; `@Schema`, `Document`, `InjectModel` | /techniques/mongodb |
| Outbound HTTP | included | `HttpModule.register(base_url=, timeout=, retries=)`; `HttpService` | /techniques/http-module |
| OpenAPI / Swagger UI | included | `SwaggerModule.setup(app, DocumentBuilder().set_title(...).build(), path="api-docs")` | /techniques/openapi |
| Health checks | included | provide `HealthCheckService` + indicators; unhealthy raises HTTP 503 | /techniques/health-checks |
| Files, signed URLs | included | `StorageModule.for_root(StorageConfig(...))`; `s3` driver in production | /techniques/file-storage |
| i18n | included | `I18nModule.for_root(I18nConfig(...))`, `LocaleMiddleware` | /techniques/i18n |
| CLI commands | included | `@Command(name=...)` + `CommandFactory.main(AppModule)`; `austial g command <name>` | /techniques/command-line |
| Templates (HTML) | included | `app.set_base_views_dir("views")`; `@Render("page.html")` | /techniques/mvc |
| AWS Lambda | `austial add lambda` | `handler = create_lambda_handler(AppModule)` | /techniques/http-server |

Docs base URL: `https://docs.austial.com`. Full text of everything: `https://docs.austial.com/llms-full.txt`.

## Rules that apply to every capability

- Register the provider/controller/module, then prove it with a test that fails without the registration.
- Secrets come from `ConfigService.get_or_throw(...)` (a `.env` file), never from source.
- Anything in the "not production-safe by default" table of `AGENTS.md` (in-memory refresh tokens, rate-limit store, idempotency store, audit store, job
  backend, local file storage, `synchronize=True`) must be swapped before more than one worker or a restart matters. Say so in your summary when you use one.
- A guard on every non-public route; a test for the unauthenticated (401) and unauthorised (403) cases.
- Tenant-scoped data: tenant A must not be able to read, update or delete tenant B's row; test it.
- Brokers and external services: test against the real server when it is available (`docker run`), otherwise say what was only faked.
