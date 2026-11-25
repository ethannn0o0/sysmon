import json

from sysmon.skins import (BUILTIN_SKINS, MIDNIGHT, ensure_user_dir, find_skin, load_skins, mood_for,
                          parse_skin)


def test_mood_thresholds():
    assert mood_for(5, 50) == "idle"
    assert mood_for(5, 85) == "busy"  # memory only matters when high
    assert mood_for(45, 30) == "busy"
    assert mood_for(95, 10) == "overload"
    assert mood_for(10, 95) == "overload"


def test_builtin_skin_names_are_unique():
    names = [s.name for s in BUILTIN_SKINS]
    assert len(names) == len(set(names))


def test_invalid_fields_fall_back_to_defaults(tmp_path):
    skin = parse_skin(
        {"colors": {"bg": "red", "text": "#ABCDEF"}, "bg_alpha": 5, "radius": "big",
         "mascot": {"builtin": "dragon"}},
        tmp_path / "weird",
    )
    assert skin.name == "weird"  # falls back to the folder name
    assert skin.bg == MIDNIGHT.bg and skin.text == "#ABCDEF"
    assert skin.bg_alpha == MIDNIGHT.bg_alpha and skin.radius == MIDNIGHT.radius
    assert skin.mascot_kind is None and not skin.has_mascot


def test_frames_must_stay_inside_skin_folder(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / "idle.png").write_bytes(b"x")
    (tmp_path / "secret.png").write_bytes(b"x")
    skin = parse_skin(
        {"mascot": {"frames": {"idle": "idle.png", "busy": "../secret.png", "overload": "idle.txt"}}}, folder
    )
    assert set(skin.frames) == {"idle"}  # '..' escape and non-image rejected
    assert skin.frame_for("overload") == skin.frames["idle"]  # missing moods reuse idle


def test_frames_without_idle_are_dropped(tmp_path):
    (tmp_path / "busy.png").write_bytes(b"x")
    assert parse_skin({"mascot": {"frames": {"busy": "busy.png"}}}, tmp_path).frames == {}


def test_load_skips_broken_and_duplicate_skins(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    (good / "skin.json").write_text(json.dumps({"name": "Good", "mascot": {"builtin": "cat"}}), encoding="utf-8")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "skin.json").write_text("{not json", encoding="utf-8")
    dup = tmp_path / "dup"
    dup.mkdir()
    (dup / "skin.json").write_text(json.dumps({"name": "Slime"}), encoding="utf-8")  # clashes with built-in
    (tmp_path / "stray-file.txt").write_text("hi")

    names = [s.name for s in load_skins(tmp_path)]
    assert names == [s.name for s in BUILTIN_SKINS] + ["Good"]


def test_missing_user_dir_is_fine(tmp_path):
    assert load_skins(tmp_path / "nope") == list(BUILTIN_SKINS)


def test_find_skin_falls_back_to_first(tmp_path):
    skins = load_skins(tmp_path)
    assert find_skin(skins, "Kitty").name == "Kitty"
    assert find_skin(skins, "deleted-skin").name == skins[0].name


def test_ensure_user_dir_writes_loadable_example(tmp_path):
    d = ensure_user_dir(tmp_path / "skins")
    names = [s.name for s in load_skins(d)]
    assert "Example (edit me)" in names
    ensure_user_dir(d)  # second call must not duplicate or fail
    assert len(list(d.iterdir())) == 1
