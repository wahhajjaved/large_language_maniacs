"""
The Builder is responsible for finding and building docker images in
the correct order

Building an image requires building all dependent images, creating the necessary
context, and actually building the current image.
"""

from harpoon.errors import NoSuchImage, BadCommand, FailedImage, UserQuit, BadEnvironment, HarpoonError
from harpoon.ship.progress_stream import ProgressStream, Failure, Unknown
from harpoon.processes import command_output
from harpoon.option_spec import command_objs
from harpoon.ship.runner import Runner
from harpoon import helpers as hp
from harpoon.layers import Layers

from input_algorithms.spec_base import NotSpecified
from contextlib import contextmanager
from itertools import chain
import docker.errors
import humanize
import logging
import uuid
import six
import sys
import os

log = logging.getLogger("harpoon.ship.builder")

########################
###   PROGRESS STREAM
########################

class BuildProgressStream(ProgressStream):
    def setup(self):
        self.last_line = ""
        self.current_action = ""
        self.current_container = None

    def interpret_line(self, line_detail):
        if "stream" in line_detail:
            self.interpret_stream(line_detail["stream"])
            self.last_line = line_detail["stream"]
        elif "status" in line_detail:
            self.interpret_status(line_detail["status"])
            self.last_line = line_detail["status"]
        else:
            self.interpret_unknown(line_detail)
            self.last_line = str(line_detail)

    def interpret_stream(self, line):
        if line.startswith("Step "):
            action = line[line.find(":")+1:].strip()
            self.current_action = action[:action.find(" ")].strip()

        if line.strip().startswith("---> Running in"):
            self.current_container = line[len("---> Running in "):].strip()
        elif line.strip().startswith("Successfully built"):
            self.current_container = line[len("Successfully built"):].strip()

        if self.last_line.startswith("Step ") and line.strip().startswith("---> "):
            if self.current_action == "FROM":
                self.cached = True
            else:
                self.cached = False

        if line.strip().startswith("---> Running in"):
            self.cached = False
        elif line.strip().startswith("---> Using cache"):
            self.cached = True

        self.add_line(line)

    def interpret_status(self, line):
        if line.startswith("Pulling image"):
            if not line.endswith("\n"):
                line = "{0}\n".format(line)
        else:
            line = "\r{0}".format(line)

        if "already being pulled by another client" in line or "Pulling repository" in line:
            self.cached = False
        self.add_line(line)

########################
###   BUILDER
########################

