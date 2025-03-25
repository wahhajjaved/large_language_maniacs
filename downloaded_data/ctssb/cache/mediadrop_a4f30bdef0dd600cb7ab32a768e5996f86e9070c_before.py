# This file is a part of MediaCore, Copyright 2009 Simple Station Inc.
#
# MediaCore is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# MediaCore is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Publicly Facing Media Controllers
"""
import os.path

from pylons import app_globals, config, request, response, session, tmpl_context
import webob.exc
from sqlalchemy import orm, sql
from paste.deploy.converters import asbool
from paste.util import mimeparse
from akismet import Akismet

from mediacore.lib.base import BaseController
from mediacore.lib.decorators import expose, expose_xhr, paginate, validate
from mediacore.lib.helpers import url_for, redirect, store_transient_message
from mediacore.model import (DBSession, fetch_row, get_available_slug,
    Media, MediaFile, Comment, Tag, Category, Author, AuthorWithIP, Podcast)
from mediacore.lib import helpers, email
from mediacore.forms.comments import PostCommentForm
from mediacore import USER_AGENT

import logging
log = logging.getLogger(__name__)

post_comment_form = PostCommentForm()

class MediaController(BaseController):
    """
    Media actions -- for both regular and podcast media
    """

    @expose('media/index.html')
    @paginate('media', items_per_page=20)
    def index(self, page=1, show='latest', q=None, tag=None, **kwargs):
        """List media with pagination.

        The media paginator may be accessed in the template with
        :attr:`c.paginators.media`, see :class:`webhelpers.paginate.Page`.

        :param page: Page number, defaults to 1.
        :type page: int
        :param show: 'latest', 'popular' or 'featured'
        :type show: unicode or None
        :param q: A search query to filter by
        :type q: unicode or None
        :param tag: A tag slug to filter for
        :type tag: unicode or None
        :rtype: dict
        :returns:
            media
                The list of :class:`~mediacore.model.media.Media` instances
                for this page.
            result_count
                The total number of media items for this query
            search_query
                The query the user searched for, if any

        """
        media = Media.query.published()\
            .options(orm.undefer('comment_count_published'))

        media, show = helpers.filter_library_controls(media, show)

        if q:
            media = media.search(q, bool=True)
        if tag:
            tag = fetch_row(Tag, slug=tag)
            media = media.filter(Media.tags.contains(tag))

        return dict(
            media = media,
            result_count = media.count(),
            search_query = q,
            show = show,
            tag = tag,
        )

    @expose('media/explore.html')
    @paginate('media', items_per_page=20)
    def explore(self, page=1, **kwargs):
        """Display the most recent 15 media.

        :rtype: Dict
        :returns:
            latest
                Latest media
            popular
                Latest media

        """
        media = Media.query.published()\
            .options(orm.undefer('comment_count_published'))

        latest = media.order_by(Media.publish_on.desc())
        popular = media.order_by(Media.popularity_points.desc())
        featured = None

        featured_cat = helpers.get_featured_category()
        if featured_cat:
            featured = latest.in_category(featured_cat).first()
        if not featured:
            featured = popular.first()

        latest = latest.exclude(featured)[:5]
        popular = popular.exclude(latest, featured)[:8]

        return dict(
            featured = featured,
            latest = latest,
            popular = popular,
        )

    @expose()
    def random(self, **kwargs):
        """Redirect to a randomly selected media item."""
        # TODO: Implement something more efficient than ORDER BY RAND().
        #       This method does a full table scan every time.
        media = Media.query.published()\
            .order_by(sql.func.random())\
            .first()
        if media is None:
            redirect(action='explore')
        if media.podcast_id:
            podcast_slug = DBSession.query(Podcast.slug).get(media.podcast_id)
        else:
            podcast_slug = None
        redirect(action='view', slug=media.slug, podcast_slug=podcast_slug)

    @expose('media/view.html')
    def view(self, slug, podcast_slug=None, **kwargs):
        """Display the media player, info and comments.

        :param slug: The :attr:`~mediacore.models.media.Media.slug` to lookup
        :param podcast_slug: The :attr:`~mediacore.models.podcasts.Podcast.slug`
            for podcast this media belongs to. Although not necessary for
            looking up the media, it tells us that the podcast slug was
            specified in the URL and therefore we reached this action by the
            preferred route.
        :rtype dict:
        :returns:
            media
                The :class:`~mediacore.model.media.Media` instance for display.
            comment_form
                The :class:`~mediacore.forms.comments.PostCommentForm` instance.
            comment_form_action
                ``str`` comment form action
            comment_form_values
                ``dict`` form values
            next_episode
                The next episode in the podcast series, if this media belongs to
                a podcast, another :class:`~mediacore.model.media.Media`
                instance.

        """
        media = fetch_row(Media, slug=slug)

        if media.podcast_id is not None:
            # Always view podcast media from a URL that shows the context of the podcast
            if url_for() != url_for(podcast_slug=media.podcast.slug):
                redirect(podcast_slug=media.podcast.slug)

        if media.fulltext:
            search_terms = '%s %s' % (media.title, media.fulltext.tags)
            related = Media.query.published()\
                .options(orm.undefer('comment_count_published'))\
                .filter(Media.id != media.id)\
                .search(search_terms, bool=False)
        else:
            related = []

        media.increment_views()

        return dict(
            media = media,
            related_media = related[:6],
            comments = media.comments.published().all(),
            comment_form = post_comment_form,
            comment_form_action = url_for(action='comment', anchor=post_comment_form.id),
            comment_form_values = kwargs,
        )

    @expose()
    def rate(self, slug, **kwargs):
        """Say 'I like this' for the given media.

        :param slug: The media :attr:`~mediacore.model.media.Media.slug`
        :rtype: unicode
        :returns:
            The new number of likes

        """
        media = fetch_row(Media, slug=slug)
        likes = media.increment_likes()
        DBSession.add(media)

        if request.is_xhr:
            return unicode(likes)
        else:
            redirect(action='view')

    @expose()
    @validate(post_comment_form, error_handler=view)
    def comment(self, slug, **values):
        """Post a comment from :class:`~mediacore.forms.comments.PostCommentForm`.

        :param slug: The media :attr:`~mediacore.model.media.Media.slug`
        :returns: Redirect to :meth:`view` page for media.

        """
        akismet_key = app_globals.settings['akismet_key']
        if akismet_key:
            akismet = Akismet(agent=USER_AGENT)
            akismet.key = akismet_key
            akismet.blog_url = app_globals.settings['akismet_url'] or \
                url_for('/', qualified=True)
            akismet.verify_key()
            data = {'comment_author': values['name'].encode('utf-8'),
                    'user_ip': request.environ.get('REMOTE_ADDR'),
                    'user_agent': request.environ.get('HTTP_USER_AGENT', ''),
                    'referrer': request.environ.get('HTTP_REFERER',  'unknown'),
                    'HTTP_ACCEPT': request.environ.get('HTTP_ACCEPT')}

            if akismet.comment_check(values['body'].encode('utf-8'), data):
                text = 'Your comment appears to be spam and has been rejected.'
                store_transient_message('comment_posted', text, success=False)
                redirect(action='view', anchor='comment-flash')

        media = fetch_row(Media, slug=slug)

        c = Comment()
        c.author = AuthorWithIP(
            values['name'], values['email'], request.environ['REMOTE_ADDR']
        )
        c.subject = 'Re: %s' % media.title
        c.body = values['body']

        require_review = asbool(app_globals.settings['req_comment_approval'])
        if not require_review:
            c.reviewed = True
            c.publishable = True

        media.comments.append(c)
        DBSession.add(media)
        email.send_comment_notification(media, c)

        if require_review:
            title = 'Thanks for your comment!'
            text = 'We will post it just as soon as a moderator approves it.'
            store_transient_message('comment_posted', text, title=title,
                success=True)
            redirect(action='view', anchor='comment-flash')
        else:
            redirect(action='view', anchor='comment-%s' % c.id)

    @expose()
    def serve(self, id, slug, container, **kwargs):
        """Serve a :class:`~mediacore.model.media.MediaFile` binary.

        :param id: File ID
        :type id: ``int``
        :param slug: The media :attr:`~mediacore.model.media.Media.slug`
        :type slug: The file :attr:`~mediacore.model.media.MediaFile.container`
        :raises webob.exc.HTTPNotFound: If no file exists for the given params.
        :raises webob.exc.HTTPNotAcceptable: If an Accept header field
            is present, and if the mimetype of the requested file doesn't
            match, then a 406 (not acceptable) response is returned.

        """
        media = fetch_row(Media, slug=slug)

        for file in media.files:
            if file.id == int(id) and file.container == container:
                # Catch external redirects in case they aren't linked to directly
                if file.url:
                    redirect(file.url.encode('utf-8'))
                elif file.embed:
                    redirect(file.link_url())

                # Ensure that the clients request allows for files of this container
                accept = request.environ.get('HTTP_ACCEPT', '*/*')
                mimetype = mimeparse.best_match([file.mimetype], accept)
                if mimetype == '':
                    raise webob.exc.HTTPNotAcceptable() # 406

                file_path = file.file_path
                file_hash = hash(file_path)
                file_size = os.path.getsize(file_path)
                file_mtime = os.path.getmtime(file_path)
                serve_method = config.get('file_serve_method', None)

                if serve_method == 'apache_xsendfile':
                    # Requires mod_xsendfile for Apache 2.x
                    response.headers['X-Sendfile'] = file_path.encode('utf-8')
                    response.body = ''
                elif serve_method == 'nginx_redirect':
                    # Placeholder for nginx's x-sendfile equivalent
                    raise NotImplementedError
                    response.headers['X-Accel-Redirect'] = '../relative/path'
                elif 'wsgi.file_wrapper' in request.environ:
                    # Take advantage of the file-serving mechanism provided
                    # by the server or gateway, if provided.
                    # http://www.python.org/dev/peps/pep-0333/#optional-platform-specific-file-handling
                    # http://code.google.com/p/modwsgi/wiki/FileWrapperExtension
                    file_wrapper = request.environ['wsgi.file_wrapper']
                    fileobj = open(file_path, 'rb')
                    chunk_size = 4096
                    response.app_iter = file_wrapper(fileobj, chunk_size)
                else:
                    # Fallback to iterating over the file and returning chunks
                    response.app_iter = FileIterable(file_path)

                response.headers['Content-Type'] = mimetype
                response.headers['Content-Disposition'] = 'attachment; '\
                    'filename="%s"' % file.display_name.encode('utf-8')
                response.content_length = file_size
                response.last_modified = file_mtime
                response.etag = '%s-%s-%s' % (file_mtime, file_size, file_hash)

                # Don't set response.body as it overrides response.app_iter
                return None
        else:
            raise webob.exc.HTTPNotFound()

class FileIterable(object):
    def __init__(self, filename, start=None, stop=None):
        self.filename = filename
        self.start = start
        self.stop = stop

    def __iter__(self):
        return FileIterator(self.filename, self.start, self.stop)

    def app_iter_range(self, start, stop):
        return self.__class__(self.filename, start, stop)

class FileIterator(object):
    chunk_size = 4096

    def __init__(self, filename, start, stop):
        self.filename = filename
        self.fileobj = open(self.filename, 'rb')
        if start:
            self.fileobj.seek(start)
        if stop is not None:
            self.length = stop - start
        else:
            self.length = None

    def __iter__(self):
        return self

    def next(self):
        if self.length is not None and self.length <= 0:
            self.close()
            raise StopIteration
        chunk = self.fileobj.read(self.chunk_size)
        if not chunk:
            self.close()
            raise StopIteration
        if self.length is not None:
            self.length -= len(chunk)
            if self.length < 0:
                # Chop off the extra:
                chunk = chunk[:self.length]
        return chunk

    def close(self):
        if self.fileobj:
            self.fileobj.close()
            self.fileobj = None
