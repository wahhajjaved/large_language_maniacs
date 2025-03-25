#!/usr/bin/env python
# -*- coding: utf-8 -*-# 
# @(#)views.py
# 
# 
# Copyright (C) 2013, GC3, University of Zurich. All rights reserved.
# 
# 
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

__docformat__ = 'reStructuredText'

from django.http import HttpResponse

import sqlalchemy as sqla
from sqlalchemy.orm import sessionmaker

from beppegrillo.settings import SQLDB_OFFLINE_URI
from beppegrillo.sqlpipe import SqlComment, SqlDowngradedComment, SqlPost

def make_session():
    engine = sqla.create_engine(SQLDB_OFFLINE_URI)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session
    

def index(request):

    html = ["""
<html>
<head>
<style type="text/css">
th,
tr,
td { 
  border: 1px solid;
  vertical-align: top;
  padding: 1em;
}
</style>
</head>
<h1>Deleted comments (so far)</h1>
<table>
    <tr><th>date</th><th>votes</th><th>when disappeared</th><th>signature</th><th>comment</th><th>post</th></tr>
"""]
    try:
        session = make_session()
        desaparecidos = session.query(SqlComment).filter_by(desaparecido=True).all()
    except:
        # Something went wrong.
        desaparecidos = None
        html.append("no results found")

    for comment in desaparecidos:
        html.append("""
    <tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td><a href="%s">%s</a></td></tr>""" % (
            comment.posting_date.strftime("%d/%m/%Y, %H:%M"),
            comment.votes,
            comment.when_desaparecido.strftime("%d/%m/%Y, %H:%M"),
            comment.comment_signature,
            comment.comment_text,
            comment.post_url, comment.post_url,
            ))
    html.append("""
</table>
""")

    html.append("""
<h1>Downgraded comments</h1>
<table>
    <tr><th>posting date</th><th>current votes</th><th>votes before</th><th>votes after</th><th>signature</th><th>comment</th></tr>
""")
    downgraded = session.query(SqlComment, SqlDowngradedComment).join(SqlDowngradedComment, SqlDowngradedComment.comment_id==SqlComment.id)
    for comment in downgraded:
        if comment.SqlComment.votes <= comment.SqlDowngradedComment.old_votes:
            # If comment is not downgraded anymore, we should fix it.
            session.delete(comment.SqlDowngradedComment)
            session.commit()
            
        html.append("""
    <tr><td>%s</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td><a href="%s">%s</a></td></tr>""" % (
            comment.SqlComment.posting_date.strftime("%d/%m/%Y, %H:%M"),
            comment.SqlComment.votes,
            comment.SqlDowngradedComment.old_votes,
            comment.SqlDowngradedComment.cur_votes,
            comment.SqlComment.comment_signature,
            comment.SqlComment.comment_text,
            comment.SqlComment.post_url, comment.SqlComment.post_url,
            ))
    html.append("""
</table>
""")

    html.append("</html>")
    return HttpResponse(str.join('\n', html))
