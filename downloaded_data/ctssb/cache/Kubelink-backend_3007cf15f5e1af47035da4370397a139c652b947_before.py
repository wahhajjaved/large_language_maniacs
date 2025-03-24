import subprocess
from subprocess import Popen, PIPE
import json
import yaml
from constants import service_types
import etcd

class ServiceCatalogClient(object):

    def __init__(self, contextName, etcd_client):
        self.context = contextName
        self.decoder = json.JSONDecoder()
        self.etcd_client = etcd_client
        
    def execute(self, cmd, read=False):
        newcmd = cmd + " --context "+self.context
        if read:
            newcmd += " -o json"
        jsonText = subprocess.check_output(newcmd, shell=True)
        if read:
            return self.decoder.decode(jsonText)
        else:
            return None

    def execute_with_stdin(self, input_str, read=False):
        newcmd = "kubectl --context "+self.context + " create -f - "
        if read:
            newcmd += " -o json"
        print newcmd
        print type(input_str)
        print input_str 
        p = Popen(newcmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate(input_str)
        print "stdout == " + stdout
        print "stderr == " + stderr


    def get_and_update_counter(self):
        key = "/counter"
        # TODO need lock?
        curr = self.etcd_client.read(key).value
        new = int(curr) + 1
        self.etcd_client.write(key, str(new))
        return curr

    def get_catalog(self):
        command = "kubectl get serviceclasses"
        return self.execute(command, True)

    def get_pod(self, label):
        command = "kubectl get pods -l instance=" + label + " -o json"
        json_text = subprocess.check_output(command, shell=True)
        json_dict = json.loads(json_text)
        if len(json_dict["items"]) == 0:    # no pod exists
            self.etcd_client.delete("/instances/standalone/"+label)
            return "Terminated"
        statuses = json_dict["items"][0]["status"]["containerStatuses"]
        final_status = "Running"
        for item in statuses:
            if "running" not in item["state"].keys():
                final_status = "Pending"

        # update in etcd also
        output = self.etcd_client.read("/instances/standalone/"+label).value
        output = json.loads(output)
        output["status"] = final_status
        self.etcd_client.write("/instances/standalone/"+label, json.dumps(output))
        return final_status

    def create_instance(self, service_class_name, service_id):
        key = "/standalone/" + service_types[service_class_name] + "/" + service_id
        output = self.etcd_client.read(key).value
        print type(output)
        print output
        output = json.loads(output)
        k8s_config = output["config"]
        curr_counter = self.get_and_update_counter()
        k8s_config["metadata"]["name"] = k8s_config["metadata"]["name"] + "-" + str(curr_counter)
        k8s_config["spec"]["parameters"]["instance"] = k8s_config["metadata"]["name"]
        k8s_config["spec"]["parameters"]["instanceLabel"] = k8s_config["metadata"]["name"]
        self.execute_with_stdin(json.dumps(k8s_config))
        return k8s_config["metadata"]["name"]


def main():
    etcd_client = etcd.Client(host='etcd.kubelink.borathon.photon-infra.com', port=80)
    #print ServiceCatalogClient("bora-catalog", etcd_client).create_instance("mysql","4f6e6cf6-ffdd-425f-a2c7-3c9258ad2464")
    print ServiceCatalogClient("bora-catalog", etcd_client).get_pod("mysql-2")

#main()

        

