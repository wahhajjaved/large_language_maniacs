#!/usr/bin/python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2010             mk@mathias-kettner.de |
# +------------------------------------------------------------------+
#
# This file is part of Check_MK.
# The official homepage is at http://mathias-kettner.de/check_mk.
#
# check_mk is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# ails.  You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.

import views, time, defaults
from lib import *
import bi

# Python 2.3 does not have 'set' in normal namespace.
# But it can be imported from 'sets'
try:
    set()
except NameError:
    from sets import Set as set

def render_bi_groups():
    bi.html = html
    bi.compile_forest()
    html.write("<ul>")
    for group, trees in bi.g_aggregation_forest.items():
        if len(trees) > 0:
            bulletlink(group, "view.py?view_name=aggr_group&aggr_group=%s" % 
                    htmllib.urlencode(group))
    html.write("</ul>")

sidebar_snapins["biaggr_groups"] = {
    "title"       : "BI Aggregation Groups",
    "description" : "A direct link to all groups of BI aggregations",
    "author"      : "Mathias Kettner",
    "render"      : render_bi_groups,
    "allowed"     : [ "admin", "user", "guest" ]
}
