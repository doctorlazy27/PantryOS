from dataclasses import dataclass


@dataclass(frozen=True)
class TemperatureRange:
    minimum_c: float
    maximum_c: float


ZONE_RANGES = {
    "AMBIENT": TemperatureRange(10.0, 25.0),
    "CHILLED": TemperatureRange(0.0, 5.0),
    "FROZEN": TemperatureRange(-30.0, -18.0),
}


def temperature_range(zone: str) -> TemperatureRange:
    try:
        return ZONE_RANGES[zone.upper()]
    except KeyError as error:
        raise ValueError(f"Unsupported storage zone: {zone}") from error


def temperature_is_safe(zone: str, temperature_c: float) -> bool:
    allowed = temperature_range(zone)
    return allowed.minimum_c <= temperature_c <= allowed.maximum_c