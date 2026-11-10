"""Compatibility shim for the built-in OpenDSS model catalog."""

from packages.simulation_core.model_catalog import BuiltinModel, builtin_models

__all__ = ["BuiltinModel", "builtin_models"]