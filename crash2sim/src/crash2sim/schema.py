"""Intermediate scenario specification.

The LLM never writes OpenSCENARIO XML directly. It fills in this small, typed
JSON object; the builder turns a validated object into .xosc via templates.
That keeps every generated scenario runnable.
"""
from __future__ import annotations

import copy
from jsonschema import Draft202012Validator

VEHICLES = ["car", "suv", "pickup", "truck", "van", "bus", "motorcycle"]

SCENARIO_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scenario_type", "environment", "ego", "other", "collision_reported",
                 "assumptions", "missing_info", "confidence"],
    "properties": {
        "scenario_type": {
            "type": "string",
            "enum": ["rear_end", "ltap_od"],
            "description": "rear_end = ego follows and strikes a lead vehicle in the same lane; "
                           "ltap_od = other vehicle turns left across ego's path from the opposite direction",
        },
        "environment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["light", "weather", "surface"],
            "properties": {
                "light": {"type": "string", "enum": ["day", "dusk", "night"]},
                "weather": {"type": "string", "enum": ["clear", "rain", "fog", "snow"]},
                "surface": {"type": "string", "enum": ["dry", "wet", "icy"]},
            },
        },
        "ego": {
            "type": "object",
            "additionalProperties": False,
            "description": "Ego = the striking / straight-going vehicle whose behaviour we test",
            "required": ["vehicle", "speed_kph", "reacts", "reaction_time_s", "brake_decel_mps2"],
            "properties": {
                "vehicle": {"type": "string", "enum": VEHICLES},
                "speed_kph": {"type": "number", "minimum": 0, "maximum": 200},
                "reacts": {"type": "boolean", "description": "true if the ego driver/system braked before impact"},
                "reaction_time_s": {"type": "number", "minimum": 0, "maximum": 10,
                                    "description": "seconds from hazard onset to brake application"},
                "brake_decel_mps2": {"type": "number", "minimum": 0, "maximum": 12},
            },
        },
        "other": {
            "type": "object",
            "additionalProperties": False,
            "required": ["vehicle", "maneuver", "speed_kph", "final_speed_kph", "decel_mps2", "gap_m"],
            "properties": {
                "vehicle": {"type": "string", "enum": VEHICLES},
                "maneuver": {"type": "string",
                             "enum": ["decelerate", "stopped", "constant_speed", "left_turn"]},
                "speed_kph": {"type": "number", "minimum": 0, "maximum": 200},
                "final_speed_kph": {"type": "number", "minimum": 0, "maximum": 200},
                "decel_mps2": {"type": "number", "minimum": 0, "maximum": 12},
                "gap_m": {"type": ["number", "null"], "minimum": 0, "maximum": 300,
                          "description": "rear_end only: initial distance between vehicles; null if unknown"},
            },
        },
        "collision_reported": {"type": "boolean"},
        "assumptions": {"type": "array", "items": {"type": "string"},
                        "description": "every value NOT stated in the report that had to be assumed"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}

_validator = Draft202012Validator(SCENARIO_SCHEMA)


def validate(spec: dict) -> list[str]:
    """Return a list of human-readable schema errors (empty list = valid)."""
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in sorted(_validator.iter_errors(spec), key=str)]


def sanitize(spec: dict) -> tuple[dict, list[str]]:
    """Fill physically-required defaults and clamp values the simulator can't use.

    Returns (clean_spec, notes). Notes are appended to the spec's assumptions so
    nothing is silently changed.
    """
    s = copy.deepcopy(spec)
    notes: list[str] = []
    ego, oth = s["ego"], s["other"]

    if s["scenario_type"] == "rear_end":
        if oth["maneuver"] == "left_turn":
            oth["maneuver"] = "decelerate"
            notes.append("pipeline: left_turn invalid for rear_end, changed to decelerate")
        if oth["maneuver"] == "stopped":
            oth["speed_kph"] = oth["final_speed_kph"] = 0.0
        if oth["maneuver"] == "constant_speed":
            oth["final_speed_kph"] = oth["speed_kph"]
        if oth["maneuver"] == "decelerate" and oth["decel_mps2"] <= 0:
            oth["decel_mps2"] = 3.0
            notes.append("pipeline: lead deceleration missing, assumed 3.0 m/s^2")
        if oth["gap_m"] is None:
            v = ego["speed_kph"] / 3.6
            oth["gap_m"] = round(max(10.0, (6.0 if oth["maneuver"] == "stopped" else 1.5) * v), 1)
            notes.append(f"pipeline: initial gap unknown, assumed {oth['gap_m']} m")
    else:  # ltap_od
        oth["maneuver"] = "left_turn"
        oth["gap_m"] = None
        if oth["speed_kph"] <= 0:
            oth["speed_kph"] = 20.0
            notes.append("pipeline: turning vehicle speed missing, assumed 20 km/h")
        if oth["final_speed_kph"] <= 0:
            oth["final_speed_kph"] = oth["speed_kph"]

    if ego["speed_kph"] < 5:
        ego["speed_kph"] = 30.0
        notes.append("pipeline: ego speed missing/too low, assumed 30 km/h")
    if ego["reacts"] and ego["brake_decel_mps2"] <= 0:
        ego["brake_decel_mps2"] = 6.0
        notes.append("pipeline: ego braking level missing, assumed 6.0 m/s^2")

    s["assumptions"] = list(s.get("assumptions", [])) + notes
    return s, notes
