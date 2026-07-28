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
from homeassistant.core import callback
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
    CONF_COVER_ENTITY,
    CONF_FILTER_DAYS,
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_HEAT_PUMP_ENTITY,
    CONF_KIOSK_ENABLED,
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_MODULES,
    CONF_NOTIFY_SERVICE,
    CONF_PEOPLE,
    CONF_POOL_LIGHT_ENTITY,
    CONF_POOL_SYSTEM_ENTITY,
    CONF_POOL_TYPE,
    CONF_PROBE_DAYS,
    CONF_PUMP_ENTITY,
    CONF_REMINDER_TIME,
    CONF_REPORT_ENABLED,
    CONF_REPORT_SENSORS,
    CONF_TOKEN,
    DEFAULT_CELL_DAYS,
    DEFAULT_FILTER_DAYS,
    DEFAULT_KIOSK_ENABLED,
    DEFAULT_LANGUAGE,
    DEFAULT_PROBE_DAYS,
    DEFAULT_REMINDER_TIME,
    DEFAULT_REPORT_ENABLED,
    DOMAIN,
    EQUIPMENT_ROLES,
    LANGUAGES,
    LINKED_MODE_MANUAL,
    LINKED_MODES,
    LINKED_SOURCES,
    POOL_TYPE_SALT,
    POOL_TYPES,
)
from .modules import (
    MODULE_FILTER,
    MODULE_PH_PROBE,
    MODULE_SALT_CHLORINATOR,
    OPTIONAL_MODULE_KEYS,
    POOL_TYPE_PRESETS,
)

CONF_REGENERATE_TOKEN = "regenerate_token"

REMINDER_DAY_FIELDS: tuple[tuple[str, str, int], ...] = (
    # (module key, options key, default)
    (MODULE_FILTER.key, CONF_FILTER_DAYS, DEFAULT_FILTER_DAYS),
    (MODULE_PH_PROBE.key, CONF_PROBE_DAYS, DEFAULT_PROBE_DAYS),
    (MODULE_SALT_CHLORINATOR.key, CONF_CELL_DAYS, DEFAULT_CELL_DAYS),
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
    """Normalize a notify service; return None when invalid."""
    service = value.strip()
    if not service:
        return ""
    if service.startswith("notify.") and len(service.split(".")) == 2:
        return service
    return None


class PoolMaintenanceTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a new pool."""

    VERSION = 1

    def __init__(self) -> None:
        self._name: str = ""
        self._pool_type: str = POOL_TYPE_SALT
        self._modules: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip() or "Pool"
            self._pool_type = user_input[CONF_POOL_TYPE]
            return await self.async_step_modules()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Pool"): TextSelector(),
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
                for _module_key, conf_key, _default in REMINDER_DAY_FIELDS:
                    if conf_key in user_input:
                        options[conf_key] = int(user_input[conf_key])
                return self.async_create_entry(
                    title=self._name,
                    data={CONF_NAME: self._name, CONF_TOKEN: _new_token()},
                    options=options,
                )

        default_language = (
            self.hass.config.language.split("-")[0]
            if self.hass.config.language.split("-")[0] in LANGUAGES
            else DEFAULT_LANGUAGE
        )
        schema: dict[vol.Marker, Any] = {
            vol.Required(CONF_LANGUAGE, default=default_language): _language_selector(),
            vol.Optional(CONF_NOTIFY_SERVICE, default=""): TextSelector(),
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

    async def _save(self, options: dict[str, Any]) -> ConfigFlowResult:
        """Store the options and go back to the menu.

        Home Assistant has no back button in options flows: finishing a step
        with async_create_entry closes the dialog, so changing two sections
        means reopening Configure. Persisting the options ourselves and
        returning the menu keeps the dialog open where the user left off.
        """
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)
        return await self.async_step_init()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "modules",
                "people",
                "sensors",
                "equipment",
                "reminders",
                "page",
                "security",
            ],
        )

    async def async_step_equipment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point the dashboards at the entities that play a known role."""
        options = dict(self.config_entry.options)
        if user_input is not None:
            for conf_key in EQUIPMENT_ROLES.values():
                if user_input.get(conf_key):
                    options[conf_key] = user_input[conf_key]
                else:
                    options.pop(conf_key, None)
            return await self._save(options)

        domains = {
            CONF_POOL_SYSTEM_ENTITY: ["switch", "input_boolean", "binary_sensor"],
            CONF_HEAT_PUMP_ENTITY: [
                "switch",
                "climate",
                "water_heater",
                "input_boolean",
                "binary_sensor",
            ],
            CONF_FILTRATION_SCHEDULE_ENTITY: ["schedule"],
            CONF_PUMP_ENTITY: ["switch", "input_boolean", "binary_sensor", "fan"],
            CONF_POOL_LIGHT_ENTITY: ["light", "switch"],
            CONF_COVER_ENTITY: ["cover", "switch", "binary_sensor"],
        }
        schema: dict[vol.Marker, Any] = {}
        for conf_key in EQUIPMENT_ROLES.values():
            schema[
                vol.Optional(conf_key, description={"suggested_value": options.get(conf_key)})
            ] = EntitySelector(EntitySelectorConfig(domain=domains[conf_key]))
        return self.async_show_form(step_id="equipment", data_schema=vol.Schema(schema))

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Link external sensors (e.g. a smart probe) to the pool."""
        options = dict(self.config_entry.options)
        if user_input is not None:
            for conf_key in LINKED_SOURCES.values():
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
            return await self._save(options)

        modules = list(options.get(CONF_MODULES, ()))
        schema: dict[vol.Marker, Any] = {}
        schema.update(_reminder_days_schema(modules, options))
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
                        default=options.get(CONF_NOTIFY_SERVICE, ""),
                    ): TextSelector(),
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
