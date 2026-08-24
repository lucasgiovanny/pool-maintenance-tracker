"""Config and options flows for Pool Maintenance Tracker."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_CELL_DAYS,
    CONF_CHEMISTRY_DAYS,
    CONF_COVER_ENTITY,
    CONF_FILTER_DAYS,
    CONF_FILTER_PRESSURE_RISE,
    CONF_FILTER_PRESSURE_SOURCE,
    CONF_FILTRATION_OFF_TIME_ENTITY,
    CONF_FILTRATION_ON_TIME_ENTITY,
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_FILTRATION_SCHEDULE_MODE,
    CONF_FILTRATION_STATE_ENTITY,
    CONF_HEAT_PUMP_ENTITY,
    CONF_KIOSK_ENABLED,
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_MAINTENANCE_MODE,
    CONF_MODULES,
    CONF_NOTIFY_SERVICE,
    CONF_PEOPLE,
    CONF_POOL_LIGHT_ENTITY,
    CONF_POOL_SYSTEM_ENTITY,
    CONF_POOL_TYPE,
    CONF_POOL_VOLUME,
    CONF_PROBE_DAYS,
    CONF_PUMP_ENTITY,
    CONF_REMINDER_TIME,
    CONF_REPORT_ENABLED,
    CONF_REPORT_SENSORS,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
    CONF_TOKEN,
    DEFAULT_CELL_DAYS,
    DEFAULT_CHEMISTRY_DAYS,
    DEFAULT_FILTER_DAYS,
    DEFAULT_FILTER_PRESSURE_RISE,
    DEFAULT_KIOSK_ENABLED,
    DEFAULT_LANGUAGE,
    DEFAULT_MAINTENANCE_MODE,
    DEFAULT_PROBE_DAYS,
    DEFAULT_REMINDER_TIME,
    DEFAULT_REPORT_ENABLED,
    DEFAULT_SALT_TARGET_MAX,
    DEFAULT_SALT_TARGET_MIN,
    DOMAIN,
    EQUIPMENT_ROLES,
    LANGUAGES,
    LINKED_MODE_MANUAL,
    LINKED_MODES,
    LINKED_SOURCES,
    POOL_TYPE_SALT,
    POOL_TYPES,
    ROLE_FILTRATION_SCHEDULE,
    SCHEDULE_MODE_HELPER,
    SCHEDULE_MODE_NONE,
    SCHEDULE_MODES,
    SCHEDULE_STATE_DOMAINS,
    SCHEDULE_TIME_DOMAINS,
    SCHEDULE_TIME_KEYS,
    schedule_mode,
)
from .modules import (
    MODULE_FILTER,
    MODULE_PH_PROBE,
    MODULE_SALT_CHLORINATOR,
    MODULE_WATER_CHEMISTRY,
    OPTIONAL_MODULE_KEYS,
    POOL_TYPE_PRESETS,
)

CONF_REGENERATE_TOKEN = "regenerate_token"
NOTIFY_DOMAIN = "notify"

REMINDER_DAY_FIELDS: tuple[tuple[str, str, int], ...] = (
    # (module key, options key, default)
    (MODULE_FILTER.key, CONF_FILTER_DAYS, DEFAULT_FILTER_DAYS),
    (MODULE_PH_PROBE.key, CONF_PROBE_DAYS, DEFAULT_PROBE_DAYS),
    (MODULE_SALT_CHLORINATOR.key, CONF_CELL_DAYS, DEFAULT_CELL_DAYS),
    (MODULE_WATER_CHEMISTRY.key, CONF_CHEMISTRY_DAYS, DEFAULT_CHEMISTRY_DAYS),
)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _modules_selector(default: list[str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=list(OPTIONAL_MODULE_KEYS),
            multiple=True,
            mode=SelectSelectorMode.LIST,
            translation_key="modules",
        )
    )


def _language_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=LANGUAGES,
            mode=SelectSelectorMode.DROPDOWN,
            translation_key="language",
        )
    )


def _reminder_days_schema(modules: list[str], current: dict[str, Any]) -> dict[vol.Marker, Any]:
    schema: dict[vol.Marker, Any] = {}
    for module_key, conf_key, default in REMINDER_DAY_FIELDS:
        if module_key in modules:
            schema[vol.Required(conf_key, default=current.get(conf_key, default))] = NumberSelector(
                NumberSelectorConfig(min=1, max=365, step=1, mode=NumberSelectorMode.BOX)
            )
    return schema


def _validate_notify_service(value: str) -> str | None:
    """Normalize a notify target; return None when invalid."""
    service = value.strip()
    if not service:
        return ""
    if service.startswith("notify.") and len(service.split(".")) == 2:
        return service
    return None


def _notify_selector(hass: HomeAssistant, current: str) -> SelectSelector:
    """Every way this Home Assistant can send a message, in one dropdown.

    Notify comes in two shapes and both are current: the legacy services
    (`notify.mobile_app_*`, which is still how the companion app pushes to
    a phone) and the newer notify entities. An entity picker would quietly
    hide the first, which is the one most people actually want, so the list
    is built from both. A custom value stays possible for anything odd.
    """
    targets = {
        f"{NOTIFY_DOMAIN}.{service}"
        for service in hass.services.async_services_for_domain(NOTIFY_DOMAIN)
    }
    # send_message is the verb for notify entities, not a target itself
    targets.discard(f"{NOTIFY_DOMAIN}.send_message")
    targets.discard(f"{NOTIFY_DOMAIN}.persistent_notification")
    targets.update(state.entity_id for state in hass.states.async_all(NOTIFY_DOMAIN))
    if current:
        targets.add(current)
    return SelectSelector(
        SelectSelectorConfig(
            options=sorted(targets),
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=True,
            sort=True,
        )
    )


class PoolMaintenanceTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a new pool."""

    VERSION = 1

    def __init__(self) -> None:
        self._name: str = ""
        self._pool_type: str = POOL_TYPE_SALT
        self._modules: list[str] = []
        self._volume: float | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip() or "Pool"
            self._pool_type = user_input[CONF_POOL_TYPE]
            self._volume = user_input.get(CONF_POOL_VOLUME)
            return await self.async_step_modules()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Pool"): TextSelector(),
                    vol.Optional(CONF_POOL_VOLUME): NumberSelector(
                        NumberSelectorConfig(min=1, max=1000, step=1, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Required(CONF_POOL_TYPE, default=POOL_TYPE_SALT): SelectSelector(
                        SelectSelectorConfig(
                            options=POOL_TYPES,
                            mode=SelectSelectorMode.LIST,
                            translation_key="pool_type",
                        )
                    ),
                }
            ),
        )

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._modules = user_input[CONF_MODULES]
            return await self.async_step_settings()

        preset = list(POOL_TYPE_PRESETS[self._pool_type])
        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema(
                {vol.Required(CONF_MODULES, default=preset): _modules_selector(preset)}
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            notify_service = _validate_notify_service(user_input.get(CONF_NOTIFY_SERVICE, ""))
            if notify_service is None:
                errors[CONF_NOTIFY_SERVICE] = "invalid_notify_service"
            else:
                options: dict[str, Any] = {
                    CONF_POOL_TYPE: self._pool_type,
                    CONF_MODULES: self._modules,
                    CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    CONF_NOTIFY_SERVICE: notify_service,
                    CONF_REMINDER_TIME: DEFAULT_REMINDER_TIME,
                }
                if self._volume:
                    options[CONF_POOL_VOLUME] = float(self._volume)
                for _module_key, conf_key, _default in REMINDER_DAY_FIELDS:
                    if conf_key in user_input:
                        options[conf_key] = int(user_input[conf_key])
                return self.async_create_entry(
                    title=self._name,
                    data={CONF_NAME: self._name, CONF_TOKEN: _new_token()},
                    options=options,
                )

        ha_language = self.hass.config.language
        default_language = next(
            (
                candidate
                for candidate in (ha_language, ha_language.split("-")[0])
                if candidate in LANGUAGES
            ),
            DEFAULT_LANGUAGE,
        )
        schema: dict[vol.Marker, Any] = {
            vol.Required(CONF_LANGUAGE, default=default_language): _language_selector(),
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                description={"suggested_value": user_input.get(CONF_NOTIFY_SERVICE)}
                if user_input
                else None,
            ): _notify_selector(self.hass, ""),
        }
        schema.update(_reminder_days_schema(self._modules, {}))
        return self.async_show_form(
            step_id="settings", data_schema=vol.Schema(schema), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PoolOptionsFlow:
        return PoolOptionsFlow()


class PoolOptionsFlow(OptionsFlow):
    """Edit modules, reminders, page settings, or regenerate the token."""

    @callback
    def _store(self, options: dict[str, Any]) -> None:
        """Persist without leaving, for a step that hands over to another."""
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)

    async def _save(self, options: dict[str, Any]) -> ConfigFlowResult:
        """Store the options and go back to the menu.

        Home Assistant has no back button in options flows: finishing a step
        with async_create_entry closes the dialog, so changing two sections
        means reopening Configure. Persisting the options ourselves and
        returning the menu keeps the dialog open where the user left off.
        """
        self._store(options)
        return await self.async_step_init()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "pool",
                "modules",
                "people",
                "sensors",
                "equipment",
                "reminders",
                "page",
                "security",
            ],
        )

    async def async_step_pool(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Volume and the salt band the readings are judged against."""
        options = dict(self.config_entry.options)
        if user_input is not None:
            if user_input.get(CONF_POOL_VOLUME):
                options[CONF_POOL_VOLUME] = float(user_input[CONF_POOL_VOLUME])
            else:
                options.pop(CONF_POOL_VOLUME, None)
            options[CONF_SALT_TARGET_MIN] = float(user_input[CONF_SALT_TARGET_MIN])
            options[CONF_SALT_TARGET_MAX] = float(user_input[CONF_SALT_TARGET_MAX])
            options[CONF_MAINTENANCE_MODE] = user_input[CONF_MAINTENANCE_MODE]
            return await self._save(options)

        salt_selector = NumberSelector(
            NumberSelectorConfig(min=0, max=10, step=0.1, mode=NumberSelectorMode.BOX)
        )
        return self.async_show_form(
            step_id="pool",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POOL_VOLUME,
                        description={"suggested_value": options.get(CONF_POOL_VOLUME)},
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=1000, step=1, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Required(
                        CONF_SALT_TARGET_MIN,
                        default=options.get(CONF_SALT_TARGET_MIN, DEFAULT_SALT_TARGET_MIN),
                    ): salt_selector,
                    vol.Required(
                        CONF_SALT_TARGET_MAX,
                        default=options.get(CONF_SALT_TARGET_MAX, DEFAULT_SALT_TARGET_MAX),
                    ): salt_selector,
                    vol.Required(
                        CONF_MAINTENANCE_MODE,
                        default=options.get(CONF_MAINTENANCE_MODE, DEFAULT_MAINTENANCE_MODE),
                    ): BooleanSelector(),
                }
            ),
        )

    async def async_step_equipment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point the dashboards at the entities that play a known role.

        The filtration schedule is the one role that is not simply an entity
        to pick: a pool holds it in a Home Assistant schedule helper, or in
        the on/off times its own controller publishes. So this step asks
        which of the two it is and the next one collects it.
        """
        options = dict(self.config_entry.options)
        if user_input is not None:
            for role, conf_key in EQUIPMENT_ROLES.items():
                if role == ROLE_FILTRATION_SCHEDULE:
                    continue
                if user_input.get(conf_key):
                    options[conf_key] = user_input[conf_key]
                else:
                    options.pop(conf_key, None)
            mode = user_input.get(CONF_FILTRATION_SCHEDULE_MODE, SCHEDULE_MODE_NONE)
            options[CONF_FILTRATION_SCHEDULE_MODE] = mode
            if mode == SCHEDULE_MODE_NONE:
                for conf_key in (CONF_FILTRATION_SCHEDULE_ENTITY, *SCHEDULE_TIME_KEYS):
                    options.pop(conf_key, None)
                return await self._save(options)
            # Kept before handing over, so closing the dialog on the next
            # step does not undo what was chosen on this one.
            self._store(options)
            if mode == SCHEDULE_MODE_HELPER:
                return await self.async_step_schedule_helper()
            return await self.async_step_schedule_times()

        domains = {
            CONF_POOL_SYSTEM_ENTITY: ["switch", "input_boolean", "binary_sensor"],
            CONF_HEAT_PUMP_ENTITY: [
                "switch",
                "climate",
                "water_heater",
                "input_boolean",
                "binary_sensor",
            ],
            CONF_PUMP_ENTITY: ["switch", "input_boolean", "binary_sensor", "fan"],
            CONF_POOL_LIGHT_ENTITY: ["light", "switch"],
            CONF_COVER_ENTITY: ["cover", "switch", "binary_sensor", "input_boolean"],
        }
        schema: dict[vol.Marker, Any] = {}
        for role, conf_key in EQUIPMENT_ROLES.items():
            if role == ROLE_FILTRATION_SCHEDULE:
                schema[
                    vol.Required(
                        CONF_FILTRATION_SCHEDULE_MODE,
                        default=schedule_mode(options),
                    )
                ] = SelectSelector(
                    SelectSelectorConfig(
                        options=SCHEDULE_MODES,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="filtration_schedule_mode",
                    )
                )
                continue
            schema[
                vol.Optional(conf_key, description={"suggested_value": options.get(conf_key)})
            ] = EntitySelector(EntitySelectorConfig(domain=domains[conf_key]))
        return self.async_show_form(step_id="equipment", data_schema=vol.Schema(schema))

    async def async_step_schedule_helper(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The filtration schedule as a Home Assistant schedule helper."""
        options = dict(self.config_entry.options)
        if user_input is not None:
            options[CONF_FILTRATION_SCHEDULE_ENTITY] = user_input[CONF_FILTRATION_SCHEDULE_ENTITY]
            for conf_key in SCHEDULE_TIME_KEYS:
                options.pop(conf_key, None)
            return await self._save(options)

        return self.async_show_form(
            step_id="schedule_helper",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FILTRATION_SCHEDULE_ENTITY,
                        description={
                            "suggested_value": options.get(CONF_FILTRATION_SCHEDULE_ENTITY)
                        },
                    ): EntitySelector(EntitySelectorConfig(domain="schedule")),
                }
            ),
        )

    async def async_step_schedule_times(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The filtration schedule as the controller's own entities.

        The two times are the schedule; the third entity is the answer to
        "is it running now?". That one is optional — with the hours known,
        a clock answers it too — but a controller that has it is more
        truthful than the grid, which cannot know about a manual override.
        """
        options = dict(self.config_entry.options)
        if user_input is not None:
            options[CONF_FILTRATION_ON_TIME_ENTITY] = user_input[CONF_FILTRATION_ON_TIME_ENTITY]
            options[CONF_FILTRATION_OFF_TIME_ENTITY] = user_input[CONF_FILTRATION_OFF_TIME_ENTITY]
            if user_input.get(CONF_FILTRATION_STATE_ENTITY):
                options[CONF_FILTRATION_STATE_ENTITY] = user_input[CONF_FILTRATION_STATE_ENTITY]
            else:
                options.pop(CONF_FILTRATION_STATE_ENTITY, None)
            options.pop(CONF_FILTRATION_SCHEDULE_ENTITY, None)
            return await self._save(options)

        time_selector = EntitySelector(EntitySelectorConfig(domain=list(SCHEDULE_TIME_DOMAINS)))
        return self.async_show_form(
            step_id="schedule_times",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FILTRATION_ON_TIME_ENTITY,
                        description={
                            "suggested_value": options.get(CONF_FILTRATION_ON_TIME_ENTITY)
                        },
                    ): time_selector,
                    vol.Required(
                        CONF_FILTRATION_OFF_TIME_ENTITY,
                        description={
                            "suggested_value": options.get(CONF_FILTRATION_OFF_TIME_ENTITY)
                        },
                    ): time_selector,
                    vol.Optional(
                        CONF_FILTRATION_STATE_ENTITY,
                        description={"suggested_value": options.get(CONF_FILTRATION_STATE_ENTITY)},
                    ): EntitySelector(EntitySelectorConfig(domain=list(SCHEDULE_STATE_DOMAINS))),
                }
            ),
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Link external sensors (e.g. a smart probe) to the pool."""
        options = dict(self.config_entry.options)
        if user_input is not None:
            for conf_key in (*LINKED_SOURCES.values(), CONF_FILTER_PRESSURE_SOURCE):
                if user_input.get(conf_key):
                    options[conf_key] = user_input[conf_key]
                else:
                    options.pop(conf_key, None)
            options[CONF_LINKED_MODE] = user_input[CONF_LINKED_MODE]
            if user_input.get(CONF_REPORT_SENSORS):
                options[CONF_REPORT_SENSORS] = user_input[CONF_REPORT_SENSORS]
            else:
                options.pop(CONF_REPORT_SENSORS, None)
            return await self._save(options)

        schema: dict[vol.Marker, Any] = {}
        for conf_key in LINKED_SOURCES.values():
            schema[
                vol.Optional(
                    conf_key,
                    description={"suggested_value": options.get(conf_key)},
                )
            ] = EntitySelector(EntitySelectorConfig(domain="sensor"))
        schema[
            vol.Optional(
                CONF_FILTER_PRESSURE_SOURCE,
                description={"suggested_value": options.get(CONF_FILTER_PRESSURE_SOURCE)},
            )
        ] = EntitySelector(EntitySelectorConfig(domain="sensor"))
        schema[
            vol.Optional(
                CONF_REPORT_SENSORS,
                description={"suggested_value": options.get(CONF_REPORT_SENSORS)},
            )
        ] = EntitySelector(EntitySelectorConfig(multiple=True))
        schema[
            vol.Required(
                CONF_LINKED_MODE,
                default=options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=LINKED_MODES,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="linked_mode",
            )
        )
        return self.async_show_form(step_id="sensors", data_schema=vol.Schema(schema))

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = dict(self.config_entry.options)
        if user_input is not None:
            options[CONF_MODULES] = user_input[CONF_MODULES]
            return await self._save(options)

        current = list(options.get(CONF_MODULES, ()))
        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema(
                {vol.Required(CONF_MODULES, default=current): _modules_selector(current)}
            ),
        )

    async def async_step_people(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = dict(self.config_entry.options)
        if user_input is not None:
            options[CONF_PEOPLE] = user_input[CONF_PEOPLE]
            return await self._save(options)

        user_options = [
            SelectOptionDict(value=user.id, label=user.name or user.id)
            for user in await self.hass.auth.async_get_users()
            if user.is_active and not user.system_generated and user.name
        ]
        known_ids = [option["value"] for option in user_options]
        current = [
            user_id for user_id in options.get(CONF_PEOPLE, ()) if user_id in known_ids
        ] or known_ids
        return self.async_show_form(
            step_id="people",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PEOPLE, default=current): SelectSelector(
                        SelectSelectorConfig(
                            options=user_options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_reminders(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = dict(self.config_entry.options)
        if user_input is not None:
            for _module_key, conf_key, _default in REMINDER_DAY_FIELDS:
                if conf_key in user_input:
                    options[conf_key] = int(user_input[conf_key])
            options[CONF_REMINDER_TIME] = user_input[CONF_REMINDER_TIME]
            if CONF_FILTER_PRESSURE_RISE in user_input:
                options[CONF_FILTER_PRESSURE_RISE] = int(user_input[CONF_FILTER_PRESSURE_RISE])
            return await self._save(options)

        modules = list(options.get(CONF_MODULES, ()))
        schema: dict[vol.Marker, Any] = {}
        schema.update(_reminder_days_schema(modules, options))
        if options.get(CONF_FILTER_PRESSURE_SOURCE):
            schema[
                vol.Required(
                    CONF_FILTER_PRESSURE_RISE,
                    default=options.get(CONF_FILTER_PRESSURE_RISE, DEFAULT_FILTER_PRESSURE_RISE),
                )
            ] = NumberSelector(
                NumberSelectorConfig(min=5, max=100, step=5, mode=NumberSelectorMode.SLIDER)
            )
        schema[
            vol.Required(
                CONF_REMINDER_TIME,
                default=options.get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME),
            )
        ] = TextSelector()
        return self.async_show_form(step_id="reminders", data_schema=vol.Schema(schema))

    async def async_step_page(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = dict(self.config_entry.options)
        errors: dict[str, str] = {}
        if user_input is not None:
            notify_service = _validate_notify_service(user_input.get(CONF_NOTIFY_SERVICE, ""))
            if notify_service is None:
                errors[CONF_NOTIFY_SERVICE] = "invalid_notify_service"
            else:
                options[CONF_LANGUAGE] = user_input[CONF_LANGUAGE]
                options[CONF_NOTIFY_SERVICE] = notify_service
                options[CONF_REPORT_ENABLED] = user_input[CONF_REPORT_ENABLED]
                options[CONF_KIOSK_ENABLED] = user_input[CONF_KIOSK_ENABLED]
                return await self._save(options)

        return self.async_show_form(
            step_id="page",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LANGUAGE,
                        default=options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
                    ): _language_selector(),
                    vol.Optional(
                        CONF_NOTIFY_SERVICE,
                        description={"suggested_value": options.get(CONF_NOTIFY_SERVICE)},
                    ): _notify_selector(self.hass, options.get(CONF_NOTIFY_SERVICE, "")),
                    vol.Required(
                        CONF_REPORT_ENABLED,
                        default=options.get(CONF_REPORT_ENABLED, DEFAULT_REPORT_ENABLED),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_KIOSK_ENABLED,
                        default=options.get(CONF_KIOSK_ENABLED, DEFAULT_KIOSK_ENABLED),
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_security(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_REGENERATE_TOKEN):
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_TOKEN: _new_token()},
                )
            return await self._save(dict(self.config_entry.options))

        return self.async_show_form(
            step_id="security",
            data_schema=vol.Schema(
                {vol.Required(CONF_REGENERATE_TOKEN, default=False): BooleanSelector()}
            ),
        )
