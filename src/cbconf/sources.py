import os
import re
import warnings
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)

from pydantic import BaseModel
from pydantic.fields import ModelField
from pydantic.typing import StrPath, get_origin, is_union
from pydantic.utils import deep_update, path_type
from typing_extensions import TypeAlias

from .errors import SettingsError

if TYPE_CHECKING:
    from .settings import Settings  # noqa

SettingsType: TypeAlias = "Settings"


@runtime_checkable
class SettingsSource(Protocol):
    def __call__(self, model: BaseModel) -> Dict[str, Any]:
        ...


class InitSource(SettingsSource):
    __slots__ = "values"

    def __init__(self, values: Dict[str, Any]):
        self.values = values

    def __call__(self, model: BaseModel) -> Dict[str, Any]:
        return self.values.copy()

    def __repr__(self) -> str:
        return f"InitSource(values={self.values!r})"


class EnvSource(SettingsSource):
    env_file: Optional[StrPath]
    env_file_encoding: Optional[str]
    env_nested_delimiter: Optional[str]
    env_prefix: Optional[str]

    def __init__(
        self,
        *,
        env_file: Optional[StrPath] = None,
        env_file_encoding: Optional[str] = None,
        env_nested_delimiter: Optional[str] = None,
        env_prefix: Optional[str] = None,
        case_sensitive: bool = True,
    ) -> None:
        self.env_file = env_file
        self.env_file_encoding = env_file_encoding
        self.env_nested_delimiter = env_nested_delimiter
        self.env_prefix = env_prefix
        self.case_sensitive = case_sensitive

    def __call__(self, model: BaseModel) -> Dict[str, Any]:  # noqa: C901
        d: Dict[str, Any] = {}

        if self.case_sensitive:
            env_vars: Mapping[str, Optional[str]] = os.environ
        else:
            env_vars = {k.lower(): v for k, v in os.environ.items()}

        if self.env_file is not None:
            env_path = Path(self.env_file).expanduser()
            if env_path.is_file():
                env_vars = {
                    **self._read_env_file(
                        env_path, encoding=self.env_file_encoding, case_sensitive=self.case_sensitive,
                    ),
                    **env_vars,
                }

        xform = str.lower if not self.case_sensitive else lambda x: x

        json_loads = model.__config__.json_loads

        for field in model.__fields__.values():
            env_val: Optional[str] = None
            env_name: str = ""

            if pattern := field.field_info.extra.get("matchfull", None):
                for k, v in env_vars.items():
                    if match := re.fullmatch(pattern, k):
                        if field.alias not in d:
                            d[field.alias] = {}
                        groups = match.groups()
                        if len(groups) == 1:
                            d[field.alias][groups[0].lower()] = v
                        else:
                            d[field.alias][groups[1].lower()] = v
            else:
                env_names = _get_source_names(field, "env", transform=xform)
                if self.env_prefix:
                    env_names = [f"{self.env_prefix}{name}" for name in env_names]

                for env_name in env_names:
                    env_val = env_vars.get(env_name)
                    if env_val is not None:
                        break

                is_complex, allow_json_failure = self.field_is_complex(field)
                if is_complex:
                    if env_val is None:
                        # field is complex but no value found so far, try explode_env_vars
                        env_val_built = self.explode_env_vars(env_vars, env_names, self.env_nested_delimiter)
                        if env_val_built:
                            d[field.alias] = env_val_built
                    else:
                        # field is complex and there's a value, decode that as JSON, then add explode_env_vars
                        try:
                            env_val = json_loads(env_val)
                        except ValueError as e:
                            if not allow_json_failure:
                                raise SettingsError(f'error parsing JSON for "{env_name}"') from e

                        if isinstance(env_val, dict):
                            d[field.alias] = deep_update(
                                env_val, self.explode_env_vars(env_vars, env_names, self.env_nested_delimiter)
                            )
                        else:
                            d[field.alias] = env_val
                elif env_val is not None:
                    # simplest case, field is not complex, we only need to add the value if it was found
                    d[field.alias] = env_val

        return d

    def field_is_complex(self, field: ModelField) -> Tuple[bool, bool]:
        if field.is_complex():
            allow_json_failure = False
        elif is_union(get_origin(field.type_)) and field.sub_fields and any(f.is_complex() for f in field.sub_fields):
            allow_json_failure = True
        else:
            return False, False

        return True, allow_json_failure

    def explode_env_vars(
        self, env_vars: Mapping[str, Optional[str]], env_names: List[str], env_nested_delimiter: Optional[str]
    ) -> Dict[str, Any]:
        env_nested_delimiter = env_nested_delimiter or ""
        prefixes = [f"{env_name}{env_nested_delimiter}" for env_name in env_names]
        result: Dict[str, Any] = {}
        for env_name, env_val in env_vars.items():
            if not any(env_name.startswith(prefix) for prefix in prefixes):
                continue
            _, *keys, last_key = env_name.split(env_nested_delimiter)
            env_var = result
            for key in keys:
                env_var = env_var.setdefault(key, {})
            env_var[last_key] = env_val

        return result

    def _read_env_file(
        self, file_path: StrPath, *, encoding: Optional[str] = None, case_sensitive: bool = False,
    ) -> Dict[str, Optional[str]]:
        try:
            from dotenv import dotenv_values
        except ImportError as e:
            raise ImportError("python-dotenv is not installed") from e

        file_vars: Dict[str, Optional[str]] = dotenv_values(file_path, encoding=encoding or "utf8")
        if not case_sensitive:
            return {k.lower(): v for k, v in file_vars.items()}
        else:
            return file_vars

    def __repr__(self) -> str:
        return (
            f"EnvSource(env_file={self.env_file!r}, env_file_encoding={self.env_file_encoding!r}, "
            "env_nested_delimiter={self.env_nested_delimiter!r}, env_prefix={self.env_prefix!r})"
        )


