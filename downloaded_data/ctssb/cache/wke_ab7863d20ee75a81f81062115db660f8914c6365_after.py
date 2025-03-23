SUMMARY = "list available images"

class Command(object):
    def __init__(self, docker_client, config):
        self.docker_client = docker_client
        self.config = config

    def expected_params(self):
        return 0

    def summary(self):
        return "list available images"

    def usage(self):
        return ""

    def run(self):
        images = self.docker_client.images()

        for i in images:
            prefix = self.config.get_canonical_image("")
            tag = i['RepoTags']
            if tag and tag[0].startswith(prefix):
                print(tag[0][len(prefix):-len(":latest")])

