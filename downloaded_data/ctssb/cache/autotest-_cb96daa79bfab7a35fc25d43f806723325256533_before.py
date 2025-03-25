import re, string, logging
from autotest_lib.client.common_lib import error
import kvm_test_utils, kvm_utils, kvm_monitor


def run_physical_resources_check(test, params, env):
    """
    Check physical resources assigned to KVM virtual machines:
    1) Log into the guest
    2) Verify whether cpu counts ,memory size, nics' model,
       count and drives' format & count, drive_serial, UUID
       reported by the guest OS matches what has been assigned
       to the VM (qemu command line)
    3) Verify all MAC addresses for guest NICs

    @param test: kvm test object
    @param params: Dictionary with the test parameters
    @param env: Dictionary with test environment.
    """
    vm = kvm_test_utils.get_living_vm(env, params.get("main_vm"))
    timeout = int(params.get("login_timeout", 360))
    session = kvm_test_utils.wait_for_login(vm, timeout=timeout)

    logging.info("Starting physical resources check test")
    logging.info("Values assigned to VM are the values we expect "
                 "to see reported by the Operating System")
    # Define a failure counter, as we want to check all physical
    # resources to know which checks passed and which ones failed
    n_fail = 0

    # Check cpu count
    logging.info("CPU count check")
    expected_cpu_nr = int(params.get("smp"))
    actual_cpu_nr = vm.get_cpu_count()
    if expected_cpu_nr != actual_cpu_nr:
        n_fail += 1
        logging.error("CPU count mismatch:")
        logging.error("    Assigned to VM: %s" % expected_cpu_nr)
        logging.error("    Reported by OS: %s" % actual_cpu_nr)

    # Check memory size
    logging.info("Memory size check")
    expected_mem = int(params.get("mem"))
    actual_mem = vm.get_memory_size()
    if actual_mem != expected_mem:
        n_fail += 1
        logging.error("Memory size mismatch:")
        logging.error("    Assigned to VM: %s" % expected_mem)
        logging.error("    Reported by OS: %s" % actual_mem)

    # Define a function for checking number of hard drivers & NICs
    def check_num(devices, info_cmd, check_str):
        f_fail = 0
        expected_num = kvm_utils.get_sub_dict_names(params, devices).__len__()
        try:
            o = vm.monitor.info(info_cmd)
        except kvm_monitor.MonitorError, e:
            f_fail += 1
            logging.error(e)
            logging.error("info/query monitor command failed (%s)", info_cmd)

        actual_num = string.count(o, check_str)
        if expected_num != actual_num:
            f_fail += 1
            logging.error("%s number mismatch:")
            logging.error("    Assigned to VM: %d" % expected_num)
            logging.error("    Reported by OS: %d" % actual_num)
        return expected_num, f_fail

    logging.info("Hard drive count check")
    drives_num, f_fail = check_num("images", "block", "type=hd")
    n_fail += f_fail

    logging.info("NIC count check")
    nics_num, f_fail = check_num("nics", "network", "model=")
    n_fail += f_fail

    # Define a function for checking hard drives & NICs' model
    def chk_fmt_model(device, fmt_model, info_cmd, str):
        f_fail = 0
        devices = kvm_utils.get_sub_dict_names(params, device)
        for chk_device in devices:
            expected = kvm_utils.get_sub_dict(params, chk_device).get(fmt_model)
            if not expected:
                expected = "rtl8139"
            try:
                o = vm.monitor.info(info_cmd)
            except kvm_monitor.MonitorError, e:
                f_fail += 1
                logging.error(e)
                logging.error("info/query monitor command failed (%s)",
                              info_cmd)

            device_found = re.findall(str, o)
            logging.debug("Found devices: %s" % device_found)
            found = False
            for fm in device_found:
                if expected in fm:
                    found = True

            if not found:
                f_fail += 1
                logging.error("%s model mismatch:")
                logging.error("    Assigned to VM: %s" % expected)
                logging.error("    Reported by OS: %s" % device_found)
        return f_fail

    logging.info("NICs model check")
    f_fail = chk_fmt_model("nics", "nic_model", "network", "model=(.*),")
    n_fail += f_fail

    logging.info("Drive format check")
    f_fail = chk_fmt_model("images", "drive_format", "block", "(.*)\: type=hd")
    n_fail += f_fail

    logging.info("Network card MAC check")
    try:
        o = vm.monitor.info("network")
    except kvm_monitor.MonitorError, e:
        n_fail += 1
        logging.error(e)
        logging.error("info/query monitor command failed (network)")
    found_mac_addresses = re.findall("macaddr=(.*)", o)
    logging.debug("Found MAC adresses: %s" % found_mac_addresses)

    for nic_name in kvm_utils.get_sub_dict_names(params, "nics"):
        nic_params = kvm_utils.get_sub_dict(params, nic_name)
        mac, ip = kvm_utils.get_mac_ip_pair_from_dict(nic_params)
        if not string.lower(mac) in found_mac_addresses:
            n_fail += 1
            logging.error("MAC address mismatch:")
            logging.error("    Assigned to VM (not found): %s" % mac)

    # Define a function to verify UUID & Serial number
    def verify_device(expect, name, verify_cmd):
        f_fail = 0
        if verify_cmd:
            actual = session.get_command_output(verify_cmd)
            if not string.upper(expect) in actual:
                f_fail += 1
                logging.error("%s mismatch:")
                logging.error("    Assigned to VM: %s" % string.upper(expect))
                logging.error("    Reported by OS: %s" % actual)
        return f_fail

    logging.info("UUID check")
    if vm.get_uuid():
        f_fail = verify_device(vm.get_uuid(), "UUID",
                               params.get("catch_uuid_cmd"))
        n_fail += f_fail

    logging.info("Hard Disk serial number check")
    catch_serial_cmd = params.get("catch_serial_cmd")
    f_fail = verify_device(params.get("drive_serial"), "Serial",
                           catch_serial_cmd)
    n_fail += f_fail

    if n_fail != 0:
        raise error.TestFail("Physical resources check test reported %s "
                             "failures. Please verify the test logs." % n_fail)

    session.close()
