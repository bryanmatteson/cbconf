from collections import Counter
from typing import Any, Callable, Dict, Generic, Iterable, Iterator, MutableMapping, TypeVar
from urllib.parse import parse_qs, urlencode


class Params(MutableMapping[str, Any]):
    @classmethod
    def __get_validators__(cls) -> Iterator[Callable[[Any], Any]]:
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> Any:
        if not v:
            return cls()

        order = ["&", ",", ";", "\n"]
        if isinstance(v, str):
            separator = next((k for k, _ in Counter(v).most_common() if k in order), "&")
            return cls(parse_qs(v, separator=separator), separator=separator)

        if isinstance(v, dict):
            return cls(v)

        return v

    _params: Dict[str, Any]

    def __init__(self, value: Dict[str, Any] = {}, *, separator: str = "&") -> None:
        self._params = value
        self._separator = separator

    def __getitem__(self, key: str):
        return self._params[key]

    def __setitem__(self, key: str, item: Any):
        self._params[key] = item

    def __delitem__(self, key: str):
        del self._params[key]

    def __iter__(self):
        return iter(self._params)

    def __len__(self):
        return len(self._params)

    def __str__(self) -> str:
        return urlencode(self._params, doseq=True).replace("&", self._separator)


_T = TypeVar("_T")


class DelimitedList(Generic[_T]):
    @classmethod
    def __get_validators__(cls) -> Iterator[Callable[[Any], Any]]:
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> Any:
        order = [",", "\n", ";", "&"]
        separator = next((k for k, _ in Counter(v).most_common() if k in order), ",")
        if isinstance(v, str):
            if not v:
                return cls()

            return cls([x.strip() for x in v.split(separator)], delimiter=separator)

        return v

    def __init__(self, value: Iterable[_T] = [], *, delimiter: str = ",") -> None:
        self._delimiter = delimiter
        self._list = [x for x in value] if not isinstance(value, list) else value

    def __iter__(self) -> Iterator[_T]:
        return iter(self._list)

    def __getitem__(self, index: int) -> Any:
        return self._list[index]

    def __setitem__(self, index: int, item: Any) -> None:
        self._list[index] = item

    def __delitem__(self, index: int) -> None:
        del self._list[index]

    def __len__(self) -> int:
        return len(self._list)

    def __str__(self) -> str:
        return self._delimiter.join(str(x) for x in self._list)

    def insert(self, index: int, value: Any) -> None:
        self._list.insert(index, value)

    def __repr__(self) -> str:
        return repr(self._list)