class Builder(object):
    """Build an image from Image configuration"""

    ########################
    ###   USAGE
    ########################

    def make_image(self, conf, images, chain=None, parent_chain=None, made=None, ignore_deps=False, ignore_parent=False, share_with_deps=None, pushing=False):
        """Make us an image"""
        made = {} if made is None else made
        chain = [] if chain is None else chain
        parent_chain = [] if parent_chain is None else parent_chain

        if share_with_deps is None:
            share_with_deps = self.determine_share_with_deps(images, conf)

        if conf.name in made:
            return

        if conf.name in chain and not ignore_deps:
            raise BadCommand("Recursive dependency images", chain=chain + [conf.name])

        if conf.name in parent_chain and not ignore_parent:
            raise BadCommand("Recursive FROM statements", chain=parent_chain + [conf.name])

        if conf.name not in images:
            raise NoSuchImage(looking_for=conf.name, available=images.keys())

        if not ignore_deps:
            for dependency, image in conf.dependency_images():
                self.make_image(images[dependency], images, chain=chain + [conf.name], made=made, share_with_deps=share_with_deps, pushing=pushing)

        if not ignore_parent:
            parent_image = conf.commands.parent_image
            if not isinstance(parent_image, six.string_types):
                self.make_image(parent_image, images, chain, parent_chain + [conf.name], made=made, share_with_deps=share_with_deps, pushing=pushing)

        # Should have all our dependencies now
        log.info("Making image for '%s' (%s) - FROM %s", conf.name, conf.image_name, conf.commands.parent_image_name)
        cached = self.build_image(conf, share_with_deps, pushing=pushing)
        made[conf.name] = True
        return cached

    def build_image(self, conf, share_with_deps=None, pushing=False):
        """Build this image"""
        if share_with_deps is None:
            share_with_deps = []

        with self.context(conf) as context:
            try:
                stream = BuildProgressStream(conf.harpoon.silent_build)
                with self.remove_replaced_images(conf) as info:
                    if conf.recursive is NotSpecified:
                        cached = self.do_build(conf, context, stream)
                    else:
                        cached = self.do_recursive_build(conf, context, stream, needs_provider=conf.name in share_with_deps)
                    info['cached'] = cached
            except (KeyboardInterrupt, Exception) as error:
                exc_info = sys.exc_info()
                if stream.current_container:
                    Runner().stage_build_intervention(conf, stream.current_container)

                if isinstance(error, KeyboardInterrupt):
                    raise UserQuit()
                else:
                    six.reraise(*exc_info)

            try:
                for squash_options, condition in [(conf.squash_after, True), (conf.squash_before_push, pushing)]:
                    if squash_options is not NotSpecified and condition:
                        if type(squash_options) is command_objs.Commands:
                            squash_commands = squash_options.docker_lines_list
                        self.squash_build(conf, context, stream, squash_commands)
                        cached = False
            except (KeyboardInterrupt, Exception) as error:
                exc_info = sys.exc_info()
                if isinstance(error, KeyboardInterrupt):
                    raise UserQuit()
                else:
                    six.reraise(*exc_info)

        return cached

    def layered(self, images, only_pushable=False):
        """Yield layers of images"""
        if only_pushable:
            operate_on = dict((image, instance) for image, instance in images.items() if instance.image_index)
        else:
            operate_on = images

        layers = Layers(operate_on, all_images=images)
        layers.add_all_to_layers()
        return layers.layered

    ########################
    ###   UTILITY
    ########################

    def determine_share_with_deps(self, images, root_conf, share_with=None):
        """Determine all the containers that are in a volumes.share_with"""
        if share_with is None:
            share_with = []

        share_with.extend(root_conf.shared_volume_containers())
        for dependency, image in root_conf.dependency_images():
            self.determine_share_with_deps(images, images[dependency], share_with=share_with)

        return set(share_with)

    @contextmanager
    def context(self, conf):
        with conf.make_context() as context:
            self.log_context_size(context, conf)
            yield context

    def log_context_size(self, context, conf):
        context_size = humanize.naturalsize(os.stat(context.name).st_size)
        log.info("Building '%s' in '%s' with %s of context", conf.name, conf.context.parent_dir, context_size)

    @contextmanager
    def remove_replaced_images(self, conf):
        current_ids = None
        if not conf.harpoon.keep_replaced:
            try:
                current_id = conf.harpoon.docker_context.inspect_image("{0}:latest".format(conf.image_name))["Id"]
            except docker.errors.APIError as error:
                if str(error).startswith("404 Client Error: Not Found"):
                    current_id = None
                else:
                    raise

        info = {"cached": False}
        yield info

        if current_id and not info.get("cached"):
            log.info("Looking for replaced images to remove")
            untagged = [image["Id"] for image in conf.harpoon.docker_context.images(filters={"dangling": True})]
            if current_id in untagged:
                log.info("Deleting replaced image\ttag=%s\told_hash=%s", "{0}:latest".format(conf.image_name), current_id)
                try:
                    conf.harpoon.docker_context.remove_image(current_id)
                except Exception as error:
                    log.error("Failed to remove replaced image\thash=%s\terror=%s", current_id, error)

    def do_build(self, conf, context, stream, image_name=None, verbose=False):
        if image_name is None:
            image_name = conf.image_name

        context.close()
        for line in conf.harpoon.docker_context.build(fileobj=context.tmpfile, custom_context=True, tag=image_name, stream=True, rm=True):
            try:
                stream.feed(line)
            except Failure as error:
                raise FailedImage("Failed to build an image", image=conf.name, msg=error)
            except Unknown as error:
                log.warning("Unknown line\tline=%s", error)

            for part in stream.printable():
                hp.write_to(conf.harpoon.stdout, part)
            conf.harpoon.stdout.flush()

        return stream.cached

    def do_recursive_build(self, conf, context, stream, needs_provider=False):
        """Do a recursive build!"""
        from harpoon.option_spec.image_objs import Volumes
        from harpoon.ship.runner import Runner
        conf_image_name = conf.name
        if conf.image_name_prefix not in (NotSpecified, "", None):
            conf_image_name = "{0}-{1}".format(conf.image_name_prefix, conf.name)

        test_conf = conf.clone()
        test_conf.image_name = "{0}-tester".format(conf_image_name)
        log.info("Building test image for recursive image to see if the cache changed")
        with self.remove_replaced_images(test_conf) as info:
            cached = self.do_build(test_conf, context, stream)
            info['cached'] = cached

        have_final = "{0}:latest".format(conf.image_name) in chain.from_iterable([image["RepoTags"] for image in conf.harpoon.docker_context.images()])

        provider_name = "{0}-provider".format(conf_image_name)
        provider_conf = conf.clone()
        provider_conf.name = "provider"
        provider_conf.image_name = provider_name
        provider_conf.container_id = None
        provider_conf.container_name = "{0}-intermediate-{1}".format(provider_name, str(uuid.uuid1())).replace("/", "__")
        provider_conf.bash = NotSpecified
        provider_conf.command = NotSpecified

        if not have_final:
            log.info("Building first image for recursive image")
            with context.clone_with_new_dockerfile(conf, conf.recursive.make_first_dockerfile(conf.docker_file)) as new_context:
                self.do_build(conf, new_context, stream)

        if not needs_provider and cached:
            return cached

        with self.remove_replaced_images(provider_conf) as info:
            if cached:
                with conf.make_context(docker_file=conf.recursive.make_provider_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                    self.log_context_size(provider_context, provider_conf)
                    info['cached'] = self.do_build(provider_conf, provider_context, stream, image_name=provider_name)
                    conf.from_name = conf.image_name
                    conf.image_name = provider_name
                    conf.deleteable = True
                    return cached
            else:
                log.info("Building intermediate provider for recursive image")
                with context.clone_with_new_dockerfile(conf, conf.recursive.make_changed_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                    self.log_context_size(provider_context, provider_conf)
                    self.do_build(provider_conf, provider_context, stream, image_name=provider_name)

        builder_name = "{0}-for-commit".format(conf_image_name)
        builder_conf = conf.clone()

        builder_conf.image_name = builder_name
        builder_conf.container_id = None
        builder_conf.container_name = "{0}-intermediate-{1}".format(builder_name, str(uuid.uuid1())).replace("/", "__")
        builder_conf.volumes = Volumes(mount=[], share_with=[provider_conf])
        builder_conf.bash = NotSpecified
        builder_conf.command = NotSpecified
        log.info("Building intermediate builder for recursive image")
        with self.remove_replaced_images(builder_conf) as info:
            with context.clone_with_new_dockerfile(conf, conf.recursive.make_builder_dockerfile(conf.docker_file)) as builder_context:
                self.log_context_size(builder_context, builder_conf)
                info['cached'] = self.do_build(builder_conf, builder_context, stream, image_name=builder_name)

        log.info("Running and committing builder container for recursive image")
        with self.remove_replaced_images(conf):
            Runner().run_container(builder_conf, {provider_conf.name:provider_conf, builder_conf.name:builder_conf}, detach=False, dependency=False, tag=conf.image_name)

        log.info("Removing intermediate image %s", builder_conf.image_name)
        conf.harpoon.docker_context.remove_image(builder_conf.image_name)

        if not needs_provider:
            return cached

        log.info("Building final provider of recursive image")
        with self.remove_replaced_images(provider_conf) as info:
            with conf.make_context(docker_file=conf.recursive.make_provider_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                self.log_context_size(provider_context, provider_conf)
                info['cached'] = self.do_build(provider_conf, provider_context, stream, image_name=provider_name)

        conf.from_name = conf.image_name
        conf.image_name = provider_name
        conf.deleteable = True
        return cached

    def squash_build(self, conf, context, stream, squash_commands):
        """Do a squash build"""
        from harpoon.option_spec.image_objs import DockerFile
        squashing = conf
        output, status = command_output("which docker-squash")
        if status != 0:
            raise BadEnvironment("Please put docker-squash in your PATH first: https://github.com/jwilder/docker-squash")

        if squash_commands:
            squasher_conf = conf.clone()
            squasher_conf.image_name = "{0}-for-squashing".format(conf.name)
            if conf.image_name_prefix not in ("", None, NotSpecified):
                squasher.conf.image_name = "{0}-{1}".format(conf.image_name_prefix, squasher_conf.image_name)

            with self.remove_replaced_images(squasher_conf) as info:
                self.log_context_size(context, conf)
                original_docker_file = conf.docker_file
                new_docker_file = DockerFile(["FROM {0}".format(conf.image_name)] + squash_commands, original_docker_file.mtime)
                with context.clone_with_new_dockerfile(squasher_conf, new_docker_file) as squasher_context:
                    self.log_context_size(squasher_context, squasher_conf)
                    info['cached'] = self.do_build(squasher_conf, squasher_context, stream)
            squashing = squasher_conf

        log.info("Saving image\timage=%s", squashing.image_name)
        with hp.a_temp_file() as fle:
            res = conf.harpoon.docker_context.get_image(squashing.image_name)
            fle.write(res.read())
            fle.close()

            with hp.a_temp_file() as fle2:
                output, status = command_output("sudo docker-squash -i {0} -o {1} -t {2} -verbose".format(fle.name, fle2.name, conf.image_name), verbose=True, timeout=600)
                if status != 0:
                    raise HarpoonError("Failed to squash the image!")

                output, status = command_output("docker load", stdin=open(fle2.name), verbose=True, timeout=600)
                if status != 0:
                    raise HarpoonError("Failed to load the squashed image")

        if squashing is not conf:
            log.info("Removing intermediate image %s", squashing.image_name)
            conf.harpoon.docker_context.remove_image(squashing.image_name)

