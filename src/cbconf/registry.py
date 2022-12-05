from __future__ import annotations

from functools import partial
from typing import Any, Callable, Dict, Optional

from cbconf.sources import EnvSource, IniFileSource, SecretsSource, SettingsSource

SourceFactory = Callable[..., SettingsSource]

__sources__: Dict[str, Any] = {"env": EnvSource, "ini": IniFileSource, "secrets": SecretsSource}
__registry__: Dict[str, Dict[str, Any]] = {"default": __sources__.copy()}


class Source:
    def __init__(self, name: str, factory: SourceFactory):
        self.name = name
        self.factory = factory

    def configure(self, env: str = "default", **options: Any) -> Source:
        __registry__[env][self.name] = partial(self.factory, **options)
        return self


def register(factory: SourceFactory, name: str, configuration: Optional[Dict[str, Dict[str, Any]]] = None) -> Source:
    if name in __sources__:
        raise ValueError(f"Settings source '{name}' already registered")

    __sources__[name] = factory
    __registry__["default"][name] = factory
    source = Source(name, factory)

    if configuration:
        for env, options in configuration.items():
            source.configure(env, **options)
    return source


def configure(name: str, env: str = "default", **options: Any) -> Source:
    if name not in __sources__:
        raise ValueError(f"Settings source '{name}' not registered")

    __registry__[env][name] = partial(__sources__[name], **options)
    return Source(name, __sources__[name])
