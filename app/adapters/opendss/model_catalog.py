from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuiltinModel:
    id: str
    name: str
    master: Path


def builtin_models(networks_root: Path) -> dict[str, BuiltinModel]:
    return {
        "ieee13": BuiltinModel("ieee13", "IEEE 13 Node Test Feeder", networks_root / "ieee13" / "IEEE13Nodeckt.dss"),
        "ieee34": BuiltinModel("ieee34", "IEEE 34 Bus Test Feeder", networks_root / "ieee34" / "ieee34Mod1.dss"),
        "ieee123": BuiltinModel("ieee123", "IEEE 123 Node Test Feeder", networks_root / "ieee123" / "IEEE123Master.dss"),
    }
