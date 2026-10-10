"""Execute placement deadlines and abort cleanup with deterministic sensors."""
from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace

import numpy as np
import pytest

from beamng_autopilot import fsd_drive as fd


class Clock:
    def __init__(self):
        self.value = 100.0
        self.wall_offset = 0.0

    def time(self):
        return self.value + self.wall_offset

    def monotonic(self):
        return self.value


class Connection:
    def __init__(self):
        self.commands = []
        self.closed = False
        self.fail_state = False
        self.state = SimpleNamespace(pos=np.array([0.0, 0.0, 0.0]), heading=0.0)

    def control(self, **controls):
        self.commands.append(controls)

    def get_state(self):
        if self.fail_state:
            raise RuntimeError("sensor connection lost")
        return self.state

    def step(self, steps):
        pass

    def open(self, **kwargs):
        pass

    def attach_vehicle(self, **kwargs):
        pass

    def current_env(self):
        return {"map": "fixture", "vehicle": "etk800"}

    def close(self):
        self.closed = True


class Stack:
    def __init__(self, clock, *, delay=0.0, centered=True):
        self.clock, self.delay = clock, delay
        self.calls = 0
        self.closed = False
        self.tick_result = SimpleNamespace(
            frame=np.zeros((2, 2, 3), np.uint8) if centered else None,
            meta={"object_head": 1})

    def tick(self, **kwargs):
        self.calls += 1
        self.clock.value += self.delay
        return self.tick_result

    def close(self):
        self.closed = True


@pytest.fixture()
def world(monkeypatch):
    clock, conn = Clock(), Connection()
    args = SimpleNamespace(strict=True, lane_mode="sensor")
    session = fd.FSDriveSession(args)
    monkeypatch.setattr(fd, "time", clock)
    monkeypatch.setattr(fd, "PLACEMENT_SKIP_TICKS", 1)
    monkeypatch.setattr(fd, "wd_heartbeat", lambda conn: True)
    monkeypatch.setattr(fd, "_sensor_lane_is_centered", lambda *args: True)
    route = np.array([[0.0, 0.0], [20.0, 0.0]])
    return clock, conn, session, route


def assert_held(conn):
    assert conn.commands
    assert all(c["throttle"] == 0.0 and c["brake"] == 1.0
               for c in conn.commands)


def test_expired_placement_never_starts_a_sensor_tick(world):
    clock, conn, session, route = world
    stack = Stack(clock)
    assert session._prewarm_and_place(
        conn, stack, route, 2, wall_hit=lambda: True) == (None, False, 3)
    assert stack.calls == 0
    assert_held(conn)


def test_tick_crossing_deadline_cannot_release_centered_car(world):
    clock, conn, session, route = world
    stack = Stack(clock, delay=2.0)
    out, placed, rc = session._prewarm_and_place(
        conn, stack, route, 2, wall_hit=lambda: clock.value >= 101.0)
    assert out is stack.tick_result
    assert (placed, rc, stack.calls) == (False, 3, 1)
    assert_held(conn)


def test_placement_exception_is_failure_even_in_collection_mode(world):
    clock, conn, session, route = world
    conn.fail_state = True
    session.args.allow_unplaced = True
    assert session._prewarm_and_place(
        conn, Stack(clock), route, 2) == (None, False, 2)
    assert_held(conn)


def test_centered_placement_without_cap_preserves_release(world):
    clock, conn, session, route = world
    stack = Stack(clock, delay=1000.0)
    out, placed, rc = session._prewarm_and_place(conn, stack, route, 2)
    assert out is stack.tick_result and placed and rc == 0
    assert conn.commands[-1]["brake"] == 0.0


def test_placement_deadline_precedes_allow_unplaced(world):
    clock, conn, session, route = world
    session.args.allow_unplaced = True
    assert session._prewarm_and_place(
        conn, Stack(clock), route, 2, wall_hit=lambda: True) == (None, False, 3)
    assert_held(conn)


def run_world(world, monkeypatch, *, cap, delay, output=None):
    clock, conn, session, route = world
    stack = Stack(clock, delay=delay, centered=False)
    session.args = SimpleNamespace(
        runtime="tech", attach=True, map=None, teleport=None,
        speed=6.0, strict=True, lane_mode="sensor", no_shadow=True,
        out=str(output) if output is not None else None, max_wall_s=cap)
    monkeypatch.setattr(fd, "BeamNGConnector", lambda *a, **k: conn)
    monkeypatch.setattr(fd.gearbox, "forward_gear_input", lambda conn: 2)
    monkeypatch.setattr(fd, "wd_arm", lambda conn: True)
    monkeypatch.setattr(fd, "wd_disarm", lambda conn: True)
    monkeypatch.setattr(session, "_build_route",
                        lambda conn: (route, route, None, None))
    monkeypatch.setattr(session, "_setup_runtime",
                        lambda conn, args: (None, stack, None, None, None))
    return session.run(), stack


def test_session_timeout_runs_brake_sensor_and_connection_cleanup(world, monkeypatch):
    clock, conn, _, _ = world
    rc, stack = run_world(world, monkeypatch, cap=1.0, delay=1.0)
    assert rc == 3 and stack.calls == 1
    assert stack.closed and conn.closed
    assert_held(conn)


def test_wall_clock_adjustment_does_not_extend_session_deadline(world, monkeypatch):
    clock, conn, _, _ = world
    clock.wall_offset = -10000.0
    rc, stack = run_world(world, monkeypatch, cap=1.0, delay=0.5)
    assert rc == 3 and stack.calls == 2
    assert stack.closed and conn.closed
    assert_held(conn)


def test_unplaceable_session_has_audit_even_without_telemetry(world, monkeypatch, tmp_path):
    output = tmp_path / "pose.json"
    rc, _stack = run_world(world, monkeypatch, cap=1.0, delay=1.0, output=output)
    record = json.loads(Path(str(output) + ".session.json").read_text(encoding="utf-8"))
    assert rc == record["exit_code"] == record["placement_rc"] == 3
    assert not record["placed"] and not record["drive_started"]
    assert record["telemetry_frames"] == 0
    assert record["actual_pose"]["pos"] == [0.0, 0.0, 0.0]
    assert not output.exists()


def test_cli_exposes_max_wall_s() -> None:
    cli = Path(__file__).resolve().parents[1] / "scripts" / "m5_fsd_drive.py"
    assert "--max-wall-s" in cli.read_text(encoding="utf-8")
