from __future__ import annotations

import inspect
from typing import Any, Callable, ClassVar, Dict, List, Mapping, Sequence, Tuple, Type, Union

from pydantic import BaseConfig, BaseModel, Extra, Field
from pydantic.fields import FieldInfo
from pydantic.main import ModelMetaclass
from pydantic.utils import deep_update
from typing_extensions import Self, dataclass_transform

from . import registry as reg
from ._utils import get_server_env, pascal_case
from .sources import InitSource, SettingsSource


@dataclass_transform(kw_only_default=True, field_descriptors=(Field, FieldInfo))
class SettingsMeta(ModelMetaclass):
    __singleton__: ClassVar[bool]
    __instances__: ClassVar[Dict[Type[Self], Self]]

    def __new__(
        cls, name: str, bases: Tuple[Type[Any], ...], namespace: Mapping[str, Any], **kwargs: Any,
    ):
        self_config: Type[BaseConfig] = namespace.get("Config", BaseConfig)
        ns = dict(namespace)
        server_env = kwargs.get("server_env", None)
        if server_env is None:
            server_env = getattr(self_config, "server_env", get_server_env)

        singleton = kwargs.get("singleton", None)
        if singleton is None:
            singleton = getattr(self_config, "singleton", True)

        if callable(server_env):
            server_env = str(server_env()).lower()

        if server_env:
            config_ns = {"env_file": f".env.{server_env}"}
            config_name = pascal_case(f"{server_env}_config")
            env_config = ns.get(config_name, None)
            if isinstance(env_config, type):
                config_ns.update({n: v for n, v in inspect.getmembers(env_config) if not n.startswith("_")})
        else:
            config_ns = {"env_file": ".env"}

        config_ns.update(kwargs)

        ns["Config"] = type("Config", (self_config,), config_ns)
        ns["__singleton__"] = singleton
        ns["__instances__"] = {}
        return super().__new__(cls, name, bases, ns)

    def __call__(cls, *args: Any, **kwargs: Any) -> Self:
        if not cls.__singleton__:
            return super().__call__(*args, **kwargs)

        if cls not in cls.__instances__:
            cls.__instances__[cls] = super().__call__(*args, **kwargs)
        return cls.__instances__[cls]


class Settings(BaseModel, metaclass=SettingsMeta):
    class Config(BaseConfig):
        sources: Sequence[str] = ()
        server_env: Union[str, Callable[[], str]] = get_server_env
        singleton: bool = True
        case_sensitive: bool = False
        validate_all: bool = True
        extra: Extra = Extra.allow
        arbitrary_types_allowed: bool = True
        allow_mutation: bool = False

    __config__: ClassVar[Type[Config]]

    def __init__(self, **values: Any) -> None:
        values = self._build_values(values)
        super().__init__(**values)

    def _build_values(self, values: Dict[str, Any]) -> Dict[str, Any]:
        default_registry = reg.__registry__.get("default", {})

        if callable(self.__config__.server_env):
            server_env = str(self.__config__.server_env()).lower()
        elif isinstance(self.__config__.server_env, str):
            server_env = str(self.__config__.server_env).lower()
        else:
            server_env = "default"

        env_sources = reg.__registry__.get(server_env, {})
        sources = {**default_registry, **env_sources}

        if unk := next((x for x in self.__config__.sources if x not in sources), None):
            raise ValueError(f"Settings source '{unk}' not found. Did you forget to `register_settings_source`?")

        def exclude(name: str) -> bool:
            return name.startswith("_")

        options = {n: v for n, v in inspect.getmembers(self.__config__) if not exclude(n)}
        options["server_env"] = server_env

        config_sources: List[SettingsSource] = [InitSource(values)]
        for s in self.__config__.sources:
            factory = sources[s]
            sig = inspect.signature(factory)
            bound = sig.bind_partial(**{n: v for n, v in options.items() if n in sig.parameters})
            bound.apply_defaults()
            config_sources.append(factory(*bound.args, **bound.kwargs))

        return deep_update(*reversed([source(self) for source in config_sources]))