class SecretsSource(SettingsSource):
    def __init__(self, secrets_dir: Optional[StrPath] = None, case_sensitive: bool = False) -> None:
        self.secrets_dir = secrets_dir
        self.case_sensitive = case_sensitive

    def __call__(self, model: BaseModel) -> Dict[str, Any]:  # noqa: C901
        secrets: Dict[str, Optional[str]] = {}

        if self.secrets_dir is None:
            return secrets

        secrets_path = Path(self.secrets_dir).expanduser()

        if not secrets_path.exists():
            warnings.warn(f'directory "{secrets_path}" does not exist')
            return secrets

        if not secrets_path.is_dir():
            raise SettingsError(f"secrets_dir must reference a directory, not a {path_type(secrets_path)}")

        xform = str.lower if not self.case_sensitive else None
        json_loads = model.__config__.json_loads

        for field in model.__fields__.values():
            env_names = _get_source_names(field, "env", transform=xform)
            for env_name in env_names:
                path = secrets_path / env_name
                if path.is_file():
                    secret_value = path.read_text().strip()
                    if field.is_complex():
                        try:
                            secret_value = json_loads(secret_value)
                        except ValueError as e:
                            raise SettingsError(f'error parsing JSON for "{env_name}"') from e

                    secrets[field.alias] = secret_value
                elif path.exists():
                    warnings.warn(
                        f'attempted to load secret file "{path}" but found a {path_type(path)} instead.', stacklevel=4,
                    )

        return secrets

    def __repr__(self) -> str:
        return f"SecretsSource(secrets_dir={self.secrets_dir!r})"


class IniFileSource(SettingsSource):
    ini_file: Optional[StrPath]
    ini_file_encoding: Optional[str]
    ini_default_section: Optional[str]

    def __init__(
        self,
        *,
        ini_file: Optional[StrPath] = None,
        ini_file_encoding: Optional[str] = None,
        ini_default_section: Optional[str] = None,
        case_sensitive: bool = False,
    ) -> None:
        self.ini_file = ini_file
        self.ini_file_encoding = ini_file_encoding
        self.ini_default_section = ini_default_section
        self.case_sensitive = case_sensitive

    def __call__(self, model: BaseModel) -> Dict[str, Any]:  # noqa: C901
        if self.ini_file is None:
            return {}

        ini_file = Path(self.ini_file).expanduser()
        if not ini_file.exists():
            raise SettingsError(f'ini_file "{ini_file}" does not exist')

        if not ini_file.is_file():
            raise SettingsError(f'ini_file "{ini_file}" is not a file')

        from configparser import ConfigParser

        parser = ConfigParser()
        parser.read(ini_file, encoding=self.ini_file_encoding)

        ini_default_section = self.ini_default_section
        if ini_default_section is None:
            ini_default_section = parser.default_section
        elif ini_default_section not in parser.sections():
            raise SettingsError(f'ini_default_section "{ini_default_section}" does not exist')

        result: Dict[str, Any] = {}
        for field in model.__fields__.values():
            section = field.field_info.extra.get("ini_section", ini_default_section)
            key = field.field_info.extra.get("ini", field.name)

            if not self.case_sensitive:
                section = section.lower()
                key = key.lower()

            if value := parser.get(section, key, raw=True, fallback=None):
                result[field.alias] = value

        return result


def _get_source_names(field: ModelField, extra: str, *, transform: Optional[Callable[[str], str]] = None) -> List[str]:
    source_names: Union[str, Iterable[str]] = field.field_info.extra.get(extra, field.name)
    if isinstance(source_names, str):
        source_names = [source_names]
    else:
        source_names = list(source_names)
    if transform is not None:
        source_names = [transform(name) for name in source_names]
    return source_names
