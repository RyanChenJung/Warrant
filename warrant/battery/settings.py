"""The battery's normalisation setting (#31), as the freeze's `global.battery.normalisation` writes it.

Kept apart from `warrant.battery.normalise` so that freeze validation can check the setting without
importing the battery (DuckDB and the vendored detectors).
"""

from dataclasses import dataclass
from typing import Literal, get_args

Setting = Literal["keep", "round", "drop"]
SETTINGS = get_args(Setting)


@dataclass(frozen=True)
class Normalisation:
    counts: Setting = "keep"
    percentages: Setting = "keep"

    @classmethod
    def parse(cls, value) -> "Normalisation":
        """The setting as the freeze writes it: `exact`, or `{counts: ..., percentages: ...}`."""
        if value == "exact":
            return cls()
        if isinstance(value, dict) and set(value) == {"counts", "percentages"} and all(
                v in SETTINGS for v in value.values()):
            return cls(**value)
        raise ValueError(
            f"battery normalisation must be 'exact' or {{counts: ..., percentages: ...}}, each one of "
            f"{', '.join(SETTINGS)}; got {value!r}")

    @classmethod
    def from_freeze(cls, raw: dict) -> "Normalisation":
        """The setting in a freeze read from YAML: `global.battery.normalisation`."""
        return cls.parse(((raw.get("global") or {}).get("battery") or {}).get("normalisation"))


EXACT = Normalisation()
