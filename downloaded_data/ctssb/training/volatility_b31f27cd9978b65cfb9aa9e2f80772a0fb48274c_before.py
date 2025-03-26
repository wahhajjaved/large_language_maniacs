# Volatility
# Copyright (C) 2007-2011 Volatile Systems
#
# Additional Authors:
# Michael Ligh <michael.ligh@mnin.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details. 
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA 
#

#pylint: disable-msg=C0111

import volatility.obj as obj
import volatility.utils as utils
import volatility.plugins.taskmods as taskmods
import volatility.plugins.filescan as filescan

# Inherit from Dlllist for command line options, FileScan for parse_string
class Handles(taskmods.DllList, filescan.FileScan):
    """Print list of open handles for each process"""

    def __init__(self, config, *args):
        filescan.FileScan.__init__(self, config, *args)
        taskmods.DllList.__init__(self, config, *args)
        config.add_option("PHYSICAL-OFFSET", short_option = 'P', default = False,
                          help = "Physical Offset", action = "store_true")
        config.add_option("OBJECT-TYPE", short_option = 't', default = None,
                          help = 'Show these object types (comma-separated)',
                          action = 'store', type = 'str')

    def full_key_name(self, handle):
        """Returns the full name of a registry key based on its CM_KEY_BODY handle"""
        output = []
        kcb = handle.KeyControlBlock
        while kcb.ParentKcb:
            if kcb.NameBlock == None:
                break
            output.append(str(kcb.NameBlock.Name))
            kcb = kcb.ParentKcb
        return "\\".join(reversed(output))

    def render_text(self, outfd, data):
        offsettype = "(V)" if not self._config.PHYSICAL_OFFSET else "(P)"

        outfd.write("{0:6}{1:6} {2:6} {3:<16} {4}\n".format(
            "Offset", offsettype, "Pid", "Type", "Details"))

        if self._config.OBJECT_TYPE:
            object_list = [s for s in self._config.OBJECT_TYPE.split(',')]
        else:
            object_list = []

        for pid, h, otype, name in data:
            if object_list and otype not in object_list:
                continue
            if not self._config.PHYSICAL_OFFSET:
                offset = h.obj_offset
            else:
                offset = h.obj_vm.vtop(h.obj_offset)

            outfd.write("{0:#010x}   {1:<6} {2:<16} {3}\n".format(
                offset, pid, otype, name))

    def calculate(self):
        ## Will need the kernel AS for later:
        self.kernel_address_space = utils.load_as(self._config)

        for task in taskmods.DllList.calculate(self):
            pid = task.UniqueProcessId
            if task.ObjectTable.HandleTableList:
                for h in task.ObjectTable.handles():
                    name = ""
                    h.kas = self.kernel_address_space
                    otype = h.get_object_type()
                    if otype == "File":
                        file_obj = obj.Object("_FILE_OBJECT", h.Body.obj_offset, h.obj_vm)
                        if file_obj.FileName:
                            name = self.parse_string(file_obj.FileName)
                    elif otype == "Key":
                        key_obj = obj.Object("_CM_KEY_BODY", h.Body.obj_offset, h.obj_vm)
                        name = self.full_key_name(key_obj)
                    elif otype == "Process":
                        proc_obj = obj.Object("_EPROCESS", h.Body.obj_offset, h.obj_vm)
                        name = "{0}({1})".format(proc_obj.ImageFileName, proc_obj.UniqueProcessId)
                    elif otype == "Thread":
                        thrd_obj = obj.Object("_ETHREAD", h.Body.obj_offset, h.obj_vm)
                        name = "TID {0} PID {1}".format(thrd_obj.Cid.UniqueThread, thrd_obj.Cid.UniqueProcess)
                    else:
                        name = repr(h.get_object_name())

                    yield pid, h, otype, name
