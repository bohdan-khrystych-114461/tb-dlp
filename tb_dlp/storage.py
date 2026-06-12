from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Generic, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class JSONStore(Generic[T]):
    """Loads/saves a single JSON file, falling back to a default value when
    the file is missing, unreadable, or malformed.

    `decode`/`encode` convert between the JSON-native shape (lists,
    string-keyed dicts) and the in-memory shape (sets, int-keyed dicts,
    tuples) — both default to the identity transform.
    """

    def __init__(
        self,
        path: str,
        default: Callable[[], T],
        *,
        decode: Callable[[object], T] | None = None,
        encode: Callable[[T], object] | None = None,
    ) -> None:
        self.path = Path(path)
        self._default = default
        self._decode = decode or (lambda raw: raw)
        self._encode = encode or (lambda value: value)

    def load(self) -> T:
        try:
            raw = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return self._default()
        try:
            return self._decode(raw)
        except (TypeError, ValueError, KeyError):
            log.exception("Malformed data in %s, using default", self.path)
            return self._default()

    def save(self, value: T) -> None:
        try:
            self.path.write_text(json.dumps(self._encode(value)))
        except OSError:
            log.exception("Failed to persist %s", self.path)
