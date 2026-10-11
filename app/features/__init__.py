"""Feature builder package: catalogue, engine and Luau code generation."""

from .core import (
    Feature,
    Param,
    Script,
    build_readme,
    build_scripts,
    build_zip,
    catalogue,
    normalise_config,
    preview_code,
    slugify,
)
from .catalog import ALL_FEATURES, CATEGORIES, FEATURES_BY_ID

__all__ = [
    "ALL_FEATURES",
    "CATEGORIES",
    "FEATURES_BY_ID",
    "Feature",
    "Param",
    "Script",
    "build_readme",
    "build_scripts",
    "build_zip",
    "catalogue",
    "normalise_config",
    "preview_code",
    "slugify",
]
