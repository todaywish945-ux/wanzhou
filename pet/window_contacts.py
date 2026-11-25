from dataclasses import replace
from itertools import combinations
import math
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from . import collision, physics


_FIXED = collision.FLAG_DRAGGING | collision.FLAG_LOCK_POSITION | collision.FLAG_SLINGSHOT_AIMING
_ACTIVE = collision.FLAG_VISIBLE | collision.FLAG_COLLISION_ENABLED


def _circles(state):
    return collision.circles_from_rect(
        state.x - state.radius_x, state.y - state.radius_y,
        state.radius_x * 2, state.radius_y * 2,
    )


def _read_member(raw):
    if not isinstance(raw, dict):
        return None
    identity = raw.get("runtime_id")
    flags = raw.get("flags")
    if not isinstance(identity, str) or not 0 < len(identity) <= 128 or type(flags) is not int:
        return None
    fields = ("x", "y", "radius_x", "radius_y", "vx", "vy", "mass", "scale")
    values = {}
    for name in fields:
        value = raw.get(name)
        if type(value) not in (int, float) or not math.isfinite(value):
            return None
        values[name] = float(value)
    if (abs(values["x"]) > 1e7 or abs(values["y"]) > 1e7
            or not 0 < values["radius_x"] <= 20000 or not 0 < values["radius_y"] <= 20000
            or abs(values["vx"]) > 20000 or abs(values["vy"]) > 20000
            or not 0 < values["mass"] <= 100 or not 0 < values["scale"] <= 10):
        return None
    if flags & _ACTIVE != _ACTIVE or flags & collision.FLAG_PAUSED:
        return None
    state = collision.MemberState(identity, flags=flags, is_infinite_mass=bool(flags & _FIXED), **values)
    state.circles = _circles(state)
    return state


class ContactWorld:
    def __init__(self, config):
        self.config = config
        self._previous = {}
        self._history = {}
        self._last_time = 0.0

    def reset(self):
        self._previous.clear()
        self._history.clear()
        self._last_time = 0.0

    def solve(self, snapshots):
        members = sorted(
            (state for raw in snapshots if (state := _read_member(raw)) is not None),
            key=lambda state: state.runtime_id,
        )
        now = time.monotonic()
        originals = {state.runtime_id: state for state in members}
        swept = {}
        first_contact = None
        if 0 < now - self._last_time < 0.12:
            for a, b in combinations(members, 2):
                old_a, old_b = self._previous.get(a.runtime_id), self._previous.get(b.runtime_id)
                if old_a is None or old_b is None:
                    continue
                if not (a.flags | b.flags) & collision.FLAG_THROWN:
                    continue
                if any((new.flags, new.radius_x, new.radius_y) != (old.flags, old.radius_x, old.radius_y)
                       for new, old in ((a, old_a), (b, old_b))):
                    continue
                hit = collision.swept_circle_chain_collision_at_t(old_a.circles, a.circles, old_b.circles, b.circles)
                if hit[0] and (first_contact is None or hit[1] < first_contact[0]):
                    first_contact = (hit[1], f"{a.runtime_id}|{b.runtime_id}", hit)
        if first_contact is not None:
            fraction, pair, hit = first_contact
            rewound = []
            for state in members:
                old = self._previous.get(state.runtime_id)
                if old is not None and not state.is_infinite_mass:
                    state = replace(state, x=old.x + (state.x - old.x) * fraction,
                                    y=old.y + (state.y - old.y) * fraction)
                    state.circles = _circles(state)
                rewound.append(state)
            members = rewound
            swept[pair] = (True, *hit[2:])
        _, combined, self._history = collision.solve_multi_body_collision(
            members, overlap_history=self._history, swept_collisions=swept,
            restitution=float(self.config.get("collision_restitution", 0.82)),
            friction=float(self.config.get("collision_friction", 0.08)),
            impulse_cap=float(self.config.get("collision_impulse_cap", 9000.0)),
        )
        result = {}
        self._previous = {}
        self._last_time = now
        for state in members:
            original = originals[state.runtime_id]
            dvx, dvy, dx, dy = combined.get(state.runtime_id, (0.0, 0.0, 0.0, 0.0))
            if not state.is_infinite_mass:
                dx += state.x - original.x
                dy += state.y - original.y
                if max(abs(dvx), abs(dvy), abs(dx), abs(dy)) > 1e-6:
                    result[state.runtime_id] = {"delta": [dvx, dvy, dx, dy]}
            corrected = replace(original, x=original.x + dx, y=original.y + dy,
                                vx=original.vx + dvx, vy=original.vy + dvy)
            if math.hypot(dvx, dvy) >= collision.IMPULSE_MIN_APPROACH_SPEED:
                corrected.flags |= collision.FLAG_THROWN
            corrected.circles = _circles(corrected)
            self._previous[state.runtime_id] = corrected
        return result


