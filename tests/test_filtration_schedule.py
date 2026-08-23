"""A filtration schedule kept as three entities instead of a helper.

A pool controller that already owns the cycle publishes it as plain
entities: the hour it starts, the hour it stops, and something reporting
whether it is running. These tests hold the promise that such a pool gets
exactly what a schedule helper gets — the weekly grid, today's hours, and
the countdown to the next change.
"""

import json
import re

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    CONF_FILTRATION_OFF_TIME_ENTITY,
    CONF_FILTRATION_ON_TIME_ENTITY,
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_FILTRATION_SCHEDULE_MODE,
    CONF_FILTRATION_STATE_ENTITY,
    SCHEDULE_MODE_HELPER,
    SCHEDULE_MODE_NONE,
    SCHEDULE_MODE_TIMES,
    URL_PAGE,
)

from .conftest import TEST_TOKEN, setup_entry

PAGE_URL = URL_PAGE.format(token=TEST_TOKEN)

TIME_OPTIONS = {
    CONF_FILTRATION_SCHEDULE_MODE: SCHEDULE_MODE_TIMES,
    CONF_FILTRATION_ON_TIME_ENTITY: "time.filtration_start",
    CONF_FILTRATION_OFF_TIME_ENTITY: "time.filtration_stop",
    CONF_FILTRATION_STATE_ENTITY: "binary_sensor.filtration_running",
}


def extract_config(html: str) -> dict:
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    assert match, "injected config not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


async def setup_with_options(hass, entry, **options) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={**entry.options, **options})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def set_times(hass, start="08:00:00", stop="20:00:00", running="on") -> None:
    hass.states.async_set("time.filtration_start", start)
    hass.states.async_set("time.filtration_stop", stop)
    if running is not None:
        hass.states.async_set(
            "binary_sensor.filtration_running", running, {"friendly_name": "Filtração"}
        )


async def report_of(hass, client) -> dict:
    return extract_config(await (await client.get(PAGE_URL)).text())["report"]


async def test_two_times_build_the_weekly_grid(hass, salt_entry, hass_client_no_auth, freezer):
    """Every day of the week runs the same block, as a helper would say it."""
    freezer.move_to("2026-07-27 16:00:00+00:00")  # 09:00 on a Monday
    set_times(hass)
    await setup_with_options(hass, salt_entry, **TIME_OPTIONS)
    client = await hass_client_no_auth()

    item = (await report_of(hass, client))["roles"]["filtration_schedule"]
    assert item["week"] == [[["08:00", "20:00"]]] * 7
    assert item["domain"] == "schedule"
    assert item["on"] is True
    # The stop time of the day we are standing in
    assert item["next_change"].startswith("2026-07-27T20:00:00")


async def test_the_hours_reach_todays_filtration(hass, salt_entry, hass_client_no_auth, freezer):
    """Today's hours are read off the two times, helper or not."""
    freezer.move_to("2026-07-27 16:00:00+00:00")  # 09:00 on a Monday
    set_times(hass, "09:30:00", "16:00:00")
    await setup_with_options(hass, salt_entry, **TIME_OPTIONS)
    client = await hass_client_no_auth()

    assert (await report_of(hass, client))["filtration"]["scheduled_hours"] == 6.5


async def test_a_cycle_through_midnight_is_one_run(hass, salt_entry, hass_client_no_auth, freezer):
    """Stopping before it starts means the night, not a zero-length day."""
    freezer.move_to("2026-07-28 06:00:00+00:00")  # 23:00 on a Monday
    set_times(hass, "22:00:00", "06:00:00")
    await setup_with_options(hass, salt_entry, **TIME_OPTIONS)
    client = await hass_client_no_auth()

    item = (await report_of(hass, client))["roles"]["filtration_schedule"]
    assert item["week"] == [[["00:00", "06:00"], ["22:00", "24:00"]]] * 7
    # Eight hours a night, split over two calendar days
    assert (await report_of(hass, client))["filtration"]["scheduled_hours"] == 8.0
    # Midnight is not a change: the blocks touch, so the run ends at 06:00
    assert item["next_change"].startswith("2026-07-28T06:00:00")


async def test_the_sensor_is_what_says_it_is_running(
    hass, salt_entry, hass_client_no_auth, freezer
):
    """A manual override is something only the controller can know about."""
    freezer.move_to("2026-07-27 16:00:00+00:00")  # 09:00, inside the block
    set_times(hass, running="off")
    await setup_with_options(hass, salt_entry, **TIME_OPTIONS)
    client = await hass_client_no_auth()

    item = (await report_of(hass, client))["roles"]["filtration_schedule"]
    assert item["on"] is False
    assert item["state"] == "off"
    assert item["entity_id"] == "binary_sensor.filtration_running"
    # Nothing here knows when a hand-made override ends, so nothing counts
    # down to it — the weekly grid still shows what the cycle would be.
    assert item["next_change"] is None
    assert item["week"] == [[["08:00", "20:00"]]] * 7
    # Every entity behind the schedule, so the card redraws when one moves
    assert item["sources"] == [
        "time.filtration_start",
        "time.filtration_stop",
        "binary_sensor.filtration_running",
    ]


async def test_without_a_sensor_the_clock_answers(hass, salt_entry, hass_client_no_auth, freezer):
    """Two times and a clock are enough to know whether it should be running."""
    freezer.move_to("2026-07-27 16:00:00+00:00")  # 09:00 on a Monday
    set_times(hass, running=None)
    options = {
        key: value for key, value in TIME_OPTIONS.items() if key != CONF_FILTRATION_STATE_ENTITY
    }
    await setup_with_options(hass, salt_entry, **options)
    client = await hass_client_no_auth()

    item = (await report_of(hass, client))["roles"]["filtration_schedule"]
    assert item["on"] is True
    assert item["entity_id"] == "time.filtration_start"

    hass.states.async_set("time.filtration_stop", "08:30:00")
    await hass.async_block_till_done()
    assert (await report_of(hass, client))["roles"]["filtration_schedule"]["on"] is False


