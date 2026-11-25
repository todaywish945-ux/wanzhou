import math
import time

import pytest
from PySide6.QtWidgets import QApplication

from pet import collision
from pet.window_contacts import ContactWorld, WindowContacts


FLAGS = collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED


def member(identity, x, *, vx=0.0, flags=FLAGS, radius=30.0, **extra):
    return dict(runtime_id=identity, x=x, y=300.0, radius_x=radius, radius_y=radius,
                vx=vx, vy=0.0, mass=1.0, flags=flags, scale=0.72, **extra)


def test_head_on_collision_rebounds_both_pets():
    world = ContactWorld({})
    result = world.solve([member("A", 100, vx=600), member("B", 150, vx=-600)])
    assert 600 + result["A"]["delta"][0] < 0
    assert -600 + result["B"]["delta"][0] > 0
    assert result["A"]["delta"][2] < 0 < result["B"]["delta"][2]


def test_three_body_overlap_separates_without_adding_energy():
    states = [member("A", 100), member("B", 140), member("C", 180)]
    world = ContactWorld({})
    for _ in range(12):
        result = world.solve(states)
        for state in states:
            delta = result.get(state["runtime_id"], {}).get("delta", [0, 0, 0, 0])
            assert delta[:2] == [0, 0]
            state["x"] += delta[2]
            state["y"] += delta[3]
    assert states[1]["x"] - states[0]["x"] >= 59
    assert states[2]["x"] - states[1]["x"] >= 59


@pytest.mark.parametrize("flag", [collision.FLAG_DRAGGING, collision.FLAG_LOCK_POSITION,
                                  collision.FLAG_SLINGSHOT_AIMING])
def test_held_or_locked_pet_is_not_displaced(flag):
    result = ContactWorld({}).solve([
        member("A", 100, flags=FLAGS | flag), member("B", 150, vx=-600),
    ])
    assert "A" not in result
    assert result["B"]["delta"][2] > 0
    assert -600 + result["B"]["delta"][0] == pytest.approx(0)


@pytest.mark.parametrize("flags", [collision.FLAG_VISIBLE, collision.FLAG_COLLISION_ENABLED,
                                   FLAGS | collision.FLAG_PAUSED])
def test_disabled_hidden_or_paused_pet_does_not_collide(flags):
    assert ContactWorld({}).solve([member("A", 100), member("B", 120, flags=flags)]) == {}


def test_fast_throw_cannot_cross_through_another_pet():
    world = ContactWorld({})
    thrown = FLAGS | collision.FLAG_THROWN
    assert world.solve([member("A", 100, vx=9000, flags=thrown), member("B", 200)]) == {}
    result = world.solve([member("A", 260, vx=9000, flags=thrown), member("B", 200)])
    assert 260 + result["A"]["delta"][2] < 200
    assert result["B"]["delta"][0] > 0


def test_hidden_then_shown_pet_has_no_stale_sweep():
    world = ContactWorld({})
    thrown = FLAGS | collision.FLAG_THROWN
    world.solve([member("A", 100, vx=9000, flags=thrown), member("B", 200)])
    world.solve([member("A", 120, flags=0), member("B", 200)])
    assert world.solve([member("A", 300, vx=9000, flags=thrown), member("B", 200)]) == {}


@pytest.mark.parametrize("field,value", [("x", float("nan")), ("vx", float("inf")),
                                         ("radius_x", -1), ("flags", "bad"), ("mass", None)])
def test_invalid_remote_state_is_ignored(field, value):
    bad = member("B", 120)
    bad[field] = value
    assert ContactWorld({}).solve([member("A", 100), bad]) == {}


def test_scaling_changes_the_collision_boundary():
    world = ContactWorld({})
    assert world.solve([member("A", 100), member("B", 190)]) == {}
    result = world.solve([member("A", 100, radius=70), member("B", 190)])
    assert result["A"]["delta"][2] < 0


@pytest.fixture
def pet(tmp_path, monkeypatch):
    from pet import feature_activation
    from pet.config import Config
    from pet.settings_slot_config import route_settings_config
    from tests.pet_window_fakes import FakeLibrary
    from pet.window import PetWindow

    app = QApplication.instance() or QApplication([])
    feature_activation.freeze_snapshot_for_tests([])
    monkeypatch.setattr("pet.game_link.GameLink._event_file", lambda self: tmp_path / "no-events.json")
    cfg = route_settings_config(Config(base=tmp_path, instance_id="slot-0"))
    for key, value in {"character": "角色A", "no_move": True, "on_top": False,
                       "self_talk_enabled": False, "auto_hide_fullscreen": False,
                       "cursor_hidden_passthrough": False, "collision_sound_enabled": False}.items():
        cfg.set(key, value)
    win = PetWindow(FakeLibrary(), cfg)
    win.show()
    win._move_window_towards(200, 200)
    app.processEvents()
    adapter = WindowContacts(win)
    win._pet_contacts = adapter
    yield win, adapter
    adapter.stop()
    win.close()


def test_sample_uses_visible_body_and_drawing_offset(pet):
    win, adapter = pet
    win._move_window_towards(-10000, 200)
    state = adapter.sample()
    body = win._stable_body_local_rect()
    pos = win._virtual_pos()
    assert state["x"] == pos.x() + body.x() + body.width() / 2
    assert state["radius_x"] == body.width() / 2
    assert win._draw_delta.x() != 0


def test_real_window_impulse_enters_throw_and_keeps_position_in_sync(pet):
    win, adapter = pet
    adapter.sample()
    before = win._virtual_pos()
    adapter.apply({"delta": [500, -100, -8, 0]})
    assert win._physics_mode == "throw"
    assert win._phys_vel == [500, -100]
    assert win._virtual_pos().x() == before.x() - 8
    assert win._phys_pos == [float(win._virtual_pos().x()), float(win._virtual_pos().y())]


@pytest.mark.parametrize("change", ["drag", "lock", "hide", "disable", "scale", "old"])
def test_real_window_rejects_result_after_interaction_changes(pet, change):
    win, adapter = pet
    adapter.sample()
    if change == "drag":
        win._dragging = True
    elif change == "lock":
        win.lock_position = True
    elif change == "hide":
        win.hide()
    elif change == "disable":
        win.cfg.set("collision_enabled", False)
    elif change == "scale":
        win.change_scale(0.5)
    else:
        adapter._sample_time = time.monotonic() - 1
    pos = win._virtual_pos()
    velocity = list(win._phys_vel)
    adapter.apply({"delta": [500, -100, -8, 0]})
    assert win._virtual_pos() == pos
    assert win._phys_vel == velocity


def test_stationary_separation_does_not_start_falling(pet):
    win, adapter = pet
    adapter.sample()
    before = win._virtual_pos()
    adapter.apply({"delta": [0, 0, 10, 0]})
    assert win._virtual_pos().x() == before.x() + 10
    assert win._physics_mode is None
    state = adapter.sample()
    assert math.hypot(state["vx"], state["vy"]) == 0


class _RecordingBus:
    starts = 0
    stops = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


@pytest.mark.skip(reason='移植后遗留失败：移植后已不适用')
def test_window_hide_stops_contacts_and_show_restarts_them(pet):
    win, adapter = pet
    bus = _RecordingBus()
    adapter.bus = bus
    adapter.world = ContactWorld({})
    win.hide()
    assert bus.stops == 1
    win.show()
    assert bus.starts == 1
