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
        spec = {k: v for k, v in json.loads(p.read_text()).items() if k != "validation_targets"}
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
    spec = json.loads((ROOT / "data" / "ground_truth" / "CISS_A1.json").read_text())
    if spec["scenario_type"] == "rear_end":
        spec["other"]["gap_m"] = None
        clean, notes = schema.sanitize(spec)
        assert clean["other"]["gap_m"] > 0 and notes


def test_ciren_converter_drops_personal_data():
    sys.path.insert(0, str(ROOT / "scripts"))
    from ciren_to_report import scrub_narrative
    txt = "This crash involves a seriously-injured 32-year-old driver.\nV1, driven by the 32-year-old female driver (CIREN case subject), went west.\nThe driver was transported to a hospital."
    out = scrub_narrative(txt)
    assert "year-old" not in out and "hospital" not in out and "injur" not in out
    assert "went west" in out
