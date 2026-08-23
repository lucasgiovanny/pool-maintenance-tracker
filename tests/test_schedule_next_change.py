"""The real next flip of a schedule, across midnight."""

from datetime import datetime

from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.report import (
    _schedule_next_change,
    _today_scheduled_hours,
)

# Monday 22:00-24:00 rolling into Tuesday 00:00-01:00 — one run, not two
WEEK = [
    [["22:00", "24:00"]],  # Monday
    [["00:00", "01:00"], ["09:00", "12:00"]],  # Tuesday
    [],
    [],
    [],
    [],
    [],
]


def local(text: str) -> datetime:
    return dt_util.as_utc(datetime.fromisoformat(text).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE))


def test_touching_blocks_are_one_run():
    """At Monday 23:00 the schedule is on until Tuesday 01:00 — midnight is
    a block edge, not a state change."""
    change = _schedule_next_change(WEEK, local("2026-07-27 23:00"))  # a Monday
    assert dt_util.as_local(change).isoformat()[:16] == "2026-07-28T01:00"


def test_a_gap_is_a_real_off():
    change = _schedule_next_change(WEEK, local("2026-07-28 00:30"))
    assert dt_util.as_local(change).isoformat()[:16] == "2026-07-28T01:00"
    change = _schedule_next_change(WEEK, local("2026-07-28 01:30"))
    assert dt_util.as_local(change).isoformat()[:16] == "2026-07-28T09:00"


def test_off_now_means_next_start():
    change = _schedule_next_change(WEEK, local("2026-07-27 20:00"))
    assert dt_util.as_local(change).isoformat()[:16] == "2026-07-27T22:00"


def test_wraps_to_next_week():
    change = _schedule_next_change(WEEK, local("2026-07-29 12:00"))  # Wednesday
    assert dt_util.as_local(change).isoformat()[:16] == "2026-08-03T22:00"


def test_empty_week_has_no_change():
    assert _schedule_next_change([[], [], [], [], [], [], []], dt_util.utcnow()) is None


def test_midnight_end_counts_as_hours(freezer):
    """A block stored as 22:00 -> 00:00 is two hours, not minus twenty-two."""
    freezer.move_to("2026-07-27 12:00:00+00:00")  # Monday
    assert _today_scheduled_hours(WEEK) == 2.0


async def test_storage_block_to_midnight_normalizes(
    hass, salt_entry, hass_client_no_auth, hass_storage
):
    """The UI stores a run-to-midnight block with to: 00:00:00."""
    import json
    import re

    from homeassistant.helpers import entity_registry as er

    from custom_components.pool_maintenance_tracker.const import URL_PAGE
    from tests.conftest import TEST_TOKEN

    hass_storage["schedule"] = {
        "version": 1,
        "minor_version": 1,
        "key": "schedule",
        "data": {
            "items": [
                {
                    "id": "abc123",
                    "name": "Filtração",
                    "monday": [{"from": "22:00:00", "to": "00:00:00"}],
                    "tuesday": [{"from": "00:00:00", "to": "01:00:00"}],
                }
            ]
        },
    }
    registry = er.async_get(hass)
    sched = registry.async_get_or_create(
        "schedule", "schedule", "abc123", suggested_object_id="filtracao"
    )
    hass.states.async_set(sched.entity_id, "on", {"friendly_name": "Filtração"})
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "filtration_schedule_entity": sched.entity_id},
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.get(URL_PAGE.format(token=TEST_TOKEN))
    match = re.search(r"const CFG = (\{.*?\});\n", await response.text(), re.DOTALL)
    config = json.loads(match.group(1).replace("<\\/", "</"))
    week = config["report"]["roles"]["filtration_schedule"]["week"]
    assert week[0] == [["22:00", "24:00"]]
