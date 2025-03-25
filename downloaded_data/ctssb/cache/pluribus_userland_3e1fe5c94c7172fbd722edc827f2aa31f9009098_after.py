#!/usr/bin/python
#

#

#
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a generic packaging object

This module contains the Action class, which represents a generic packaging
object."""

from cStringIO import StringIO
import errno
import os
try:
        # Some versions of python don't have these constants.
        os.SEEK_SET
except AttributeError:
        os.SEEK_SET, os.SEEK_CUR, os.SEEK_END = range(3)
import pkg.actions
import pkg.client.api_errors as apx
import pkg.portable as portable
import pkg.variant as variant
import stat

class Action(object):
        """Class representing a generic packaging object.

        An Action is a very simple wrapper around two dictionaries: a named set
        of data streams and a set of attributes.  Data streams generally
        represent files on disk, and attributes represent metadata about those
        files.
        """

        __slots__ = ["attrs", "data", "ord"]

        # 'name' is the name of the action, as specified in a manifest.
        name = "generic"
        # 'key_attr' is the name of the attribute whose value must be unique in
        # the namespace of objects represented by a particular action.  For
        # instance, a file's key_attr would be its pathname.  Or a driver's
        # key_attr would be the driver name.  When 'key_attr' is None, it means
        # that all attributes of the action are distinguishing.
        key_attr = None
        # 'globally_unique' is True if the key attribute of the action
        # represents a key which must be unique in the space of all installed
        # actions of that type.
        globally_unique = False

        # the following establishes the sort order between action types.
        # Directories must precede all
        # filesystem-modifying actions; hardlinks must follow all
        # filesystem-modifying actions.  Note that usr/group actions
        # precede file actions; this implies that /etc/group and /etc/passwd
        # file ownership needs to be part of initial contents of those files
        orderdict = {}
        unknown = 0

        def loadorderdict(self):
                ol = [
                        "set",
                        "depend",
                        "group",
                        "user",
                        "dir",
                        "file",
                        "hardlink",
                        "link",
                        "driver",
                        "unknown",
                        "legacy",
                        "signature"
                        ]
                self.orderdict.update(dict((
                    (pkg.actions.types[t], i) for i, t in enumerate(ol)
                    )))
                self.__class__.unknown = \
                    self.orderdict[pkg.actions.types["unknown"]]

        def __init__(self, data=None, **attrs):
                """Action constructor.

                The optional 'data' argument may be either a string, a file-like
                object, or a callable.  If it is a string, then it will be
                substituted with a callable that will return an open handle to
                the file represented by the string.  Otherwise, if it is not
                already a callable, it is assumed to be a file-like object, and
                will be substituted with a callable that will return the object.
                If it is a callable, it will not be replaced at all.

                Any remaining named arguments will be treated as attributes.
                """

                if not self.orderdict:
                        self.loadorderdict()
                self.ord = self.orderdict.get(type(self), self.unknown)

                self.attrs = attrs

                # Since this is a hot path, avoid a function call unless
                # absolutely necessary.
                if data is None:
                        self.data = None
                else:
                        self.set_data(data)

        def set_data(self, data):
                """This function sets the data field of the action.

                The "data" parameter is the file to use to set the data field.
                It can be a string which is the path to the file, a function
                which provides the file when called, or a file handle to the
                file."""

                if data is None:
                        self.data = None
                        return

                if isinstance(data, basestring):
                        if not os.path.exists(data):
                                raise pkg.actions.ActionDataError(
                                    _("No such file: '%s'.") % data, path=data)
                        elif os.path.isdir(data):
                                raise pkg.actions.ActionDataError(
                                    _("'%s' is not a file.") % data, path=data)

                        def file_opener():
                                return open(data, "rb")
                        self.data = file_opener
                        if "pkg.size" not in self.attrs:
                                try:
                                        fs = os.stat(data)
                                        self.attrs["pkg.size"] = str(fs.st_size)
                                except EnvironmentError, e:
                                        raise \
                                            pkg.actions.ActionDataError(
                                            e, path=data)
                        return

                if callable(data):
                        # Data is not None, and is callable.
                        self.data = data
                        return

                if "pkg.size" in self.attrs:
                        self.data = lambda: data
                        return

                try:
                        sz = data.size
                except AttributeError:
                        try:
                                try:
                                        sz = os.fstat(data.fileno()).st_size
                                except (AttributeError, TypeError):
                                        try:
                                                try:
                                                        data.seek(0,
                                                            os.SEEK_END)
                                                        sz = data.tell()
                                                        data.seek(0)
                                                except (AttributeError,
                                                    TypeError):
                                                        d = data.read()
                                                        sz = len(d)
                                                        data = StringIO(d)
                                        except (AttributeError, TypeError):
                                                # Raw data was provided; fake a
                                                # file object.
                                                sz = len(data)
                                                data = StringIO(data)
                        except EnvironmentError, e:
                                raise pkg.actions.ActionDataError(e)

                self.attrs["pkg.size"] = str(sz)
                self.data = lambda: data

        def __str__(self):
                """Serialize the action into manifest form.

                The form is the name, followed by the hash, if it exists,
                followed by attributes in the form 'key=value'.  All fields are
                space-separated; fields with spaces in the values are quoted.

                Note that an object with a datastream may have been created in
                such a way that the hash field is not populated, or not
                populated with real data.  The action classes do not guarantee
                that at the time that __str__() is called, the hash is properly
                computed.  This may need to be done externally.
                """

                out = self.name
                if hasattr(self, "hash"):
                        out += " " + self.hash

                def q(s):
                        if " " in s or "'" in s or "\"" in s or s == "":
                                if "\"" not in s:
                                        return '"%s"' % s
                                elif "'" not in s:
                                        return "'%s'" % s
                                else:
                                        return '"%s"' % s.replace("\"", "\\\"")
                        else:
                                return s

                # Sort so that we get consistent action attribute ordering.
                # We pay a performance penalty to do so, but it seems worth it.
                for k in sorted(self.attrs.keys()):
                        v = self.attrs[k]
                        if isinstance(v, list) or isinstance(v, set):
                                out += " " + " ".join([
                                    "%s=%s" % (k, q(lmt)) for lmt in v
                                ])
                        elif " " in v or "'" in v or "\"" in v or v == "":
                                if "\"" not in v:
                                        out += " " + k + "=\"" + v + "\""
                                elif "'" not in v:
                                        out += " " + k + "='" + v + "'"
                                else:
                                        out += " " + k + "=\"" + v.replace("\"", "\\\"") + "\""
                        else:
                                out += " " + k + "=" + v

                return out

        def __cmp__(self, other):
                """Compare actions for ordering.  The ordinality of a
                   given action is computed and stored at action
                   initialization."""
                if not isinstance(other, Action):
                        return NotImplemented

                res = cmp(self.ord, other.ord)

                if res == 0:
                        return self.compare(other) # often subclassed

                return res

        def compare(self, other):
                return cmp(id(self), id(other))

        def different(self, other):
                """Returns True if other represents a non-ignorable change from
                self.

                By default, this means two actions are different if any of their
                attributes are different.  Subclasses should override this
                behavior when appropriate.
                """

                # We could ignore key_attr, or possibly assert that it's the
                # same.
                sset = set(self.attrs.keys())
                oset = set(other.attrs.keys())
                if sset.symmetric_difference(oset):
                        return True

                for a in self.attrs:
                        x = self.attrs[a]
                        y = other.attrs[a]
                        if isinstance(x, list) and \
                            isinstance(y, list):
                                if sorted(x) != sorted(y):
                                        return True
                        elif x != y:
                                return True

                if hasattr(self, "hash"):
                        assert(hasattr(other, "hash"))
                        if self.hash != other.hash:
                                return True

                return False

        def differences(self, other):
                """Returns a list of attributes that have different values
                between other and self"""
                sset = set(self.attrs.keys())
                oset = set(other.attrs.keys())
                l = list(sset.symmetric_difference(oset))
                for k in sset & oset: # over attrs in both dicts
                        if isinstance(self.attrs[k], list) and \
                            isinstance(other.attrs[k], list):
                                if sorted(self.attrs[k]) != sorted(other.attrs[k]):
                                        l.append(k)
                        elif self.attrs[k] != other.attrs[k]:
                                l.append(k)
                return (l)

        def consolidate_attrs(self):
                """Removes duplicate values from values which are lists."""
                for k in self.attrs.iterkeys():
                        if isinstance(self.attrs[k], list):
                                self.attrs[k] = list(set(self.attrs[k]))

        def generate_indices(self):
                """Generate the information needed to index this action.

                This method, and the overriding methods in subclasses, produce
                a list of four-tuples.  The tuples are of the form
                (action_name, key, token, full value).  action_name is the
                string representation of the kind of action generating the
                tuple.  'file' and 'depend' are two examples.  It is required to
                not be None.  Key is the string representation of the name of
                the attribute being indexed.  Examples include 'basename' and
                'path'.  Token is the token to be searched against.  Full value
                is the value to display to the user in the event this token
                matches their query.  This is useful for things like categories
                where what matched the query may be a substring of what the
                desired user output is.
                """

                if hasattr(self, "hash"):
                        return [
                            (self.name, "content", self.hash, self.hash),
                        ]
                return []

        def distinguished_name(self):
                """ Return the distinguishing name for this action,
                    preceded by the type of the distinguishing name.  For
                    example, for a file action, 'path' might be the
                    key_attr.  So, the distinguished name might be
                    "path: usr/lib/libc.so.1".
                """

                if self.key_attr is None:
                        return str(self)
                return "%s: %s" % \
                    (self.name, self.attrs.get(self.key_attr, "???"))

        def makedirs(self, path, **kw):
                """Make directory specified by 'path' with given permissions, as
                well as all missing parent directories.  Permissions are
                specified by the keyword arguments 'mode', 'uid', and 'gid'.

                The difference between this and os.makedirs() is that the
                permissions specify only those of the leaf directory.  Missing
                parent directories inherit the permissions of the deepest
                existing directory.  The leaf directory will also inherit any
                permissions not explicitly set."""

                # generate the components of the path.  The first
                # element will be empty since all absolute paths
                # always start with a root specifier.
                pathlist = portable.split_path(path)

                # Fill in the first path with the root of the filesystem
                # (this ends up being something like C:\ on windows systems,
                # and "/" on unix.
                pathlist[0] = portable.get_root(path)

                g = enumerate(pathlist)
                for i, e in g:
                        # os.path.isdir() follows links, which isn't
                        # desirable here.
                        p = os.path.join(*pathlist[:i + 1])
                        try:
                                fs = os.lstat(p)
                        except OSError, e:
                                if e.errno == errno.ENOENT:
                                        break
                                raise

                        if not stat.S_ISDIR(fs.st_mode):
                                if p == path:
                                        # Allow caller to handle target by
                                        # letting the operation continue,
                                        # and whatever error is encountered
                                        # being raised to the caller.
                                        break

                                err_txt = _("Unable to create %(path)s; a "
                                    "parent directory %(p)s has been replaced "
                                    "with a file or link.  Please restore the "
                                    "parent directory and try again.") % \
                                    locals()
                                raise apx.ActionExecutionError(self,
                                    details=err_txt, error=e,
                                    fmri=kw.get("fmri", None))
                else:
                        # XXX Because the filelist codepath may create
                        # directories with incorrect permissions (see
                        # pkgtarfile.py), we need to correct those permissions
                        # here.  Note that this solution relies on all
                        # intermediate directories being explicitly created by
                        # the packaging system; otherwise intermediate
                        # directories will not get their permissions corrected.
                        fs = os.lstat(path)
                        mode = kw.get("mode", fs.st_mode)
                        uid = kw.get("uid", fs.st_uid)
                        gid = kw.get("gid", fs.st_gid)
                        try:
                                if mode != fs.st_mode:
                                        os.chmod(path, mode)
                                if uid != fs.st_uid or gid != fs.st_gid:
                                        portable.chown(path, uid, gid)
                        except  OSError, e:
                                if e.errno != errno.EPERM and \
                                    e.errno != errno.ENOSYS:
                                        raise
                        return

                fs = os.stat(os.path.join(*pathlist[:i]))
                for i, e in g:
                        p = os.path.join(*pathlist[:i])
                        try:
                                os.mkdir(p, fs.st_mode)
                        except OSError, e:
                                if e.ernno != errno.ENOTDIR:
                                        raise
                                err_txt = _("Unable to create %(path)s; a "
                                    "parent directory %(p)s has been replaced "
                                    "with a file or link.  Please restore the "
                                    "parent directory and try again.") % \
                                    locals()
                                raise apx.ActionExecutionError(self,
                                    details=err_txt, error=e,
                                    fmri=kw.get("fmri", None))

                        os.chmod(p, fs.st_mode)
                        try:
                                portable.chown(p, fs.st_uid, fs.st_gid)
                        except OSError, e:
                                if e.errno != errno.EPERM:
                                        raise

                # Create the leaf with any requested permissions, substituting
                # missing perms with the parent's perms.
                mode = kw.get("mode", fs.st_mode)
                uid = kw.get("uid", fs.st_uid)
                gid = kw.get("gid", fs.st_gid)
                os.mkdir(path, mode)
                os.chmod(path, mode)
                try:
                        portable.chown(path, uid, gid)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def get_varcet_keys(self):
                """Return the names of any facet or variant tags in this
                action."""

                variants = []
                facets = []

                for k in self.attrs.iterkeys():
                        if k.startswith("variant."):
                                variants.append(k)
                        if k.startswith("facet."):
                                facets.append(k)
                return variants, facets

        def get_variants(self):
                return variant.VariantSets(dict((
                    (v, self.attrs[v]) for v in self.get_varcet_keys()[0]
                )))

        def strip_variants(self):
                """Remove all variant tags from the attrs dictionary."""

                for k in self.attrs.keys():
                        if k.startswith("variant."):
                                del self.attrs[k]

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""
                return [], [], []

        def validate_fsobj_common(self, fmri=None):
                """Common validation logic for filesystem objects."""

                errors = []

                bad_mode = False
                raw_mode = self.attrs.get("mode", None)
                if not raw_mode:
                        bad_mode = True
                else:
                        mlen = len(raw_mode)
                        # Common case for our packages is 4 so place that first.
                        if not (mlen == 4 or mlen == 3 or mlen == 5):
                                bad_mode = True
                        elif mlen == 5 and raw_mode[0] != "0":
                                bad_mode = True

                # The group, mode, and owner attributes are intentionally only
                # required during publication as it is anticipated that the
                # there will eventually be defaults for these (possibly parent
                # directory, etc.).  By only requiring these attributes here,
                # it prevents publication of packages for which no default
                # currently exists, while permitting future changes to remove
                # that limitaiton and use sane defaults.
                if not bad_mode:
                        try:
                                mode = str(int(raw_mode, 8))
                        except (TypeError, ValueError):
                                bad_mode = True
                        else:
                                bad_mode = mode == ""

                if bad_mode:
                        if not raw_mode:
                                errors.append(("mode", _("mode is required; "
                                    "value must be of the form '644', "
                                    "'0644', or '04755'.")))
                        else:
                                errors.append(("mode", _("'%s' is not a valid "
                                    "mode; value must be of the form '644', "
                                    "'0644', or '04755'.") % raw_mode))

                owner = self.attrs.get("owner", "").rstrip()
                if not owner:
                        errors.append(("owner", _("owner is required")))

                group = self.attrs.get("group", "").rstrip()
                if not group:
                        errors.append(("group", _("group is required")))

                if errors:
                        raise pkg.actions.InvalidActionAttributesError(self,
                            errors, fmri=fmri)

        def get_fsobj_uid_gid(self, pkgplan, fmri):
                """Returns a tuple of the form (owner, group) containing the uid
                and gid of the filesystem object.  If the attributes are missing
                or invalid, an InvalidActionAttributesError exception will be
                raised."""

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                # The attribute may be missing.
                owner = self.attrs.get("owner", "").rstrip()

                # Now attempt to determine the uid and raise an appropriate
                # exception if it can't be.
                try:
                        owner = pkgplan.image.get_user_by_name(owner)
                except KeyError:
                        if not owner:
                                # Owner was missing; let validate raise a more
                                # informative error.
                                self.validate(fmri=fmri)

                        # Otherwise, the user is unknown; attempt to report why.
                        ip = pkgplan.image.imageplan
                        if owner in ip.removed_users:
                                # What package owned the user that was removed?
                                src_fmri = ip.removed_users[owner]

                                raise pkg.actions.InvalidActionAttributesError(
                                    self, [("owner", _("'%(path)s' cannot be "
                                    "installed; the owner '%(owner)s' was "
                                    "removed by '%(src_fmri)s'.") % {
                                    "path": path, "owner": owner,
                                    "src_fmri": src_fmri })],
                                    fmri=fmri)
                        elif owner in ip.added_users:
                                # This indicates an error on the part of the
                                # caller; the user should have been added
                                # before attempting to install the file.
                                raise

                        # If this spot was reached, the user wasn't part of
                        # the operation plan and is completely unknown or
                        # invalid.
                        raise pkg.actions.InvalidActionAttributesError(
                            self, [("owner", _("'%(path)s' cannot be "
                                    "installed; '%(owner)s' is an unknown "
                                    "or invalid user.") % { "path": path,
                                    "owner": owner })],
                                    fmri=fmri)

                # The attribute may be missing.
                group = self.attrs.get("group", "").rstrip()

                # Now attempt to determine the gid and raise an appropriate
                # exception if it can't be.
                try:
                        group = pkgplan.image.get_group_by_name(group)
                except KeyError:
                        if not group:
                                # Group was missing; let validate raise a more
                                # informative error.
                                self.validate(fmri=pkgplan.destination_fmri)

                        # Otherwise, the group is unknown; attempt to report
                        # why.
                        ip = pkgplan.image.imageplan
                        if group in ip.removed_groups:
                                # What package owned the group that was removed?
                                src_fmri = ip.removed_groups[group]

                                raise pkg.actions.InvalidActionAttributesError(
                                    self, [("group", _("'%(path)s' cannot be "
                                    "installed; the group '%(group)s' was "
                                    "removed by '%(src_fmri)s'.") % {
                                    "path": path, "group": group,
                                    "src_fmri": src_fmri })],
                                    fmri=pkgplan.destination_fmri)
                        elif group in ip.added_groups:
                                # This indicates an error on the part of the
                                # caller; the group should have been added
                                # before attempting to install the file.
                                raise

                        # If this spot was reached, the group wasn't part of
                        # the operation plan and is completely unknown or
                        # invalid.
                        raise pkg.actions.InvalidActionAttributesError(
                            self, [("group", _("'%(path)s' cannot be "
                                    "installed; '%(group)s' is an unknown "
                                    "or invalid group.") % { "path": path,
                                    "group": group })],
                                    fmri=pkgplan.destination_fmri)

                return owner, group

        def verify_fsobj_common(self, img, ftype):
                """Common verify logic for filesystem objects."""

                errors = []
                warnings = []
                info = []

                abort = False
                def ftype_to_name(ftype):
                        assert ftype is not None
                        tmap = {
                                stat.S_IFIFO: "fifo",
                                stat.S_IFCHR: "character device",
                                stat.S_IFDIR: "directory",
                                stat.S_IFBLK: "block device",
                                stat.S_IFREG: "regular file",
                                stat.S_IFLNK: "symbolic link",
                                stat.S_IFSOCK: "socket",
                        }
                        if ftype in tmap:
                                return tmap[ftype]
                        else:
                                return "Unknown (0x%x)" % ftype

                mode = owner = group = None
                if "mode" in self.attrs:
                        mode = int(self.attrs["mode"], 8)
                if "owner" in self.attrs:
                        owner = self.attrs["owner"]
                        try:
                                owner = img.get_user_by_name(owner)
                        except KeyError:
                                errors.append(_("Owner: %s is unknown") % owner)
                                owner = None
                if "group" in self.attrs:
                        group = self.attrs["group"]
                        try:
                                group = img.get_group_by_name(group)
                        except KeyError:
                                errors.append(_("Group: %s is unknown ") %
                                    group)
                                group = None

                path = os.path.normpath(
                    os.path.sep.join((img.get_root(), self.attrs["path"])))

                lstat = None
                try:
                        lstat = os.lstat(path)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                errors.append(_("Missing: %s does not exist") %
                                    ftype_to_name(ftype))
                        elif e.errno == errno.EACCES:
                                errors.append(_("Skipping: Permission denied"))
                        else:
                                errors.append(_("Unexpected Error: %s") % e)
                        abort = True

                if abort:
                        return lstat, errors, warnings, info, abort

                if ftype is not None and ftype != stat.S_IFMT(lstat.st_mode):
                        errors.append(_("File Type: '%(found)s' should be "
                            "'%(expected)s'") % {
                            "found": ftype_to_name(stat.S_IFMT(lstat.st_mode)),
                            "expected": ftype_to_name(ftype) })
                        abort = True

                if owner is not None and lstat.st_uid != owner:
                        errors.append(_("Owner: '%(found_name)s "
                            "(%(found_id)d)' should be '%(expected_name)s "
                            "(%(expected_id)d)'") % {
                            "found_name": img.get_name_by_uid(lstat.st_uid,
                            True), "found_id": lstat.st_uid,
                            "expected_name": self.attrs["owner"],
                            "expected_id": owner })

                if group is not None and lstat.st_gid != group:
                        errors.append(_("Group: '%(found_name)s "
                            "(%(found_id)s)' should be '%(expected_name)s "
                            "(%(expected_id)s)'") % {
                            "found_name": img.get_name_by_gid(lstat.st_gid,
                            True), "found_id": lstat.st_gid,
                            "expected_name": self.attrs["group"],
                            "expected_id": group })

                if mode is not None and stat.S_IMODE(lstat.st_mode) != mode:
                        errors.append(_("Mode: 0%(found).3o should be "
                            "0%(expected).3o") % {
                            "found": stat.S_IMODE(lstat.st_mode),
                            "expected": mode })
                return lstat, errors, warnings, info, abort

        def needsdata(self, orig, pkgplan):
                """Returns True if the action transition requires a
                datastream."""
                return False

        def attrlist(self, name):
                """return list containing value of named attribute."""
                value = self.attrs.get(name, [])
                if isinstance(value, list):
                        return value
                else:
                        return [ value ]

        def directory_references(self):
                """Returns references to paths in action."""
                if "path" in self.attrs:
                        return [os.path.dirname(os.path.normpath(
                            self.attrs["path"]))]
                return []

        def preinstall(self, pkgplan, orig):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self, pkgplan, orig):
                """Client-side method that installs the object."""
                pass

        def postinstall(self, pkgplan, orig):
                """Client-side method that performs post-install actions."""
                pass

        def preremove(self, pkgplan):
                """Client-side method that performs pre-remove actions."""
                pass

        def remove(self, pkgplan):
                """Client-side method that removes the object."""
                pass

        def remove_fsobj(self, pkgplan, path):
                """Shared logic for removing file and link objects."""

                # Necessary since removal logic is reused by install.
                fmri = pkgplan.destination_fmri
                if not fmri:
                        fmri = pkgplan.origin_fmri

                try:
                        portable.remove(path)
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                # Already gone; don't care.
                                return
                        elif e.errno == errno.EBUSY and os.path.ismount(path):
                                # User has replaced item with mountpoint, or a
                                # package has been poorly implemented.
                                err_txt = _("Unable to remove %s; it is in use "
                                    "as a mountpoint.  To continue, please "
                                    "unmount the filesystem at the target "
                                    "location and try again.") % path
                                raise apx.ActionExecutionError(self,
                                    details=err_txt, error=e, fmri=fmri)
                        elif e.errno == errno.EBUSY:
                                # os.path.ismount() is broken for lofs
                                # filesystems, so give a more generic
                                # error.
                                err_txt = _("Unable to remove %s; it is in "
                                    "use by the system, another process, or "
                                    "as a mountpoint.") % path
                                raise apx.ActionExecutionError(self,
                                    details=err_txt, error=e, fmri=fmri)
                        elif e.errno == errno.EPERM and \
                            not stat.S_ISDIR(os.lstat(path).st_mode):
                                # Was expecting a directory in this failure
                                # case, it is not, so raise the error.
                                raise
                        elif e.errno in (errno.EACCES, errno.EROFS):
                                # Raise these permissions exceptions as-is.
                                raise
                        elif e.errno != errno.EPERM:
                                # An unexpected error.
                                raise apx.ActionExecutionError(self, error=e,
                                    fmri=fmri)

                        # Attempting to remove a directory as performed above
                        # gives EPERM.  First, try to remove the directory,
                        # if it isn't empty, salvage it.
                        try:
                                os.rmdir(path)
                        except OSError, e:
                                if e.errno in (errno.EPERM, errno.EACCES):
                                        # Raise permissions exceptions as-is.
                                        raise
                                elif e.errno not in (errno.EEXIST,
                                    errno.ENOTEMPTY):
                                        # An unexpected error.
                                        raise apx.ActionExecutionError(self,
                                            error=e, fmri=fmri)

                                pkgplan.image.salvage(path)

        def postremove(self, pkgplan):
                """Client-side method that performs post-remove actions."""
                pass

        def include_this(self, excludes):
                """Callables in excludes list returns True
                if action is to be included, False if
                not"""
                for c in excludes:
                        if not c(self):
                                return False
                return True

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action."""
                pass

        def fsobj_checkpath(self, pkgplan, final_path):
                """Verifies that the specified path doesn't contain one or more
                symlinks relative to the image root.  Raises an
                ActionExecutionError exception if path check fails."""

                valid_dirs = pkgplan.image.imageplan.valid_directories
                parent_path = os.path.dirname(final_path)
                if parent_path in valid_dirs:
                        return

                real_parent_path = os.path.realpath(parent_path)
                if parent_path == real_parent_path:
                        valid_dirs.add(parent_path)
                        return

                fmri = pkgplan.destination_fmri

                # Now test each component of the parent path until one is found
                # to be a link.  When found, that's the parent that has been
                # redirected to some other location.
                idx = 0
                while idx < len(parent_path) and parent_path[idx] == os.path.sep:
                        idx += 1
                tmp = parent_path[idx-1:]
                if pkgplan.image.root != os.path.sep:
                        img_root = pkgplan.image.root.rstrip(os.path.sep)
                else:
                        img_root = pkgplan.image.root
                while 1:
                        if tmp == img_root:
                                # No parent directories up to the root were
                                # found to be links, so assume this is ok.
                                valid_dirs.add(parent_path)
                                return

                        if os.path.islink(tmp):
                                # We've found the parent that changed locations.
                                break
                        # Drop the final component.
                        tmp = os.path.split(tmp)[0]

                parent_dir = tmp
                parent_target = os.path.realpath(parent_dir)
                err_txt = _("Cannot install '%(final_path)s'; parent directory "
                    "%(parent_dir)s is a link to %(parent_target)s.  To "
                    "continue, move the directory to its original location and "
                    "try again.") % locals() 
                raise apx.ActionExecutionError(self, details=err_txt,
                    fmri=fmri)
