from __future__ import with_statement
import re


class ConfigFile:

    def __init__(self, config):
        self.config = config

    @staticmethod
    def load(config_file):
        config_data = {}        
        with open(config_file) as config:
            section_name = None
            for config_line in config.readlines():
                section_match = re.match(
                    "^\\s*\[\\s*([^\]]+)\\s*\]\\s*$",
                    config_line, re.I | re.S
                )
                parameter_match = re.match(
                    "^\\s*([^#][\\S]*)\\s*=\\s*(.*?)\\s*$",
                    config_line, re.I | re.S
                )
        
                if section_match:
                    section_name = section_match.group(1)
                    config_data[section_name] = {}
                elif parameter_match:
                    key = parameter_match.group(1).strip()
                    value = parameter_match.group(2).strip()
        
                    config_data[section_name][key] = value

        return ConfigFile(config_data)

    def set(self, section, key, value):
        if section not in self.config.keys:
            self.config[section] = {}
        self.config[section][key] = value

    def get(self, section, key):
        return self.config.get(section, {}).get(key, None)

    def find(self, key):
        sections = []
        for section, parameters in self.config.items():
            if key in parameters.keys():
                sections.append(section)
        return sections

    def dump(self, config_file):
        with open(config_file, "w") as config:
            for section, parameters in self.config.items():
                config.write("[%s]\r\n" % section)
                for key, value in parameters.items():
                    config.write("%s = %s\r\n" % (key, value))
