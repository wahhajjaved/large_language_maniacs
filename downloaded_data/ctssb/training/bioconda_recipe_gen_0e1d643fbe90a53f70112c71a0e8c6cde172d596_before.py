import pkg_resources
import os


class BuildScript:
    """ Represents a build.sh """

    def __init__(self, name, path, strategy, filesystem, script_content=None):
        self.name = name
        self._path = path
        self._lines = list()
        self._filesystem = filesystem

        if script_content is not None and strategy.startswith("python"):
            if "python" in script_content:
                self._lines = [script_content.replace("$PYTHON", "python")]
            else:
                python_build_script = "$PYTHON %s" % script_content
                self._lines = [python_build_script]

        else:
            build_template_file = pkg_resources.resource_filename(
                __name__, os.path.join("recipes", self.strategy_to_template(strategy))
            )
            with open(build_template_file, "r") as template:
                self._lines = template.readlines()


    def __eq__(self, other):
        """ Overwrite default implementation. Compare _lines instead of id """
        if isinstance(other, BuildScript):
            return self._lines == other._lines
        return False

    @property
    def path(self):
        return self._path

    @property
    def filesystem(self):
        return self._filesystem

    def strategy_to_template(self, strategy):
        if strategy == "autoconf":
            return "template_build_autoreconf.sh"
        elif strategy == "cmake":
            return "template_build_cmake.sh"
        else:
            return "template_build_python.sh"

    def write_build_script_to_file(self):
        """ Write build script to path/build.sh """
        lines_to_write = ["#!/bin/bash\n"] + self._lines
        with open(os.path.join(self._path, "build.sh"), "w") as fp:
            for line in lines_to_write:
                if line[-1] is "\n":
                    fp.write(line)
                else:
                    fp.write(line + "\n")

    def add_chmodx(self, file_path):
        self._lines.append("chmod +x %s\n" % file_path)

    def add_cmake_flags(self, flags):
        """ Add flags to the cmake call """
        for i, line in enumerate(self._lines):
            if line.startswith("cmake .."):
                self._lines[i] = "cmake .. %s" % flags

    def move_file_from_source_to_bin(self, file_path):
        """ Use cp to move a file from SRC_DIR to PREFIX/bin """
        self._lines.append("cp $SRC_DIR/%s $PREFIX/bin/" % file_path)

    def add_moving_bin_files(self):
        """ Add lines to make sure the bin files are moved """
        self._lines.append("mkdir -p $PREFIX/bin")
        self._lines.append("cp bin/%s $PREFIX/bin" % self.name)
