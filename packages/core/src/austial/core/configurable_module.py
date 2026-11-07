"""``ConfigurableModuleBuilder`` -- mirrors Nest's: generates the boilerplate sync/async
``for_root`` / ``register`` classmethods every dynamic module otherwise hand-writes::

    config = ConfigurableModuleBuilder().set_class_method_name("for_root").build()


    @Module(providers=[MailService], exports=[MailService])
    class MailModule(config.module_class):
        pass


    @Injectable()
    class MailService:
        def __init__(self, options=Inject(config.options_token)):
            self.options = options


    MailModule.for_root({"host": "smtp.example.com"})
    MailModule.for_root_async(use_factory=lambda cfg: {"host": cfg.get("SMTP")}, inject=[ConfigService])
    MailModule.for_root_async(use_class=MailOptionsFactory)       # class with a `create()` method
    MailModule.for_root_async(use_existing=MailOptionsFactory)    # reuse an already-provided one

Options (any object -- a dict, a dataclass, a pydantic model) are provided under
``config.options_token``. ``set_extras`` lets the module accept extra top-level arguments
(e.g. ``is_global``) that shape the :class:`DynamicModule` rather than the options.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from austial.core.dynamic_module import DynamicModule


@dataclass(frozen=True)
class ConfigurableModule:
    module_class: type
    options_token: str


class ConfigurableModuleBuilder:
    def __init__(self, *, options_injection_key: str | None = None) -> None:
        self._options_token = options_injection_key
        self._method_name = "register"
        self._factory_method = "create"
        self._extras: dict[str, Any] = {}
        self._extras_transform: Callable[[DynamicModule, dict[str, Any]], DynamicModule] | None = None

    def set_class_method_name(self, name: str) -> ConfigurableModuleBuilder:
        """Names the generated classmethods ``<name>`` and ``<name>_async`` (default ``register``)."""
        self._method_name = name
        return self

    def set_factory_method_name(self, name: str) -> ConfigurableModuleBuilder:
        """The method ``use_class`` / ``use_existing`` options factories expose (default ``create``)."""
        self._factory_method = name
        return self

    def set_extras(
        self,
        defaults: dict[str, Any],
        transform: Callable[[DynamicModule, dict[str, Any]], DynamicModule] | None = None,
    ) -> ConfigurableModuleBuilder:
        """Accept extra keyword arguments (with ``defaults``) on the generated methods and let
        ``transform(dynamic_module, extras)`` fold them into the returned ``DynamicModule``."""
        self._extras = dict(defaults)
        self._extras_transform = transform
        return self

    def build(self) -> ConfigurableModule:
        builder = self
        token = self._options_token or f"CONFIGURABLE_MODULE_OPTIONS[{id(self)}]"
        name = self._method_name

        def apply_extras(module: DynamicModule, extras: dict[str, Any]) -> DynamicModule:
            if builder._extras_transform is not None:
                return builder._extras_transform(module, {**builder._extras, **extras})
            return module

        def sync_method(cls: type, options: Any = None, **extras: Any) -> DynamicModule:
            module = DynamicModule(
                module=cls,
                providers=[{"provide": token, "useValue": options}],
                exports=[token],
            )
            return apply_extras(module, extras)

        def async_method(
            cls: type,
            *,
            use_factory: Callable | None = None,
            use_class: type | None = None,
            use_existing: type | None = None,
            inject: list | None = None,
            imports: list | None = None,
            **extras: Any,
        ) -> DynamicModule:
            chosen = [x for x in (use_factory, use_class, use_existing) if x is not None]
            if len(chosen) != 1:
                raise ValueError(
                    f"{cls.__name__}.{name}_async() needs exactly one of use_factory/use_class/use_existing"
                )
            providers: list[Any] = []
            if use_factory is not None:
                providers.append({"provide": token, "useFactory": use_factory, "inject": list(inject or [])})
            else:
                source = use_class if use_class is not None else use_existing
                assert source is not None
                if use_class is not None:
                    providers.append(use_class)
                providers.append(
                    {
                        "provide": token,
                        "useFactory": lambda factory: getattr(factory, builder._factory_method)(),
                        "inject": [source],
                    }
                )
            module = DynamicModule(module=cls, imports=list(imports or []), providers=providers, exports=[token])
            return apply_extras(module, extras)

        module_class = type(
            "ConfigurableModuleClass",
            (),
            {name: classmethod(sync_method), f"{name}_async": classmethod(async_method)},
        )
        return ConfigurableModule(module_class=module_class, options_token=token)
