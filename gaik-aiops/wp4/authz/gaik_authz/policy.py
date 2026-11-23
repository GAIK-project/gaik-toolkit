"""Role-to-permission policy loaded from configuration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml


class PolicyError(ValueError):
    pass


class Policy:
    def __init__(self, roles: Mapping[str, Mapping]) -> None:
        self._permissions: dict[str, frozenset[str]] = {}
        for name in roles:
            self._permissions[name] = frozenset(self._resolve(roles, name, ()))

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls(data.get("roles") or {})

    @staticmethod
    def _resolve(roles: Mapping[str, Mapping], name: str, seen: tuple[str, ...]) -> set[str]:
        if name in seen:
            raise PolicyError(f"role include cycle: {' -> '.join((*seen, name))}")
        if name not in roles:
            raise PolicyError(f"unknown role in include: {name}")
        spec = roles[name] or {}
        perms = set(spec.get("permissions") or [])
        for included in spec.get("includes") or []:
            perms |= Policy._resolve(roles, included, (*seen, name))
        return perms

    @property
    def roles(self) -> frozenset[str]:
        return frozenset(self._permissions)

    def permissions_for(self, roles: Iterable[str]) -> frozenset[str]:
        """Union of permissions of the known roles; unknown roles grant nothing."""
        out: set[str] = set()
        for role in roles:
            out |= self._permissions.get(role, frozenset())
        return frozenset(out)

    def allows(self, roles: Iterable[str], permission: str) -> bool:
        return permission in self.permissions_for(roles)
