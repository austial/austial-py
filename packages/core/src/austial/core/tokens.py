"""Well-known injection tokens -- mirrors ``@nestjs/core``'s ``APP_GUARD`` & friends.

Register a provider under one of these tokens in *any* module and Austial applies it **globally**,
with full constructor injection (unlike ``app.use_global_guards(Guard())``, which takes an instance you
built by hand)::

    @Module(providers=[{"provide": APP_GUARD, "useClass": AuthGuard}])
    class AuthModule: ...

The same token can be registered any number of times; each registration adds one more global component.
``useClass``, ``useValue``, ``useFactory`` and ``useExisting`` all work.
"""

APP_GUARD = "APP_GUARD"
APP_PIPE = "APP_PIPE"
APP_INTERCEPTOR = "APP_INTERCEPTOR"
APP_FILTER = "APP_FILTER"

# Injecting this into a provider gives it the class that is asking for it (see Container docs).
INQUIRER = "INQUIRER"

# token -> the kind the container files it under
GLOBAL_COMPONENT_KINDS = {
    APP_GUARD: "guards",
    APP_PIPE: "pipes",
    APP_INTERCEPTOR: "interceptors",
    APP_FILTER: "filters",
}
