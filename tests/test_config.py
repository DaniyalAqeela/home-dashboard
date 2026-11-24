import json

from dashboard import config, fsutil


def test_defaults_roundtrip():
    d = config.default_config()
    assert config.normalize(d) == d
    types = [w["type"] for w in d["widgets"]]
    assert types == ["photos", "clock", "shalat", "weather", "news"]


def test_normalize_bad_types():
    c = config.normalize({"display": {"rotation": "45", "scale": "x"}})
    assert c["display"]["rotation"] == 0
    assert c["display"]["scale"] == 1.0
    assert config.normalize("garbage") == config.default_config()


def test_normalize_drops_unknown_widget():
    c = config.normalize({"widgets": [{"type": "evil"}, {"type": "clock"}]})
    assert [w["type"] for w in c["widgets"]] == ["clock"]
    assert c["widgets"][0]["id"]


def test_normalize_clamps_widget_geometry():
    c = config.normalize({"widgets": [{"type": "clock", "id": "a", "x": 95, "y": -5, "w": 50, "h": 500}]})
    w = c["widgets"][0]
    assert (w["x"], w["y"], w["w"], w["h"]) == (95, 0, 5, 100)


def test_normalize_widget_options_and_style():
    c = config.normalize({"widgets": [{"type": "clock", "id": "a",
                                       "options": {"hour24": "yes", "bogus": 1},
                                       "style": {"fontSize": 99999, "align": "diagonal"}}]})
    w = c["widgets"][0]
    assert w["options"]["hour24"] is True
    assert "bogus" not in w["options"]
    assert w["style"]["fontSize"] == 400
    assert w["style"]["align"] == "center"  # falls back to the clock type's default


def test_normalize_times_and_colors():
    c = config.normalize({"display": {"schedule": {"off": "25:99", "on": "6:5"}}, "theme": {"background": "red"}})
    assert c["display"]["schedule"]["off"] == "23:00"
    assert c["display"]["schedule"]["on"] == "06:05"
    assert c["theme"]["background"] == "#000000"


def test_duplicate_widget_ids_fixed():
    c = config.normalize({"widgets": [{"type": "clock", "id": "a"}, {"type": "clock", "id": "a"}]})
    ids = [w["id"] for w in c["widgets"]]
    assert len(set(ids)) == 2


def test_load_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json")
    assert config.load(p) == config.default_config()
    assert config.load(tmp_path / "missing.json") == config.default_config()


def test_save_is_atomic_and_normalized(tmp_path):
    p = tmp_path / "config.json"
    out = config.save(p, {"display": {"rotation": 90}})
    assert out["display"]["rotation"] == 90
    assert json.loads(p.read_text())["display"]["rotation"] == 90
    assert [f.name for f in tmp_path.iterdir()] == ["config.json"]


def test_safe_name():
    assert fsutil.safe_name("../a b?.jpg") == "a_b_.jpg"
    assert fsutil.safe_name("")
    assert not fsutil.safe_name("...").startswith(".")
    assert len(fsutil.safe_name("x" * 300)) <= 80


def test_normalize_unknown_timezone():
    from dashboard.config import normalize
    c = normalize({"location": {"timezone": "Asia/Jakart"}})
    assert c["location"]["timezone"] == normalize({})["location"]["timezone"]
    assert normalize({"location": {"timezone": "Asia/Jakarta"}})["location"]["timezone"] == "Asia/Jakarta"
