# Rekall Memory Forensics
# Copyright 2014 Google Inc. All Rights Reserved.
#
# Authors:
# Michael Cohen <scudette@google.com>
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

"""This file implements ObjectRenderers for the JsonRenderer.

The JsonRenderer aims to serialize and recreate objects exactly at they were
upon unserializing them. This means that the environment loading the serialized
data must have access to all the necessary files (i.e. the complete memory image
file).

For example consider an _EPROCESS() instance. In memory, python merely stores
the following items in the object:

- obj_offset: The offset in the address space.
- obj_profile: The profile this object came from.
- obj_vm: The address space the object will be read from.

When the object is read, the address space is read at obj_offset, the data is
decoded and possibly other members are created using the profile. We do not know
the value of the object without reading it from the image.

Contrast this with the WebConsoleRenderer which needs to be deserialized in an
environment which does not have access to the original image. In this case we
must store all kinds of additional metadata about each object, since the decoder
is unable to directly get this information.

Example:

zeus2x4.vmem.E01 23:46:28> x = session.profile._EPROCESS(0x81e8a368)
zeus2x4.vmem.E01 23:46:32> encoder = json_renderer.JsonEncoder()
zeus2x4.vmem.E01 23:46:34> print encoder.Encode(x)
{'offset': 2179507048,
 'profile': ('*', u'nt/GUID/1B2D0DFE2FB942758D615C901BE046922'),
 'type': u'_EPROCESS,_EPROCESS,Struct,BaseAddressComparisonMixIn,BaseObject',
 'type_name': ('*', u'_EPROCESS'),
 'vm': {'base': {'filename': ('*',
    u'/home/scudette/images/zeus2x4.vmem.E01'),
   'type': u'EWFAddressSpace,CachingAddressSpaceMixIn,FDAddressSpace,BaseAddressSpace'},
  'dtb': 233472,
  'type': u'IA32PagedMemory,PagedReader,BaseAddressSpace'}}

zeus2x4.vmem.E01 23:47:25> decoder = json_renderer.JsonDecoder(session=session)
zeus2x4.vmem.E01 23:48:10> print decoder.Decode(encoder.Encode(x)).ImageFileName
alg.exe

Since the decoder is able to exactly recreate the original object, this object
can then be subsequently used to dereference the memory image - we can recover
the _EPROCESS.ImageFileName attribute and print the process name - even though
the actual name was never encoded.
"""
from rekall import addrspace
from rekall import obj
from rekall import session
from rekall import utils
from rekall.ui import json_renderer




class BaseAddressSpaceObjectRenderer(json_renderer.StateBasedObjectRenderer):
    renders_type = "BaseAddressSpace"

    @json_renderer.CacheableState
    def DecodeFromJsonSafe(self, value, options):
        value = super(BaseAddressSpaceObjectRenderer,
                      self).DecodeFromJsonSafe(value, options)

        cls_name = value.pop("cls")
        cls = addrspace.BaseAddressSpace.classes[cls_name]

        if value["base"] == "PhysicalAS":
            value["base"] = (self.session.physical_address_space or
                             self.session.plugins.load_as().GetPhysicalAddressSpace())

        return cls(session=self.session, **value)

    def GetState(self, item, **_):
        result = dict(cls=unicode(item.__class__.__name__))
        if item.base is not item:
            result["base"] = item.base

        if item.base is self.renderer.session.physical_address_space:
            result["base"] = "PhysicalAS"

        return result


class FileAddressSpaceObjectRenderer(BaseAddressSpaceObjectRenderer):
    renders_type = "FileAddressSpace"

    def GetState(self, item, **options):
        state = super(FileAddressSpaceObjectRenderer, self).GetState(
            item, **options)
        state["filename"] = utils.SmartUnicode(item.name)

        return state


class AttributeDictObjectRenderer(json_renderer.StateBasedObjectRenderer):
    renders_type = "AttributeDict"

    def GetState(self, item, **_):
        return dict(data=dict(item))

    def DecodeFromJsonSafe(self, state, options):
        state = super(AttributeDictObjectRenderer, self).DecodeFromJsonSafe(
            state, options)

        return utils.AttributeDict(state.get("data", {}))


class IA32PagedMemoryObjectRenderer(BaseAddressSpaceObjectRenderer):
    renders_type = "IA32PagedMemory"

    def GetState(self, item, **options):
        state = super(IA32PagedMemoryObjectRenderer, self).GetState(
            item, **options)
        state["dtb"] = item.dtb

        return state


