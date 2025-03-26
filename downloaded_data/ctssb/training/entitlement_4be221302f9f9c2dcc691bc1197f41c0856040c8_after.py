'''
commands to operate beaker
need beaker-client installed
'''
import time
from utils.tools.xmlparser.bkjobparser import BKJobParser
from utils.tools.shell.command import Command
from utils.tools.shell.remotesh import RemoteSH

class BeakerCMD(Command):

    def job_submit(self, job_xml):
        cmd = "bkr job-submit %s" % job_xml
        retcode, output = self.run(cmd)
        if retcode == 0:
            # Submitted: ['J:693133']
            job_id = output.strip("\n").split("[")[1].strip("'").strip("]").strip("'")
        return job_id

    def job_watch(self, job_id):
        cmd = "bkr job_watch %s" % job_id
        return self.run(cmd)

    def create_runtime_job(self, job_xml):
        return BKJobParser().runtime_job_copy(job_xml)

    def update_job_param(self, job_xml, task_name, parameter, value):
        BKJobParser(job_xml).update_param(task_name, parameter, value)

    def set_beaker_distro_name(self, job_xml, distro_name):
        BKJobParser(job_xml).update_distroRequires("distro_name", distro_name)

    def set_beaker_distro_variant(self, job_xml, distro_variant):
        BKJobParser(job_xml).update_distroRequires("distro_variant", distro_variant)

    def set_beaker_job_name(self, job_xml, job_name):
        BKJobParser(job_xml).update_whiteboard(job_name)

    def set_packages(self, job_xml, packages):
        BKJobParser(job_xml).add_packages(packages)

    def check_job_finished(self, job_id):
        cmd = "bkr job-logs %s | grep 'test_log--distribution-reservesys.log'" % job_id
        while True:
            retcode, output = self.run(cmd)
            if retcode == 0:
#                 reserved_machine = output.split("/")[2]
                reserved_machine = self.get_job_machine(job_id)
                return reserved_machine
            time.sleep(600)

    def get_job_machine(self, job_id):
        cmd = "curl -s `bkr job-logs %s | grep 'test_log--distribution-install-Sysinfo.log'` | grep Hostname" % job_id
        retcode, output = self.run(cmd)
        reserved_machine = output.split("=")[1].strip("\n").strip(" ")
        return reserved_machine

    def post_config_sam(self, sam_server):
        self.__deploy_sam(sam_server)
        self.__import_manifest(sam_server)

    def __deploy_sam(self, sam_server):
        cmd = "katello-configure --deployment=sam --user-pass=admin"
        RemoteSH.remote_run(cmd, sam_server, "root", "xxoo2014", 1800)

    def __import_manifest(self, sam_server):
        cmd = "headpin -u admin -p admin provider import_manifest --org=ACME_Corporation --name='Red Hat' --file=/root/sam_install_manifest.zip"
        RemoteSH.remote_run(cmd, sam_server, "root", "xxoo2014", 1800)

if __name__ == "__main__":
    test = BeakerCMD()
    test.post_config_sam("dell-per300-01.rhts.eng.bos.redhat.com")
    pass
