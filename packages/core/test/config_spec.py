from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from austial import AustialFactory, Inject, Injectable, Module
from austial.config import (
    ConfigModule,
    ConfigService,
    ConfigValidationError,
    expand_variables,
    register_as,
)
from austial.testing import Test


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in ("PORT", "DB_HOST", "A_VAR", "B_VAR", "BASE", "URL", "SECRET", "ONLY_IN_SECOND", "SHARED"):
        monkeypatch.delenv(key, raising=False)


async def _config(**options) -> ConfigService:
    module = await Test.create_testing_module(
        imports=[ConfigModule.for_root(ignore_env_file=True, **options)]
    ).compile()
    return module.get(ConfigService)


async def test_basic_get_default_and_get_or_throw(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "8080")
    config = await _config()
    assert config.get("PORT") == "8080"
    assert config.get("NOPE") is None and config.get("NOPE", "dflt") == "dflt"
    assert config.get_or_throw("PORT") == "8080"
    with pytest.raises(KeyError, match="NOPE"):
        config.get_or_throw("NOPE")
    assert config.has("PORT") and not config.has("NOPE")
    config.set("PORT", "9")
    assert config.get("PORT") == "9" and os.environ["PORT"] == "8080"  # set() doesn't touch the process env


# -- schema validation ---------------------------------------------------------------------


class Settings(BaseModel):
    PORT: int = Field(default=3000, ge=1)
    DB_HOST: str
    DEBUG: bool = False


async def test_validation_schema_coerces_and_applies_defaults(monkeypatch) -> None:
    monkeypatch.setenv("DB_HOST", "db.local")
    monkeypatch.setenv("PORT", "8080")
    config = await _config(validation_schema=Settings)
    assert config.get("PORT") == 8080 and isinstance(config.get("PORT"), int)  # "8080" -> 8080
    assert config.get("DEBUG") is False  # default filled in
    assert config.get("DB_HOST") == "db.local"


async def test_validation_failure_lists_every_problem(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(ConfigValidationError) as caught:
        ConfigModule.for_root(ignore_env_file=True, validation_schema=Settings)
    messages = caught.value.errors
    assert any(m.startswith("PORT") for m in messages) and any(m.startswith("DB_HOST") for m in messages)
    assert "Invalid configuration" in str(caught.value)


async def test_custom_validate_function(monkeypatch) -> None:
    monkeypatch.setenv("SECRET", "short")

    def validate(env):
        if len(env.get("SECRET", "")) < 8:
            raise ValueError("SECRET must be at least 8 characters")
        return env

    with pytest.raises(ConfigValidationError, match="at least 8"):
        ConfigModule.for_root(ignore_env_file=True, validate=validate)

    monkeypatch.setenv("SECRET", "long-enough-secret")
    config = await _config(validate=lambda env: {**env, "SECRET_LEN": len(env["SECRET"])})
    assert config.get("SECRET_LEN") == 18


# -- variable expansion --------------------------------------------------------------------


def test_expand_variables_forms_and_chains() -> None:
    env = {"BASE": "http://x", "URL": "${BASE}/api", "A_VAR": "$BASE!", "B_VAR": "${MISSING:-fallback}-${URL}"}
    out = expand_variables(env)
    assert out["URL"] == "http://x/api"
    assert out["A_VAR"] == "http://x!"
    assert out["B_VAR"] == "fallback-http://x/api"  # references a value that itself references another
    assert expand_variables({"X": "${NOPE}"}) == {"X": ""}
    with pytest.raises(ValueError, match="Circular"):
        expand_variables({"A": "${B}", "B": "${A}"})


async def test_expand_option_reads_and_writes_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("BASE", "http://x")
    monkeypatch.setenv("URL", "${BASE}/api")
    config = await _config(expand=True)
    assert config.get("URL") == "http://x/api" and os.environ["URL"] == "http://x/api"
    monkeypatch.undo()


# -- multiple env files --------------------------------------------------------------------


async def test_multiple_env_files_first_file_wins_and_real_env_beats_both(tmp_path: Path, monkeypatch) -> None:
    first, second = tmp_path / ".env.local", tmp_path / ".env"
    first.write_text("SHARED=from-first\nPORT=1111\n")
    second.write_text("SHARED=from-second\nONLY_IN_SECOND=yes\nPORT=2222\n")
    monkeypatch.setenv("PORT", "9999")  # a real variable
    module = await Test.create_testing_module(imports=[ConfigModule.for_root([str(first), str(second)])]).compile()
    config = module.get(ConfigService)
    assert (config.get("SHARED"), config.get("ONLY_IN_SECOND"), config.get("PORT")) == ("from-first", "yes", "9999")
    for key in ("SHARED", "ONLY_IN_SECOND"):
        os.environ.pop(key, None)


# -- namespaces: register_as, load, for_feature --------------------------------------------


database_config = register_as("database", lambda: {"host": os.environ.get("DB_HOST", "localhost"), "port": 5432})
cache_config = register_as("cache", lambda env: {"ttl": int(env.get("CACHE_TTL", 60))})  # takes the config env


async def test_load_registers_namespaces_with_dotted_access(monkeypatch) -> None:
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("CACHE_TTL", "5")
    config = await _config(load=[database_config, cache_config])
    assert config.get("database.host") == "db.internal"
    assert config.get("database.port") == 5432
    assert config.get("database") == {"host": "db.internal", "port": 5432}
    assert config.get(database_config) == {"host": "db.internal", "port": 5432}
    assert config.get("cache.ttl") == 5
    assert config.get("database.nope", "dflt") == "dflt" and config.get("nonamespace.x") is None
    with pytest.raises(KeyError):
        config.get_or_throw("database.nope")
    assert config.get_or_throw(database_config)["host"] == "db.internal"


async def test_namespace_is_injectable_by_key(monkeypatch) -> None:
    monkeypatch.setenv("DB_HOST", "injected")

    @Injectable()
    class Repo:
        def __init__(self, db=Inject(database_config.KEY)):
            self.db = db

    module = await Test.create_testing_module(
        imports=[ConfigModule.for_root(ignore_env_file=True, load=[database_config])], providers=[Repo]
    ).compile()
    assert module.get(Repo).db["host"] == "injected"


async def test_for_feature_registers_a_namespace_from_a_feature_module(monkeypatch) -> None:
    monkeypatch.setenv("CACHE_TTL", "7")

    @Module(imports=[ConfigModule.for_feature(cache_config)])
    class CacheFeature:
        pass

    @Module(imports=[ConfigModule.for_root(ignore_env_file=True), CacheFeature])
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.init()  # on_module_init registers the namespace eagerly
    assert app.get(ConfigService).get("cache.ttl") == 7
    assert app.get(cache_config.KEY) == {"ttl": 7}
    assert register_as("x", lambda: {"a": 1})() == {"a": 1}  # factories are directly callable too
