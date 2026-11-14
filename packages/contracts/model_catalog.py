from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinModelSpec:
    id: str
    name: str
    master_relative: str


BUILTIN_MODEL_SPECS: dict[
    str,
    BuiltinModelSpec,
] = {
    "ieee13": BuiltinModelSpec(
        id="ieee13",
        name="IEEE 13 Node Test Feeder",
        master_relative=(
            "ieee13/IEEE13Nodeckt.dss"
        ),
    ),
    "ieee34": BuiltinModelSpec(
        id="ieee34",
        name="IEEE 34 Bus Test Feeder",
        master_relative=(
            "ieee34/ieee34Mod1.dss"
        ),
    ),
    "ieee123": BuiltinModelSpec(
        id="ieee123",
        name="IEEE 123 Node Test Feeder",
        master_relative=(
            "ieee123/IEEE123Master.dss"
        ),
    ),
    "ieee8500": BuiltinModelSpec(
        id="ieee8500",
        name="IEEE 8500 Node Test Feeder",
        master_relative=(
            "ieee8500/Master_cloud.dss"
        ),
    ),
}