# encoding: utf8
#
# (C) Copyright Arskom Ltd. <info@arskom.com.tr>
#               Uğurcan Ergün <ugurcanergn@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.
#

import logging
logger = logging.getLogger(__name__)

import os

from lxml import html
from sqlalchemy import sql

from spyne.util import reconstruct_url
from spynepi.util.pypi import cache_package

from pkg_resources import resource_filename

from sqlalchemy.orm.exc import NoResultFound

from spyne.decorator import rpc
from spyne.error import RequestNotAllowed
from spyne.model.binary import File
from spyne.model.complex import Array
from spyne.model.primitive import AnyUri
from spyne.model.primitive import Unicode
from spyne.protocol.html import HtmlPage
from spyne.protocol.http import HttpPattern
from spyne.service import ServiceBase

from spynepi.const import FILES_PATH
from spynepi.entity.project import Index
from spynepi.entity.project import Release
from spynepi.db import Package
from spynepi.db import Release

from lxml import html

TPL_DOWNLOAD = os.path.abspath(resource_filename("spynepi.const.template",
                                                               "download.html"))


class IndexService(ServiceBase):
    @rpc (_returns=Array(Index), _patterns=[HttpPattern("/",verb="GET")])
    def index(ctx):
        return [
            Index(
                Updated=package.package_cdate,
                Package=AnyUri.Value(
                    text=package.package_name,
                    href=package.latest_release.rdf_about
                ),
                Description=html.fromstring(package.package_description),
            ) for package in ctx.udc.session.query(Package)
        ]


class HtmlService(ServiceBase):
    @rpc(Unicode, Unicode, _returns=Unicode, _patterns=[
            HttpPattern("/<project_name>"),
            HttpPattern("/<project_name>/"),
            HttpPattern("/<project_name>/<version>"),
            HttpPattern("/<project_name>/<version>/"),
        ])
    def download_html(ctx, project_name, version):
        ctx.transport.mime_type = "text/html"
        own_url = reconstruct_url(ctx.transport.req_env,
                                                 path=False, query_string=False)
        try:
            ctx.udc.session.query(Package).filter_by(
                                                package_name=project_name).one()
        except NoResultFound:
            cache_package(project_name, own_url)

        download = HtmlPage(TPL_DOWNLOAD)
        download.title = project_name
        if version:
            release = ctx.udc.session.query(Release).join(Package).filter(
                sql.and_(
                    Package.package_name == project_name,
                    Release.release_version == version,
                )).one()

            if len(release.distributions) == 0:
                cache_package("%s==%s" % (project_name, version), own_url)
                ctx.udc.session.refresh(release)

            download.link.attrib["href"] = "%s/doap.rdf" % (release.rdf_about)
            download.h1 = '%s-%s' % (project_name, version)
            download.a = release.distributions[0].file_name
            download.a.attrib["href"] = "/files/%s/%s#md5=%s" % (
                    release.distributions[0].file_path,
                    release.distributions[0].file_name,
                    release.distributions[0].dist_md5,
                )

        else:
            package = ctx.udc.session.query(Package) \
                                     .filter_by(package_name=project_name).one()

            if len(package.latest_release.distributions) == 0:
                cache_package(project_name, own_url)
                ctx.udc.session.refresh(package)

            download = HtmlPage(TPL_DOWNLOAD)
            download.link.attrib["href"] = '%s/doap.rdf' % (package.latest_release.rdf_about)
            download.h1 = project_name
            download.a = package.latest_release.distributions[0].file_name
            download.a.attrib["href"] = "/%s/%s#md5=%s" % (
                    package.latest_release.distributions[0].file_path,
                    package.latest_release.distributions[0].file_name,
                    package.latest_release.distributions[0].dist_md5
                )

        return html.tostring(download.html)

    @rpc(Unicode, Unicode, Unicode, _returns=File, _patterns=[
                    HttpPattern("/files/<project_name>/<version>/<file_name>")])
    def download_file(ctx, project_name, version, file_name):
        repository_path = os.path.abspath(os.path.join(FILES_PATH,"files"))
        file_path = os.path.join(repository_path, project_name, version, file_name)
        file_path = os.path.abspath(file_path)

        if not file_path.startswith(repository_path):
            # This request tried to read data from where it's not supposed to
            raise RequestNotAllowed(repr([project_name, version, file_name]))

        return File.Value(name=file_name, path=file_path)