async def test_an_input_datetime_holds_a_time_too(hass, salt_entry, hass_client_no_auth, freezer):
    """The parts an input_datetime spells out beat parsing its state."""
    freezer.move_to("2026-07-27 16:00:00+00:00")  # 09:00 on a Monday
    hass.states.async_set(
        "input_datetime.filtration_start",
        "2026-07-27 07:30:00",
        {"hour": 7, "minute": 30, "second": 0, "has_date": True, "has_time": True},
    )
    hass.states.async_set(
        "input_datetime.filtration_stop",
        "2026-07-27 18:45:00",
        {"hour": 18, "minute": 45, "second": 0, "has_date": True, "has_time": True},
    )
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_FILTRATION_SCHEDULE_MODE: SCHEDULE_MODE_TIMES,
            CONF_FILTRATION_ON_TIME_ENTITY: "input_datetime.filtration_start",
            CONF_FILTRATION_OFF_TIME_ENTITY: "input_datetime.filtration_stop",
        },
    )
    client = await hass_client_no_auth()

    item = (await report_of(hass, client))["roles"]["filtration_schedule"]
    assert item["week"][0] == [["07:30", "18:45"]]


async def test_times_that_say_nothing_leave_the_role_out(hass, salt_entry, hass_client_no_auth):
    """An unavailable controller is not a schedule of zero hours."""
    hass.states.async_set("time.filtration_start", "unavailable")
    hass.states.async_set("time.filtration_stop", "20:00:00")
    await setup_with_options(hass, salt_entry, **TIME_OPTIONS)
    client = await hass_client_no_auth()

    report = await report_of(hass, client)
    assert "filtration_schedule" not in report["roles"]
    # Nothing scheduled and no pump to have run: no hours block at all
    assert report["filtration"] is None


async def test_a_helper_pool_is_untouched(hass, salt_entry, hass_client_no_auth, hass_storage):
    """The schedule helper stays exactly what it was, mode or no mode."""
    hass_storage["schedule"] = {
        "version": 1,
        "minor_version": 1,
        "key": "schedule",
        "data": {
            "items": [
                {
                    "id": "abc123",
                    "name": "Filtração",
                    "monday": [{"from": "08:00:00", "to": "12:00:00"}],
                }
            ]
        },
    }
    registry = er.async_get(hass)
    reg_entry = registry.async_get_or_create(
        "schedule", "schedule", "abc123", suggested_object_id="filtracao"
    )
    hass.states.async_set(reg_entry.entity_id, "on", {"friendly_name": "Filtração"})
    # No mode stored at all: the entity a pool already picked is the answer
    await setup_with_options(
        hass, salt_entry, **{CONF_FILTRATION_SCHEDULE_ENTITY: reg_entry.entity_id}
    )
    client = await hass_client_no_auth()

    item = (await report_of(hass, client))["roles"]["filtration_schedule"]
    assert item["entity_id"] == reg_entry.entity_id
    assert item["week"][0] == [["08:00", "12:00"]]


async def test_options_flow_switches_to_times(hass, salt_entry):
    """Picking the type leads to the form that collects it."""
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, CONF_FILTRATION_SCHEDULE_ENTITY: "schedule.filtracao"},
    )
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "equipment"}
    )
    assert result["step_id"] == "equipment"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FILTRATION_SCHEDULE_MODE: SCHEDULE_MODE_TIMES}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "schedule_times"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FILTRATION_ON_TIME_ENTITY: "time.filtration_start",
            CONF_FILTRATION_OFF_TIME_ENTITY: "time.filtration_stop",
        },
    )
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()

    assert salt_entry.options[CONF_FILTRATION_ON_TIME_ENTITY] == "time.filtration_start"
    # One schedule per pool: choosing a type drops what the other one held
    assert CONF_FILTRATION_SCHEDULE_ENTITY not in salt_entry.options


async def test_options_flow_switches_back_to_a_helper(hass, salt_entry):
    """And back, dropping the entities the other type used."""
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, **TIME_OPTIONS}
    )
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "equipment"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FILTRATION_SCHEDULE_MODE: SCHEDULE_MODE_HELPER}
    )
    assert result["step_id"] == "schedule_helper"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FILTRATION_SCHEDULE_ENTITY: "schedule.filtracao"}
    )
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()

    assert salt_entry.options[CONF_FILTRATION_SCHEDULE_ENTITY] == "schedule.filtracao"
    assert CONF_FILTRATION_ON_TIME_ENTITY not in salt_entry.options
    assert CONF_FILTRATION_STATE_ENTITY not in salt_entry.options


async def test_options_flow_can_have_no_schedule_at_all(hass, salt_entry):
    """A pool without one keeps the rest of the equipment step working."""
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, **TIME_OPTIONS}
    )
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "equipment"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FILTRATION_SCHEDULE_MODE: SCHEDULE_MODE_NONE,
            "pump_entity": "switch.pump",
        },
    )
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()

    assert salt_entry.options["pump_entity"] == "switch.pump"
    for conf_key in (CONF_FILTRATION_ON_TIME_ENTITY, CONF_FILTRATION_SCHEDULE_ENTITY):
        assert conf_key not in salt_entry.options
