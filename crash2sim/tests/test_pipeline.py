"""Fast checks: every ground-truth spec validates, builds to well-formed XML, and the
rules baseline always emits schema-valid output. Run: pytest -q"""
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from crash2sim import build, extract, schema  # noqa: E402

GT = sorted((ROOT / "data" / "ground_truth").glob("*.json"))
REPORTS = sorted((ROOT / "data" / "reports").glob("*.json"))


def test_ground_truth_valid_and_buildable(tmp_path):
    assert GT
    for p in GT:
        spec = json.loads(p.read_text())
        assert schema.validate(spec) == [], p.name
        clean, _ = schema.sanitize(spec)
        xosc = build.build_xosc(clean, p.stem, tmp_path)
        root = ET.parse(xosc).getroot()
        assert root.tag == "OpenSCENARIO"
        assert "{{" not in xosc.read_text()


def test_rules_backend_schema_valid():
    for p in REPORTS:
        spec, _ = extract.extract(json.loads(p.read_text()), "rules")
        assert schema.validate(spec) == [], p.name


def test_sanitize_fills_missing_gap():
    spec = json.loads(GT[0].read_text())
    if spec["scenario_type"] == "rear_end":
        spec["other"]["gap_m"] = None
        clean, notes = schema.sanitize(spec)
        assert clean["other"]["gap_m"] > 0 and notes
