from embedded.state_manager import StateManager


def test_state_manager_updates_json_sections_and_snapshots():
    manager = StateManager(ui_queue_size=2)

    snapshot = manager.update("NAV", "route", {
        "session_id": "ride_1",
        "instruction": "Turn left",
        "verified_position": [19.076, 72.877],
    })

    assert snapshot["route"]["session_id"] == "ride_1"
    assert snapshot["route"]["instruction"] == "Turn left"
    assert snapshot["route"]["verified_position"] == [19.076, 72.877]
    assert snapshot["version"] == 1


def test_state_manager_ui_queue_keeps_latest_without_blocking():
    manager = StateManager(ui_queue_size=1)
    first = manager.update("NAV", "route", {"instruction": "First"})
    second = manager.update("NAV", "route", {"instruction": "Second"})

    assert manager.queue_ui_snapshot("test", first)
    assert manager.queue_ui_snapshot("test", second)

    queued = manager.get_ui_snapshot_nowait()
    assert queued["route"]["instruction"] == "Second"
    assert manager.get_ui_snapshot_nowait() is None
