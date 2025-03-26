# -*- coding: utf-8 -*-

# Copyright © 2012-2014 Roberto Alsina and others.

# Permission is hereby granted, free of charge, to any
# person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the
# Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice
# shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals
import io
import datetime
import glob
import json
import mimetypes
import os
import sys
try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin  # NOQA

import natsort
Image = None
try:
    from PIL import Image  # NOQA
except ImportError:
    try:
        import Image as _Image
        Image = _Image
    except ImportError:
        pass

import PyRSS2Gen as rss

from nikola.plugin_categories import Task
from nikola import utils
from nikola.image_processing import ImageProcessor
from nikola.post import Post
from nikola.utils import req_missing

_image_size_cache = {}


class Galleries(Task, ImageProcessor):
    """Render image galleries."""

    name = 'render_galleries'
    dates = {}

    def set_site(self, site):
        site.register_path_handler('gallery', self.gallery_path)
        site.register_path_handler('gallery_rss', self.gallery_rss_path)

        self.logger = utils.get_logger('render_galleries', site.loghandlers)

        self.kw = {
            'thumbnail_size': site.config['THUMBNAIL_SIZE'],
            'max_image_size': site.config['MAX_IMAGE_SIZE'],
            'output_folder': site.config['OUTPUT_FOLDER'],
            'cache_folder': site.config['CACHE_FOLDER'],
            'default_lang': site.config['DEFAULT_LANG'],
            'use_filename_as_title': site.config['USE_FILENAME_AS_TITLE'],
            'gallery_folders': site.config['GALLERY_FOLDERS'],
            'sort_by_date': site.config['GALLERY_SORT_BY_DATE'],
            'filters': site.config['FILTERS'],
            'translations': site.config['TRANSLATIONS'],
            'global_context': site.GLOBAL_CONTEXT,
            'feed_length': site.config['FEED_LENGTH'],
            'tzinfo': site.tzinfo,
            'comments_in_galleries': site.config['COMMENTS_IN_GALLERIES'],
            'generate_rss': site.config['GENERATE_RSS'],
        }

        # Verify that no folder in GALLERY_FOLDERS appears twice
        appearing_paths = set()
        for source, dest in self.kw['gallery_folders'].items():
            if source in appearing_paths or dest in appearing_paths:
                problem = source if source in appearing_paths else dest
                utils.LOGGER.error("The gallery input or output folder '{0}' appears in more than one entry in GALLERY_FOLDERS, exiting.".format(problem))
                sys.exit(1)
            appearing_paths.add(source)
            appearing_paths.add(dest)

        # Find all galleries we need to process
        self.find_galleries()
        # Create self.gallery_links
        self.create_galleries_paths()

        return super(Galleries, self).set_site(site)

    def _find_gallery_path(self, name):
        # The system using self.proper_gallery_links and self.improper_gallery_links
        # is similar as in listings.py.
        if name in self.proper_gallery_links:
            return self.proper_gallery_links[name]
        elif name in self.improper_gallery_links:
            candidates = self.improper_gallery_links[name]
            if len(candidates) == 1:
                return candidates[0]
            self.logger.error("Gallery name '{0}' is not unique! Possible output paths: {1}".format(name, candidates))
        else:
            self.logger.error("Unknown gallery '{0}'!".format(name))
            self.logger.info("Known galleries: " + str(list(self.proper_gallery_links.keys())))
        sys.exit(1)

    def gallery_path(self, name, lang):
        gallery_path = self._find_gallery_path(name)
        return [_f for _f in [self.site.config['TRANSLATIONS'][lang]] +
                list(os.path.split(gallery_path)) +
                [self.site.config['INDEX_FILE']] if _f]

    def gallery_rss_path(self, name, lang):
        gallery_path = self._find_gallery_path(name)
        return [_f for _f in [self.site.config['TRANSLATIONS'][lang]] +
                list(os.path.split(gallery_path)) +
                ['rss.xml'] if _f]

    def gen_tasks(self):
        """Render image galleries."""

        if Image is None:
            req_missing(['pillow'], 'render galleries')

        self.image_ext_list = self.image_ext_list_builtin
        self.image_ext_list.extend(self.site.config.get('EXTRA_IMAGE_EXTENSIONS', []))

        for k, v in self.site.GLOBAL_CONTEXT['template_hooks'].items():
            self.kw['||template_hooks|{0}||'.format(k)] = v._items

        yield self.group_task()

        template_name = "gallery.tmpl"

        # Create all output folders
        for task in self.create_galleries():
            yield task

        # For each gallery:
        for gallery, input_folder, output_folder in self.gallery_list:

            # Create subfolder list
            folder_list = [(x, x.split(os.sep)[-2]) for x in
                           glob.glob(os.path.join(gallery, '*') + os.sep)]

            # Parse index into a post (with translations)
            post = self.parse_index(gallery, input_folder, output_folder)

            # Create image list, filter exclusions
            image_list = self.get_image_list(gallery)

            # Sort as needed
            # Sort by date
            if self.kw['sort_by_date']:
                image_list.sort(key=lambda a: self.image_date(a))
            else:  # Sort by name
                image_list.sort()

            # Create thumbnails and large images in destination
            for image in image_list:
                for task in self.create_target_images(image, input_folder):
                    yield task

            # Remove excluded images
            for image in self.get_excluded_images(gallery):
                for task in self.remove_excluded_image(image, input_folder):
                    yield task

            crumbs = utils.get_crumbs(gallery, index_folder=self)

            # Create index.html for each language
            for lang in self.kw['translations']:
                # save navigation links as dependencies
                self.kw['navigation_links|{0}'.format(lang)] = self.kw['global_context']['navigation_links'](lang)

                dst = os.path.join(
                    self.kw['output_folder'],
                    self.site.path("gallery", gallery, lang))
                dst = os.path.normpath(dst)

                for k in self.site._GLOBAL_CONTEXT_TRANSLATABLE:
                    self.kw[k] = self.site.GLOBAL_CONTEXT[k](lang)

                context = {}
                context["lang"] = lang
                if post:
                    context["title"] = post.title(lang)
                else:
                    context["title"] = os.path.basename(gallery)
                context["description"] = None

                image_name_list = [os.path.basename(p) for p in image_list]

                if self.kw['use_filename_as_title']:
                    img_titles = []
                    for fn in image_name_list:
                        name_without_ext = os.path.splitext(os.path.basename(fn))[0]
                        img_titles.append(utils.unslugify(name_without_ext))
                else:
                    img_titles = [''] * len(image_name_list)

                thumbs = ['.thumbnail'.join(os.path.splitext(p)) for p in image_list]
                thumbs = [os.path.join(self.kw['output_folder'], output_folder, os.path.relpath(t, input_folder)) for t in thumbs]
                dst_img_list = [os.path.join(output_folder, os.path.relpath(t, input_folder)) for t in image_list]
                dest_img_list = [os.path.join(self.kw['output_folder'], t) for t in dst_img_list]

                folders = []

                # Generate friendly gallery names
                for path, folder in folder_list:
                    fpost = self.parse_index(path, input_folder, output_folder)
                    if fpost:
                        ft = fpost.title(lang) or folder
                    else:
                        ft = folder
                    if not folder.endswith('/'):
                        folder += '/'
                    folders.append((folder, ft))

                context["folders"] = natsort.natsorted(folders)
                context["crumbs"] = crumbs
                context["permalink"] = self.site.link("gallery", gallery, lang)
                context["enable_comments"] = self.kw['comments_in_galleries']
                context["thumbnail_size"] = self.kw["thumbnail_size"]

                if post:
                    yield {
                        'basename': self.name,
                        'name': post.translated_base_path(lang),
                        'targets': [post.translated_base_path(lang)],
                        'file_dep': post.fragment_deps(lang),
                        'actions': [(post.compile, [lang])],
                        'uptodate': [utils.config_changed(self.kw, 'nikola.plugins.task.galleries:post')] + post.fragment_deps_uptodate(lang)
                    }
                    context['post'] = post
                else:
                    context['post'] = None
                file_dep = self.site.template_system.template_deps(
                    template_name) + image_list + thumbs
                if post:
                    file_dep += [post.translated_base_path(l) for l in self.kw['translations']]

                yield utils.apply_filters({
                    'basename': self.name,
                    'name': dst,
                    'file_dep': file_dep,
                    'targets': [dst],
                    'actions': [
                        (self.render_gallery_index, (
                            template_name,
                            dst,
                            context,
                            dest_img_list,
                            img_titles,
                            thumbs,
                            file_dep))],
                    'clean': True,
                    'uptodate': [utils.config_changed({
                        1: self.kw,
                        2: self.site.config["COMMENTS_IN_GALLERIES"],
                        3: context.copy(),
                    }, 'nikola.plugins.task.galleries:gallery')],
                }, self.kw['filters'])

                # RSS for the gallery
                if self.kw["generate_rss"]:
                    rss_dst = os.path.join(
                        self.kw['output_folder'],
                        self.site.path("gallery_rss", gallery, lang))
                    rss_dst = os.path.normpath(rss_dst)

                    yield utils.apply_filters({
                        'basename': self.name,
                        'name': rss_dst,
                        'file_dep': file_dep,
                        'targets': [rss_dst],
                        'actions': [
                            (self.gallery_rss, (
                                image_list,
                                dst_img_list,
                                img_titles,
                                lang,
                                self.site.link("gallery_rss", gallery, lang),
                                rss_dst,
                                context['title']
                            ))],
                        'clean': True,
                        'uptodate': [utils.config_changed({
                            1: self.kw,
                        }, 'nikola.plugins.task.galleries:rss')],
                    }, self.kw['filters'])

    def find_galleries(self):
        """Find all galleries to be processed according to conf.py"""

        self.gallery_list = []
        for input_folder, output_folder in self.kw['gallery_folders'].items():
            for root, dirs, files in os.walk(input_folder, followlinks=True):
                self.gallery_list.append((root, input_folder, output_folder))

    def create_galleries_paths(self):
        """Given a list of galleries, puts their paths into self.gallery_links."""

        # gallery_path is "gallery/foo/name"
        self.proper_gallery_links = dict()
        self.improper_gallery_links = dict()
        for gallery_path, input_folder, output_folder in self.gallery_list:
            if gallery_path == input_folder:
                gallery_name = ''
                # special case, because relpath will return '.' in this case
            else:
                gallery_name = os.path.relpath(gallery_path, input_folder)

            output_path = os.path.join(output_folder, gallery_name)
            self.proper_gallery_links[gallery_path] = output_path
            self.proper_gallery_links[output_path] = output_path

            # If the input and output names differ, the gallery is accessible
            # only by `input` and `output/`.
            output_path_noslash = output_path[:-1]
            if output_path_noslash not in self.proper_gallery_links:
                self.proper_gallery_links[output_path_noslash] = output_path

            gallery_path_slash = gallery_path + '/'
            if gallery_path_slash not in self.proper_gallery_links:
                self.proper_gallery_links[gallery_path_slash] = output_path

            if gallery_name not in self.improper_gallery_links:
                self.improper_gallery_links[gallery_name] = list()
            self.improper_gallery_links[gallery_name].append(output_path)

    def create_galleries(self):
        """Given a list of galleries, create the output folders."""

        # gallery_path is "gallery/foo/name"
        for gallery_path, input_folder, _ in self.gallery_list:
            # have to use dirname because site.path returns .../index.html
            output_gallery = os.path.dirname(
                os.path.join(
                    self.kw["output_folder"],
                    self.site.path("gallery", gallery_path)))
            output_gallery = os.path.normpath(output_gallery)
            # Task to create gallery in output/
            yield {
                'basename': self.name,
                'name': output_gallery,
                'actions': [(utils.makedirs, (output_gallery,))],
                'targets': [output_gallery],
                'clean': True,
                'uptodate': [utils.config_changed(self.kw, 'nikola.plugins.task.galleries:mkdir')],
            }

    def parse_index(self, gallery, input_folder, output_folder):
        """Returns a Post object if there is an index.txt."""

        index_path = os.path.join(gallery, "index.txt")
        destination = os.path.join(
            self.kw["output_folder"], output_folder,
            os.path.relpath(gallery, input_folder))
        if os.path.isfile(index_path):
            post = Post(
                index_path,
                self.site.config,
                destination,
                False,
                self.site.MESSAGES,
                'story.tmpl',
                self.site.get_compiler(index_path)
            )
            # If this did not exist, galleries without a title in the
            # index.txt file would be errorneously named `index`
            # (warning: galleries titled index and filenamed differently
            #  may break)
            if post.title == 'index':
                post.title = os.path.split(gallery)[1]
        else:
            post = None
        return post

    def get_excluded_images(self, gallery_path):
        exclude_path = os.path.join(gallery_path, "exclude.meta")

        try:
            f = open(exclude_path, 'r')
            excluded_image_name_list = f.read().split()
        except IOError:
            excluded_image_name_list = []

        excluded_image_list = ["{0}/{1}".format(gallery_path, i) for i in excluded_image_name_list]
        return excluded_image_list

    def get_image_list(self, gallery_path):

        # Gather image_list contains "gallery/name/image_name.jpg"
        image_list = []

        for ext in self.image_ext_list:
            image_list += glob.glob(gallery_path + '/*' + ext.lower()) +\
                glob.glob(gallery_path + '/*' + ext.upper())

        # Filter ignored images
        excluded_image_list = self.get_excluded_images(gallery_path)
        image_set = set(image_list) - set(excluded_image_list)
        image_list = list(image_set)
        return image_list

    def create_target_images(self, img, input_path):
        gallery_name = os.path.dirname(img)
        output_gallery = os.path.dirname(
            os.path.join(
                self.kw["output_folder"],
                self.site.path("gallery", gallery_name)))
        # Do thumbnails and copy originals
        # img is "galleries/name/image_name.jpg"
        # img_name is "image_name.jpg"
        # fname, ext are "image_name", ".jpg"
        # thumb_path is
        # "output/GALLERY_PATH/name/image_name.thumbnail.jpg"
        img_name = os.path.basename(img)
        fname, ext = os.path.splitext(img_name)
        thumb_path = os.path.join(
            output_gallery,
            ".thumbnail".join([fname, ext]))
        # thumb_path is "output/GALLERY_PATH/name/image_name.jpg"
        orig_dest_path = os.path.join(output_gallery, img_name)
        yield utils.apply_filters({
            'basename': self.name,
            'name': thumb_path,
            'file_dep': [img],
            'targets': [thumb_path],
            'actions': [
                (self.resize_image,
                    (img, thumb_path, self.kw['thumbnail_size']))
            ],
            'clean': True,
            'uptodate': [utils.config_changed({
                1: self.kw['thumbnail_size']
            }, 'nikola.plugins.task.galleries:resize_thumb')],
        }, self.kw['filters'])

        yield utils.apply_filters({
            'basename': self.name,
            'name': orig_dest_path,
            'file_dep': [img],
            'targets': [orig_dest_path],
            'actions': [
                (self.resize_image,
                    (img, orig_dest_path, self.kw['max_image_size']))
            ],
            'clean': True,
            'uptodate': [utils.config_changed({
                1: self.kw['max_image_size']
            }, 'nikola.plugins.task.galleries:resize_max')],
        }, self.kw['filters'])

    def remove_excluded_image(self, img, input_folder):
        # Remove excluded images
        # img is something like input_folder/demo/tesla2_lg.jpg so it's the *source* path
        # and we should remove both the large and thumbnail *destination* paths

        output_folder = os.path.dirname(
            os.path.join(
                self.kw["output_folder"],
                self.site.path("gallery", os.path.dirname(img))))
        img = os.path.relpath(img, input_folder)
        img_path = os.path.join(output_folder, os.path.basename(img))
        fname, ext = os.path.splitext(img_path)
        thumb_path = fname + '.thumbnail' + ext

        yield utils.apply_filters({
            'basename': '_render_galleries_clean',
            'name': thumb_path,
            'actions': [
                (utils.remove_file, (thumb_path,))
            ],
            'clean': True,
            'uptodate': [utils.config_changed(self.kw, 'nikola.plugins.task.galleries:clean_thumb')],
        }, self.kw['filters'])

        yield utils.apply_filters({
            'basename': '_render_galleries_clean',
            'name': img_path,
            'actions': [
                (utils.remove_file, (img_path,))
            ],
            'clean': True,
            'uptodate': [utils.config_changed(self.kw, 'nikola.plugins.task.galleries:clean_file')],
        }, self.kw['filters'])

    def render_gallery_index(
            self,
            template_name,
            output_name,
            context,
            img_list,
            img_titles,
            thumbs,
            file_dep):
        """Build the gallery index."""

        # The photo array needs to be created here, because
        # it relies on thumbnails already being created on
        # output

        def url_from_path(p):
            url = '/'.join(os.path.relpath(p, os.path.dirname(output_name) + os.sep).split(os.sep))
            return url

        photo_array = []
        for img, thumb, title in zip(img_list, thumbs, img_titles):
            w, h = _image_size_cache.get(thumb, (None, None))
            if w is None:
                im = Image.open(thumb)
                w, h = im.size
                _image_size_cache[thumb] = w, h
            # Thumbs are files in output, we need URLs
            photo_array.append({
                'url': url_from_path(img),
                'url_thumb': url_from_path(thumb),
                'title': title,
                'size': {
                    'w': w,
                    'h': h
                },
            })
        context['photo_array'] = photo_array
        context['photo_array_json'] = json.dumps(photo_array)
        self.site.render_template(template_name, output_name, context)

    def gallery_rss(self, img_list, dest_img_list, img_titles, lang, permalink, output_path, title):
        """Create a RSS showing the latest images in the gallery.

        This doesn't use generic_rss_renderer because it
        doesn't involve Post objects.
        """

        def make_url(url):
            return urljoin(self.site.config['BASE_URL'], url.lstrip('/'))

        items = []
        for img, srcimg, title in list(zip(dest_img_list, img_list, img_titles))[:self.kw["feed_length"]]:
            img_size = os.stat(
                os.path.join(
                    self.site.config['OUTPUT_FOLDER'], img)).st_size
            args = {
                'title': title,
                'link': make_url(img),
                'guid': rss.Guid(img, False),
                'pubDate': self.image_date(srcimg),
                'enclosure': rss.Enclosure(
                    make_url(img),
                    img_size,
                    mimetypes.guess_type(img)[0]
                ),
            }
            items.append(rss.RSSItem(**args))
        rss_obj = rss.RSS2(
            title=title,
            link=make_url(permalink),
            description='',
            lastBuildDate=datetime.datetime.now(),
            items=items,
            generator='http://getnikola.com/',
            language=lang
        )

        rss_obj.rss_attrs["xmlns:dc"] = "http://purl.org/dc/elements/1.1/"
        rss_obj.self_url = make_url(permalink)
        rss_obj.rss_attrs["xmlns:atom"] = "http://www.w3.org/2005/Atom"
        dst_dir = os.path.dirname(output_path)
        utils.makedirs(dst_dir)
        with io.open(output_path, "w+", encoding="utf-8") as rss_file:
            data = rss_obj.to_xml(encoding='utf-8')
            if isinstance(data, utils.bytes_str):
                data = data.decode('utf-8')
            rss_file.write(data)
