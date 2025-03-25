#!/usr/bin/python
import subprocess
import re
import logging

class IpSetException(Exception):
    """Base class for IpSet thrown exceptions"""
    def __init__(self, inner_exc):
        self.inner = inner_exc

    def __str__(self):
        return "IpSet Failure on:\n%s" % self.inner


class IpSetList(object):
    """Object representation of operating system's IP sets"""
    def __init__(self, listName, listType, listItems=None):
        self.listName = listName
        self.listType = listType
        self.listItems = listItems if listItems else []

    def __repr__(self):
        return '<%s name=%r type=%r items=%r>' % (self.__class__.__name__, self.listName, self.listType, self.listItems)


class IpSetCommandWrapper(object):
    """ipset command interface for manipulating Linux IP sets in Python

    see man ipset(8) for more information"""

    @staticmethod
    def save(name=None):
        """Create IpSetList objects for all IP sets (unless `name' is specified) currently defined on the host

        @return a dictionary of {'ipset_name': IpSetList object, ...}
        """
        ret = {}

        command = ["ipset", "save"]
        if name:
            command.append(name)

        try:
            ipset_output = subprocess.check_output(command).split("\n")
        except subprocess.CalledProcessError as e:
            raise IpSetException(e)

        for line in ipset_output:
            if not line:
                continue

            # process "create" lines
            match = re.match(r'^create (?P<name>\S+) (?P<type>.+?)\s*$', line)
            if match:
                groups = match.groupdict()
                ret[groups['name']] = IpSetList(groups['name'], groups['type'])
                continue

            # process "add" lines
            match = re.match(r'^add (?P<name>\S+) (?P<value>.+)$', line)
            if match:
                groups = match.groupdict()
                ret[groups['name']].listItems.append(groups['value'])
                continue

            # this part should never be reached
            logging.warn('unprocessed line: %s', line)

        return ret

    @staticmethod
    def add(name, item):
        """Add item `item' to ipset list `name'"""
        subprocess.check_call(["ipset", "add", name, item])

    @staticmethod
    def remove(name, item):
        """Remove item `item' from ipset list `name'"""
        subprocess.check_call(["ipset", "del", name, item])

class IpSet(object):
    """High level, object oriented interface to Linux IP sets"""

    def __init__(self, name):
        """Create an IpSet object for `name' kernel ipset, populate it with data from the kernel"""
        self.name = name
        self.load()

    def load(self):
        """Refresh the data from the kernel"""
        self.ipset = IpSetCommandWrapper.save(self.name)[self.name]

    def getItems(self):
        """Return the items inside this set"""
        return self.ipset.listItems

    def add(self, item):
        """Add item `item' to the list"""
        IpSetCommandWrapper.add(self.name, item)
        self.ipset.listItems.append(item)

    def remove(self, item):
        """Remove item `item' from the list"""
        IpSetCommandWrapper.remove(self.name, item)
        self.ipset.listItems.remove(item)

    def __hasitem__(self, item):
        """Returns true if `item' exists in this IP set"""
        return item in self.ipset.listItems

    def __repr__(self):
        return '<%s name=%r ips=%r>' % (self.__class__.__name__, self.name, self.getItems())

if __name__ == '__main__':
    main()

