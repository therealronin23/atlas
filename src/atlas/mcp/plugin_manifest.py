"""Declarative PluginManifest v1; executable plugins are deliberately excluded."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


_PluginId = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9-]{2,63}$", min_length=3, max_length=64),
]
_Text = Annotated[str, Field(min_length=1, max_length=512)]
_Permission = Literal["read_context", "write_workspace", "network"]
_ContributionKind = Literal["skill", "prompt", "rule", "command"]


class PluginSource(_StrictModel):
    """Provenance asserted by the staging producer, never fetched by A2."""

    origin: _Text
    revision: _Text
    license: _Text


class PluginContribution(_StrictModel):
    contribution_id: _PluginId
    kind: _ContributionKind
    path: _Text

    @field_validator("path")
    @classmethod
    def _require_safe_markdown_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("contribution path must use POSIX separators")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.suffix.lower() != ".md"
        ):
            raise ValueError("contribution path must be a relative Markdown file")
        return path.as_posix()


class PluginManifest(_StrictModel):
    """A static contribution manifest, not a loader for third-party code."""

    schema_version: Literal["1.0"]
    plugin_id: _PluginId
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    version: Annotated[str, Field(min_length=1, max_length=120)]
    source: PluginSource
    activation: Literal["declarative"]
    permissions: Annotated[list[_Permission], Field(max_length=0)]
    contributions: Annotated[list[PluginContribution], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def _require_unique_contributions(self) -> "PluginManifest":
        ids = [item.contribution_id for item in self.contributions]
        paths = [item.path for item in self.contributions]
        if len(ids) != len(set(ids)):
            raise ValueError("contribution_id values must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("contribution paths must be unique")
        return self
