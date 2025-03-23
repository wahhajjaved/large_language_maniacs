import api.server

from flask.views import MethodView
from flask import request
from flask import jsonify

from api.configs.config import ACTIONS_TYPES
from api.configs.utils import HTTPStatusCodes
from api.services.fcm_service import FcmService
from api.services.gateways.gateways_devices_service import DevicesService
from api.services.gateways.gateways_devices_history_service import DevicesHistoryService
from api.services.gateways.gateways_rules_service import RulesService
from api.services.gateways.gateways_rules_history import RulesHistoryService
from api.services.users.users_service import UserService


class GatewaysDevicesActionsView(MethodView):
    POST_REQUIRED_FIELDS = {
        ACTIONS_TYPES.RULE_TRIGGERED: {"type", "rule", "timestamp", },
        ACTIONS_TYPES.CHANGE_VALUE: {"type", "device", "value", "timestamp"},
    }

    def __init__(self):
        self.devices_service = DevicesService()
        self.devices_history_service = DevicesHistoryService()
        self.rules_service = RulesService()
        self.rules_history_service = RulesHistoryService()
        self.user_service = UserService()

        self.fcm_service = FcmService()

    def _validate_post_body(self, body):
        for action in body:
            if not isinstance(action, dict):
                return "All actions must be provided as an object"

            if not action.get("type"):
                return "All the actions must have their type"

            if action["type"] not in self.POST_REQUIRED_FIELDS:
                api.server.app.logger.debug("Received unknown type of action: {}".format(action["type"]))
                continue

            missing_fields = self.POST_REQUIRED_FIELDS[action["type"]] - action.keys()
            if missing_fields:
                return "Missing fields: {}".format(missing_fields)

    def _update_devices_values(self, actions, gateway_uuid):
        if not actions:
            return

        devices_new_history = []
        devices_new_values = {}
        for action in actions:
            devices_new_history.append({
                "device_uuid": action["device"],
                "value": action["value"],
                "timestamp": action["timestamp"],
                "gateway_uuid": gateway_uuid,
            })
            devices_new_values[action["device"]] = action["value"]

        self.devices_history_service.insert_multiple(devices_new_history)
        for device_id, new_device_value in devices_new_values.items():
            self.devices_service.update_device_value(device_id, new_device_value)

    def _update_rule_triggered(self, actions, gateway_uuid):
        if not actions:
            return

        rules_history = []
        for action in actions:
            rules_history.append({
                "rule_id": action["rule"],
                "timestamp": action["timestamp"],
                "gateway_uuid": gateway_uuid,
            })

        self.rules_history_service.insert_multiple(rules_history)

    def _get_device_action_notification(self, gateway_uuid, action):
        device_uuid = action["device"]
        device = self.devices_service.find_device_from_gateway(device_uuid, gateway_uuid)
        if not device:
            return None

        notification = {
            "type": ACTIONS_TYPES.CHANGE_VALUE,
            "device_info": {
                "id": action["device"],
                "name": device["name"],
                "value": action["value"],
            }
        }
        return notification

    def _get_rule_trigger_action_notification(self, rule_id):
        rule = self.rules_service.find(rule_id)
        if not rule:
            return None

        notification = {
            "type": ACTIONS_TYPES.RULE_TRIGGERED,
            "rule_info": {
                "id": str(rule["_id"]),
                "name": rule["name"],
            }
        }
        return notification

    def _send_notifications(self, gateway_uuid, performed_actions):
        notifications_to_send = []
        for action in performed_actions:
            if action["type"] == ACTIONS_TYPES.CHANGE_VALUE:
                notification = self._get_device_action_notification(gateway_uuid, action)
                if not notification:
                    api.server.app.logger.error(
                        "Device with {} from gateway {} wasn't found"
                            .format(gateway_uuid, action["device"])
                    )
                    continue

                notifications_to_send.append(notification)

            elif action["type"] == ACTIONS_TYPES.CHANGE_VALUE:
                notification = self.rules_service.find(action["rule"])
                if not notification:
                    api.server.app.logger.error("Rule {} wasn't found".format(action["rule"]))
                    continue

                notifications_to_send.append(notification)

        if not notifications_to_send:
            api.server.app.logger.error(
                "From {} actions, no notification to be sent".format(performed_actions)
            )
            return

        USER_ID = "5cef014dbc9e3b3638cde0e8"
        user = self.user_service.find(USER_ID)
        if not user:
            api.server.app.logger.error(
                "Do not send notification because user {} wasn't found"
                    .format(USER_ID)
            )
            return

        registration_id = user["fcm_token"]
        registrations_ids = [registration_id, ]

        for notification in notifications_to_send:
            self.fcm_service.push_notification([registration_id, ], notification)
            api.server.app.logger.info(
                "Send notification {} -----> {} "
                    .format(notification, registrations_ids)
            )

    def post(self, gateway_uuid):
        body = request.get_json()
        validation_error_message = self._validate_post_body(body)
        if validation_error_message:
            api.server.app.logger.warning(
                "Some error occurred during the validation of the body. Reason: {}"
                    .format(validation_error_message)
            )
            response = {
                "message": validation_error_message,
            }
            return jsonify(response), HTTPStatusCodes.BAD_REQUEST

        api.server.app.logger.info("Devices actions Body: {}".format(body))
        performed_actions = {
            ACTIONS_TYPES.CHANGE_VALUE: [],
            ACTIONS_TYPES.RULE_TRIGGERED: [],
        }
        for action in body:
            if action["type"] == ACTIONS_TYPES.CHANGE_VALUE:
                performed_actions[ACTIONS_TYPES.CHANGE_VALUE].append(action)
            elif action["type"] == ACTIONS_TYPES.RULE_TRIGGERED:
                performed_actions[ACTIONS_TYPES.RULE_TRIGGERED].append(action)

        self._update_devices_values(performed_actions[ACTIONS_TYPES.CHANGE_VALUE], str(gateway_uuid))
        self._update_rule_triggered(performed_actions[ACTIONS_TYPES.RULE_TRIGGERED], str(gateway_uuid))

        self._send_notifications(gateway_uuid, body)

        response = {
            "message": "Actions has been registered"
        }
        return jsonify(response), HTTPStatusCodes.CREATED