class WindowContacts(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.world = None  # start() 时才建（构造期不读配置，替身窗也能装配）
        self.bus = None
        self._motion = None
        self._sample = None
        self._sample_time = 0.0
        QApplication.instance().aboutToQuit.connect(self.stop)

    def start(self):
        from .contact_transport import ContactBus

        directory = self.window.cfg.dir
        try:
            directory.mkdir(parents=True, exist_ok=True)  # 全新安装首启也没有配置目录
        except OSError:
            return
        if self.world is None:
            self.world = ContactWorld(self.window.cfg)
        if self.bus is None:
            self.bus = ContactBus(directory, self.sample, self.world.solve, self.apply, self)
        self.bus.start()

    def stop(self):
        if self.bus is not None:
            self.bus.stop()
        if self.world is not None:
            self.world.reset()
        self._sample = None
        self._motion = None

    def _flags(self):
        win = self.window
        flags = 0
        if win.isVisible() and not win._hidden_paused and not getattr(win, "_closing", False):
            flags |= collision.FLAG_VISIBLE
        if win.cfg.get("collision_enabled", True):
            flags |= collision.FLAG_COLLISION_ENABLED
        if win._physics_mode == "throw":
            flags |= collision.FLAG_THROWN
        if win._dragging or win._physics_mode == "drag" or win._press_global is not None:
            flags |= collision.FLAG_DRAGGING
        if win.lock_position:
            flags |= collision.FLAG_LOCK_POSITION
        if win._interaction_state == "SLINGSHOT_AIMING":
            flags |= collision.FLAG_SLINGSHOT_AIMING
        if win._context_menu_open:
            flags |= collision.FLAG_PAUSED
        return flags

    def sample(self):
        win = self.window
        now = time.monotonic()
        pos, body = win._virtual_pos(), win._stable_body_local_rect()
        flags = self._flags()
        vx = vy = 0.0
        if win._physics_mode == "throw":
            vx, vy = win._phys_vel
        elif self._motion is not None and not win.lock_position:
            stamp, x, y, scale, old_flags = self._motion
            dt = now - stamp
            if 0.001 < dt < 0.12 and scale == win.scale and old_flags == flags:
                vx, vy = (pos.x() - x) / dt, (pos.y() - y) / dt
        speed = math.hypot(vx, vy)
        if speed > win._throw_speed_cap:
            vx, vy = vx * win._throw_speed_cap / speed, vy * win._throw_speed_cap / speed
        self._motion = (now, pos.x(), pos.y(), win.scale, flags)
        self._sample_time = now
        self._sample = dict(
            x=pos.x() + body.x() + body.width() / 2,
            y=pos.y() + body.y() + body.height() / 2,
            radius_x=body.width() / 2, radius_y=body.height() / 2,
            vx=vx, vy=vy, scale=win.scale, flags=flags,
            mass=collision.calculate_mass(body.width() / 2, body.height() / 2, scale=win.scale,
                                          collision_mass_scale=float(win.cfg.get("collision_mass_scale", 1.0))),
        )
        return dict(self._sample)

    def apply(self, change):
        delta = change.get("delta") if isinstance(change, dict) else None
        if not isinstance(delta, list) or len(delta) != 4:
            return
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in delta):
            return
        dvx, dvy, dx, dy = delta
        if max(abs(dvx), abs(dvy)) > 18000 or max(abs(dx), abs(dy)) > 4000:
            return
        win, sampled = self.window, self._sample
        flags = self._flags()
        if (sampled is None or time.monotonic() - self._sample_time > 0.12
                or flags != sampled["flags"] or win.scale != sampled["scale"]
                or flags & _ACTIVE != _ACTIVE or flags & (_FIXED | collision.FLAG_PAUSED)):
            return
        was_thrown = win._physics_mode == "throw"
        if was_thrown and sum(a * b for a, b in zip(win._phys_vel, (sampled["vx"], sampled["vy"]))) < 0:
            return
        pos = win._virtual_pos()
        body = win._stable_body_local_rect()
        travel = math.hypot(pos.x() + body.x() + body.width() / 2 - sampled["x"],
                            pos.y() + body.y() + body.height() / 2 - sampled["y"])
        if travel > 10 + win._throw_speed_cap * (time.monotonic() - self._sample_time):
            return
        win._cancel_move()
        win._move_window_towards(pos.x() + dx, pos.y() + dy)
        pos = win._virtual_pos()
        win._phys_pos[:] = [float(pos.x()), float(pos.y())]
        self._motion = (time.monotonic(), pos.x(), pos.y(), win.scale, flags)
        impulse = math.hypot(dvx, dvy)
        if was_thrown or impulse >= collision.IMPULSE_MIN_APPROACH_SPEED:
            vx, vy = win._phys_vel if was_thrown else (sampled["vx"], sampled["vy"])
            vx, vy = vx + dvx, vy + dvy
            speed = math.hypot(vx, vy)
            if speed > win._throw_speed_cap:
                factor = physics.soft_clamp_speed(speed, win._throw_speed_cap) / speed
                vx, vy = vx * factor, vy * factor
            win._phys_vel[:] = [vx, vy]
            if not was_thrown:
                win._enter_physics_mode("throw")
                win._interaction_state = "THROWN"
                win._last_physics_tick_time = None
                win._physics_timer.start()
                edge = getattr(win, "_edge_probe", None)
                if edge is not None:
                    edge.cancel("pet_hit", restore=False)
                win._reentry_after_throw_armed = True
                win._just_dragged = True
                QTimer.singleShot(120, win, win._clear_just_dragged)
            if impulse >= collision.IMPULSE_MIN_APPROACH_SPEED:
                win._play_collision_sound()
                egg = getattr(win, "_throw_egg", None)
                if egg is not None and egg.active:
                    egg.on_pet_contact(math.hypot(vx, vy))
