from __future__ import annotations

from bisect import bisect_right


SYNTHETIC_MIXED_DAILY_V1 = "synthetic_mixed_daily_v1"

_HOURLY_PROFILE = (
    (0.0, 0.58),
    (1.0, 0.54),
    (2.0, 0.50),
    (3.0, 0.47),
    (4.0, 0.46),
    (5.0, 0.50),
    (6.0, 0.61),
    (7.0, 0.76),
    (8.0, 0.86),
    (9.0, 0.89),
    (10.0, 0.87),
    (11.0, 0.84),
    (12.0, 0.82),
    (13.0, 0.81),
    (14.0, 0.83),
    (15.0, 0.88),
    (16.0, 0.95),
    (17.0, 1.00),
    (18.0, 0.98),
    (19.0, 0.92),
    (20.0, 0.84),
    (21.0, 0.75),
    (22.0, 0.68),
    (23.0, 0.62),
    (24.0, 0.58),
)


def synthetic_mixed_daily_profile(step_count: int, step_minutes: float) -> list[float]:
    """Generate a deterministic linearly interpolated daily profile."""
    if step_count < 1:
        raise ValueError("step_count debe ser mayor que cero")
    if step_minutes <= 0:
        raise ValueError("step_minutes debe ser mayor que cero")

    profile: list[float] = []
    hourly_times = [hour for hour, _ in _HOURLY_PROFILE]

    for step in range(1, step_count + 1):
        hour = step * step_minutes / 60.0
        if hour >= 24.0:
            profile.append(_HOURLY_PROFILE[-1][1])
            continue

        right_index = bisect_right(hourly_times, hour)
        left_index = max(0, right_index - 1)
        right_index = min(right_index, len(_HOURLY_PROFILE) - 1)
        left_hour, left_value = _HOURLY_PROFILE[left_index]
        right_hour, right_value = _HOURLY_PROFILE[right_index]
        fraction = (hour - left_hour) / (right_hour - left_hour)
        profile.append(left_value + fraction * (right_value - left_value))

    return profile


def qsts_profile(
    profile_source: str,
    step_count: int,
    step_minutes: float,
    load_multiplier: float = 1.0,
) -> list[float] | None:
    if profile_source == "constant":
        return [load_multiplier] * step_count
    if profile_source == "synthetic_daily":
        return synthetic_mixed_daily_profile(step_count, step_minutes)
    if profile_source == "model":
        return None
    if profile_source == "values":
        raise ValueError("profile_source='values' requiere load_multipliers")
    raise ValueError(f"Perfil QSTS no soportado: {profile_source}")
