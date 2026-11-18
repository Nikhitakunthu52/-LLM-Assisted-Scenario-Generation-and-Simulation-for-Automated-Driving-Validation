"""Crash report -> scenario spec (JSON) using an LLM.

Backends
  ollama : local model through Ollama (default; free, offline). Uses Ollama's
           structured-output mode: the JSON schema is passed as `format`.
  openai : any OpenAI-compatible chat API (OpenAI, Groq, Together, a
           Hugging Face Inference Endpoint, vLLM, LM Studio ...). Set
           LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.
  rules  : keyword/regex baseline with NO LLM. Used for offline testing and
           as the comparison baseline in the demo ("what does the LLM add?").
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

from .schema import SCENARIO_SCHEMA

SYSTEM_PROMPT = """You convert police / NHTSA crash reports into a parameter set for a driving simulator.

Return ONLY a JSON object that matches the provided schema. Rules:
- scenario_type: "rear_end" if one vehicle strikes the back of another in the same lane;
  "ltap_od" if a vehicle turns left across the path of an oncoming vehicle;
  "head_on" if a vehicle crosses the center line and hits an oncoming vehicle front-to-front.
- ego = the STRIKING vehicle in a rear_end, the STRAIGHT-GOING vehicle in an ltap_od, or the vehicle
  that STAYED IN ITS LANE in a head_on.
  other = the struck lead vehicle (rear_end), the left-turning vehicle (ltap_od), or the vehicle
  that departed its lane (head_on).
  In SGO/ADS reports the ADS "subject vehicle" (SV) may be either role - decide from the movements.
- Speeds in km/h (1 mph = 1.609 km/h). Use pre-crash / EDR speeds when given; else infer from
  the posted limit and context.
- other.maneuver: decelerate | stopped | constant_speed (rear_end), left_turn (ltap_od),
  lane_departure (head_on).