class SessionObjectRenderer(json_renderer.StateBasedObjectRenderer):
    renders_type = "Session"

    def GetState(self, item, **options):
        state = super(SessionObjectRenderer, self).GetState(item, **options)
        state["session_id"] = item.session_id
        state_dict = state["state"] = {}
        for parameter, type in item.SERIALIZABLE_STATE_PARAMETERS:
            value = None
            if item.HasParameter(parameter):
                value = item.GetParameter(parameter)

            state_dict[parameter] = (value, type)

        return state

    @json_renderer.CacheableState
    def DecodeFromJsonSafe(self, state, options):
        state = super(SessionObjectRenderer, self).DecodeFromJsonSafe(
            state, options)

        mro = state["mro"].split(":")
        result = session.Session.classes[mro[0]]()
        with result:
            for k, v in state["state"].iteritems():
                result.SetParameter(k, v[0])

        return result


class ProfileObjectRenderer(json_renderer.StateBasedObjectRenderer):
    renders_type = "Profile"

    def GetState(self, item, **_):
        return dict(name=item.name)

    @json_renderer.CacheableState
    def DecodeFromJsonSafe(self, state, options):
        state = super(ProfileObjectRenderer, self).DecodeFromJsonSafe(
            state, options)

        return self.session.LoadProfile(state["name"])


class SetObjectRenderer(json_renderer.StateBasedObjectRenderer):
    """Encode a python set()."""
    renders_type = "set"

    def GetState(self, item, **_):
        return dict(data=list(item))

    def DecodeFromJsonSafe(self, state, options):
        return set(state["data"])


class NoneObjectRenderer(json_renderer.StateBasedObjectRenderer):
    """Encode a None Object."""
    renders_type = "NoneObject"

    def GetState(self, item, **_):
        return dict(reason=item.FormatReason())

    def DecodeFromJsonSafe(self, state, options):
        state = super(NoneObjectRenderer, self).DecodeFromJsonSafe(
            state, options)

        return obj.NoneObject(state.get("reason"))


class UnixTimestampJsonObjectRenderer(json_renderer.StateBasedObjectRenderer):
    renders_type = "UnixTimeStamp"

    def Summary(self, item, **_):
        return item.get("string_value", "")

    def GetState(self, item, **_):
        return dict(epoch=item.v(),
                    string_value=unicode(item))

    def DecodeFromJsonSafe(self, state, options):
        return self.session.profile.UnixTimeStamp(value=state.get("epoch", 0))


class PointerObjectRenderer(json_renderer.BaseObjectRenderer):
    """Encode a Pointer."""
    renders_type = "Pointer"

    def GetState(self, item, **options):
        state = super(PointerObjectRenderer, self).GetState(item, **options)
        state["target"] = item.target
        state["target_args"] = item.target_args

        return state


class ArrayObjectRenderer(PointerObjectRenderer):
    renders_type = "Array"

    def GetState(self, item, **options):
        state = super(ArrayObjectRenderer, self).GetState(item, **options)
        state["count"] = item.count

        return state


class JsonAttributedStringRenderer(json_renderer.StateBasedObjectRenderer):
    """Encode an attributed string."""
    renders_type = "AttributedString"

    def GetState(self, item, **options):
        state = super(JsonAttributedStringRenderer, self).GetState(
            item, **options)

        state["value"] = utils.SmartUnicode(item.value)
        state["highlights"] = item.highlights
        return state


class JsonHexdumpRenderer(json_renderer.StateBasedObjectRenderer):
    """Encode a hex dumped string."""
    renders_type = "HexDumpedString"

    def GetState(self, item, **options):
        state = super(JsonHexdumpRenderer, self).GetState(item, **options)
        state["value"] = " ".join(
            [unicode(x.encode("hex")) for x in item.value])

        state["translated"] = u".".join([
            x if ord(x) < 127 and ord(x) > 32 else "." for x in item.value])

        state["highlights"] = item.highlights

        return state


class JsonInstructionRenderer(json_renderer.StateBasedObjectRenderer):
    renders_type = "Instruction"

    def GetState(self, item, **_):
        return dict(value=unicode(item))


class JsonEnumerationRenderer(json_renderer.StateBasedObjectRenderer):
    """For enumerations store both their value and the enum name."""
    renders_type = ["Enumeration", "BitField"]

    def GetState(self, item, **_):
        return dict(enum=unicode(item),
                    value=int(item))

    def Summary(self, item, **_):
        return item.get("enum", "")


class JsonRangedCollectionObjectRenderer(
        json_renderer.StateBasedObjectRenderer):
    """Serialize RangedCollection objects."""
    renders_type = ["RangedCollection"]

    def EncodeToJsonSafe(self, item, **_):
        # Optimized this since we know we do not need to escape any item since
        # this is a simple list of integers.
        return dict(data=list(item.collection),
                    mro="RangedCollection")

    def DecodeFromJsonSafe(self, state, _):
        result = utils.RangedCollection()
        result.collection = utils.SortedCollection(state["data"])

        return result
