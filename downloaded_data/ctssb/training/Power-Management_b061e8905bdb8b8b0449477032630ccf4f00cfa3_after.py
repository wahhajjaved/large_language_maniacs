import sys
from cloudshell.core.logger.qs_logger import get_qs_logger

SEVERITY_INFO = 20
SEVERITY_ERROR = 40


class QualiError(Exception):
    def __init__(self, name, message):
        self.message = message
        self.name = name

    def __str__(self):
        return 'CloudShell error at ' + self.name + '. Error is:' + self.message


class device_power_mgmt:
    def __init__(self, api_session, reservation_id):
        self.logger = get_qs_logger("extensibility", "QS", "service")
        self.api_session = api_session
        self.id = reservation_id
        self.power_on_wl = ["power_on", "Power On", "Power ON"]  # whitelist for power on commands
        self.power_off_wl = ["power_off", "Power Off", "Power OFF"]  # whitelist for power off commands
        self.shutdown_wl = ["Graceful Shutdown", "shutdown", "graceful_shutdown"]  # whitelist for shutdown cmds
        self.hard_power = False  # use power off command if a graceful isn't found
        # 'shutdown' is the official command in the Shell's Guidelines
        pass

    def write_message_to_output(self, message, severity_level=SEVERITY_INFO):
        """
        Write a message to the output window
        :param str message:  The message to be displayed in window
        :param integer severity_level: level of message, if == severity_error, colors red in window
        """
        if severity_level == SEVERITY_INFO:
            self.api_session.WriteMessageToReservationOutput(self.id, message)
        elif severity_level == SEVERITY_ERROR:
            self.api_session.WriteMessageToReservationOutput(self.id, '<font color="red">' + message + '</font>')

    def report_error(self, error_message, raise_error=True, write_to_output_window=False):
        """
        Report on an error to the log file, output window is optional.There is also an option to raise the error up
        :param str error_message:  The error message you would like to present
        :param bool raise_error:  Do you want to throw an exception
        :param bool write_to_output_window:  Would you like to write the message to the output window
        """
        self.logger.error(error_message)
        if write_to_output_window:
            self.write_message_to_output(error_message, SEVERITY_ERROR)
        if raise_error:
            raise QualiError(self.id, error_message)

    def report_info(self, message, write_to_output_window=False):
        """
        Report information to the log file, output window is optional.
        :param str message:  The message you would like to present
        :param bool write_to_output_window:  Would you like to write the message to the output window?
        """
        self.logger.info(message)
        if write_to_output_window:
            self.write_message_to_output(message, SEVERITY_INFO)

    def _item_in_list(self, i, l):
        """
        Returns Boolean if i in contained in l
        :param str i: the item to look for in the list
        :param list of str l: The list of items to look in
        :return: bool
        """
        try:
            idx = l.index(i)
            return True
        except:
            return False

    def _has_power_on(self, cmd_list):
        """
        Checks to see if the cmd_list contains one of the whitelisted power on commands
        returns command name if found, else ''
        :param cmd_list: list of str
        :return: str
        """
        cmd_name = ''
        for each in cmd_list:
            check = self._item_in_list(each.Name, self.power_on_wl)
            if check:
                cmd_name = each.Name
                break

        return cmd_name

    def _has_power_off(self, cmd_list):
        """
        Checks to see if the cmd_list contains one of the whitelisted power off commands
        return command name if found, else ''
        :param cmd_list: list of str
        :return: boolean
        """
        cmd_name = ''
        for each in cmd_list:
            check = self._item_in_list(each.Name, self.power_off_wl)
            if check:
                cmd_name = each.Name
                break

        return cmd_name

    def _has_shutdown(self, cmd_list):
        """
        Checks to see if the cmd_list contains one of the whitelisted shutdown commands
        returns command name if found, else ''
        :param cmd_list:
        :return:
        """
        cmd_name = ''
        for each in cmd_list:
            check = self._item_in_list(each.Name, self.shutdown_wl)
            if check:
                cmd_name = each.Name
                break

        return cmd_name

    def call_power_on(self, resource_list, source):
        """
        Walks the input list of devices, and calls the white-listed power on command if that device has one
        :param resource_list: list of str
        :return: int
        """
        try:
            for dev_name in resource_list:
                dev_cmd_list = self.api_session.GetResourceCommands(dev_name).Commands
                dev_cmd_name = self._has_power_on(dev_cmd_list)
                if dev_cmd_name != '':
                    # self.api_session.EnqueueResourceCommand(self.id, dev_name, dev_cmd_name)
                    # -- Old command for driver build commands only - updated is ExecuteCommand for all
                    self.api_session.EnqueueCommand(self.id, dev_name, 'Resource', dev_cmd_name)
                    self.report_info('Command "' + dev_cmd_name + '" called on ' + dev_name)
            return 1
        except QualiError as qe:
            err = "Failed on calling " + dev_cmd_name + " from " + source + ". " + str(qe)
            self.report_error(error_message=err, write_to_output_window=True)
            return -1
        except:
            err = "Failed on calling " + dev_cmd_name + " from " + source + ". Unexpected error: " + "'" +\
                  str(sys.exc_info()[0]) + "'"
            self.report_error(error_message=err, write_to_output_window=True)
            return -99

    def call_power_off(self, resource_list, source):
        """
        Walks the input list of devices, and calls the white-listed power down option (shutdown first, hard
        power off second) if that device has one
        :param resource_list: list of str
        :return: int
        """
        try:
            for dev_name in resource_list:
                dev_cmd_list = self.api_session.GetResourceCommands(dev_name).Commands
                dev_cmd_name = self._has_shutdown(dev_cmd_list)
                if dev_cmd_name == '' and self.hard_power:
                    dev_cmd_name = self._has_power_off(dev_cmd_list)
                if dev_cmd_name != '':
                    # self.api_session.EnqueueResourceCommand(self.id, dev_name, dev_cmd_name)
                    # -- Old command for driver build commands only - updated is ExecuteCommand for all
                    # self.api_session.EnqueueCommand(self.id, dev_name, 'Resource', dev_cmd_name)
                    # use Execute instead of Enqueue because it's called from a 'Sync' -
                    # sync can't complete till this is done.
                    self.api_session.ExecuteCommand(self.id, dev_name, 'Resource', dev_cmd_name)
                    self.report_info('Command "' + dev_cmd_name + '" called on ' + dev_name)
            return 1
        except QualiError as qe:
            err = "Failed on calling " + dev_cmd_name + " from " + source + ". " + str(qe)
            self.report_error(error_message=err, write_to_output_window=True)
            return -1
        except:
            err = "Failed on calling " + dev_cmd_name + " from " + source + ". Unexpected error: " + "'" + \
                  str(sys.exc_info()[0]) + "'"
            self.report_error(error_message=err, write_to_output_window=True)
            return -99