- other.brake_ttc_s (head_on): seconds before impact the departing vehicle braked (EDR "Service Brake
  Engaged" at -1.5 s -> 1.5); null if it did not brake. Use EDR speed at -5 s as other.speed_kph.
- other.speed_kph is its initial speed; final_speed_kph its speed after slowing (0 = stops).
- ego.reacts = true only if the ego driver/system braked or steered before impact.
  reaction_time_s = time from the hazard appearing to braking (alert ~0.8-1.2 s, distracted 2-4 s,
  automated 0.3-0.6 s). brake_decel_mps2: dry 6-8, wet 4-6, icy 2-3. If reacts=false use 0 for both.
- gap_m: initial distance between vehicles for rear_end (null if not derivable); null for ltap_od.
- collision_reported: true if the report says the vehicles made contact.
- assumptions: list EVERY value you did not read directly from the report, with the value used.
- missing_info: facts a simulation engineer would want that the report does not give.
- confidence: high (most values stated), medium (some inferred), low (mostly assumed / redacted).
Never refuse. If text is redacted, use coded fields and typical values and say so in assumptions."""


def report_to_prompt(report: dict) -> str:
    coded = json.dumps(report.get("coded_fields", {}), indent=1)
    edr = ""
    if report.get("edr_precrash"):
        lines = []
        for veh, sigs in report["edr_precrash"].items():
            for sig, series in sigs.items():
                lines.append(f"{veh} {sig}: " + ", ".join(f"{t:+.1f}s={v}" for t, v in series))
        edr = "\n\nEDR PRE-CRASH DATA (time relative to impact):\n" + "\n".join(lines)
    return (f"REPORT SOURCE: {report.get('source_type', 'unknown')}\n\n"
            f"NARRATIVE:\n{report.get('narrative', '')}\n\nCODED FIELDS:\n{coded}{edr}\n\n"
            "Produce the scenario JSON.")


def _parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"LLM did not return JSON: {text[:200]}")
    return json.loads(m.group(0))


# ---------------------------------------------------------------- backends
def extract_ollama(report: dict, model: str | None = None) -> dict:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
    model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    body = {
        "model": model,
        "stream": False,
        "format": SCENARIO_SCHEMA,          # structured outputs (Ollama >= 0.5)
        "options": {"temperature": 0, "seed": 42},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": report_to_prompt(report)}],
    }
    r = requests.post(url, json=body, timeout=300)
    r.raise_for_status()
    return _parse_json(r.json()["message"]["content"])


def extract_openai(report: dict, model: str | None = None) -> dict:
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("LLM_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY not set (see .env.example)")
    model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT + "\n\nJSON schema:\n" + json.dumps(SCENARIO_SCHEMA)},
                     {"role": "user", "content": report_to_prompt(report)}],
    }
    r = requests.post(f"{base}/chat/completions", json=body, timeout=300,
                      headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    return _parse_json(r.json()["choices"][0]["message"]["content"])


def _num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    return float(m.group(1)) if m else None


def extract_rules(report: dict, model: str | None = None) -> dict:
    """No-LLM baseline: keywords + regex. Deliberately simple."""
    coded = report.get("coded_fields", {})
    text = (report.get("narrative", "") + " " + json.dumps(coded)).lower()
    ltap = any(k in text for k in ["left turn", "turning left", "turn left", "making left"])
    head_on = "head-on" in text or "head on" in text
    stype = "head_on" if head_on else "ltap_od" if ltap else "rear_end"

    light = "night" if "dark" in text else "dusk" if "dusk" in text or "dawn" in text else "day"
    weather = ("rain" if "rain" in text else "snow" if "snow" in text else
               "fog" if "fog" in text else "clear")
    surface = "wet" if "wet" in text else "icy" if "ice" in text or "icy" in text else "dry"

    speeds = [float(x) for x in re.findall(r"(\d{2,3})\s*km/h", text)]
    speeds += [round(float(x) * 1.609, 1) for x in re.findall(r"(\d{2,3})\s*mph", text)]
    limit = _num(r"speed_limit_kph\"?:\s*(\d+)", text) or (
        (_num(r"speed limit \(mph\)\"?:\s*(\d+)", text) or 0) * 1.609) or 50.0
    ego_speed = max(speeds) if speeds else limit
    braked = any(k in text for k in ["braked", "brake application", "braking"])
    stopped = "stopped" in text and stype == "rear_end"

    return {
        "scenario_type": stype,
        "environment": {"light": light, "weather": weather, "surface": surface},
        "ego": {"vehicle": "car", "speed_kph": ego_speed, "reacts": braked and not stopped,
                "reaction_time_s": 1.5 if braked else 0, "brake_decel_mps2": 6.0 if braked else 0},
        "other": {"vehicle": "car",
                  "maneuver": "lane_departure" if head_on else "left_turn" if ltap else
                              ("stopped" if stopped else "decelerate"),
                  "speed_kph": 15.0 if ltap else (0.0 if stopped else ego_speed),
                  "final_speed_kph": 15.0 if ltap else 0.0,
                  "decel_mps2": 0.0 if ltap else 3.0, "gap_m": None,
                  "brake_ttc_s": None},
        "collision_reported": any(k in text for k in ["struck", "contact", "collision", "impact"]),
        "assumptions": ["rules baseline: generic defaults for vehicles, reaction, deceleration"],
        "missing_info": [],
        "confidence": "low",
    }


BACKENDS = {"ollama": extract_ollama, "openai": extract_openai, "rules": extract_rules}


def extract(report: dict, backend: str = "ollama", model: str | None = None,
            retries: int = 2) -> tuple[dict, float]:
    """Return (spec, seconds). Retries on malformed output."""
    fn = BACKENDS[backend]
    last = None
    for _ in range(retries + 1):
        t0 = time.time()
        try:
            return fn(report, model), time.time() - t0
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            last = e
    raise RuntimeError(f"{backend} failed after {retries + 1} attempts: {last}")
