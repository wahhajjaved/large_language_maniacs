# Miro - an RSS based video player application
# Copyright (C) 2005-2008 Participatory Culture Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the OpenSSL
# library.
#
# You must obey the GNU General Public License in all respects for all of
# the code used other than OpenSSL. If you modify file(s) with this
# exception, you may extend this exception to your version of the file(s),
# but you are not obligated to do so. If you do not wish to do so, delete
# this exception statement from your version. If you delete this exception
# statement from all source files in the program, then also delete it here.

"""Constants that define the look-and-feel."""

import datetime
import math

from miro import util
from miro import displaytext
from miro.gtcache import gettext as _
from miro.frontends.widgets import cellpack
from miro.frontends.widgets import imagepool
from miro.frontends.widgets import widgetutil
from miro.plat import resources
from miro.plat.frontends.widgets import widgetset

PI = math.pi

TAB_LIST_BACKGROUND_COLOR = (221/255.0, 227/255.0, 234/255.0)
TAB_LIST_HEADER_COLOR = (128/255.0, 137/255.0, 153/255.0)
TAB_LIST_SEPARATOR_COLOR = (209/255.0, 216/255.0, 220/255.0)

class TabRenderer(widgetset.CustomCellRenderer):
    MIN_WIDTH = 175
    MIN_HEIGHT = 25
    TITLE_FONT_SIZE = 0.82
    BOLD_TITLE = False
    UNWATCHED_BUBBLE_COLOR = (0.31, 0.75, 0.12)
    AVAILABLE_BUBBLE_COLOR = (0.60, 0.68, 0.80)

    def get_size(self, style, layout):
        return (self.MIN_WIDTH, max(self.MIN_HEIGHT,
            layout.font(self.TITLE_FONT_SIZE).line_height()))

    def render(self, context, layout, selected, hotspot):
        layout.set_text_color(context.style.text_color)
        layout.set_font(self.TITLE_FONT_SIZE, bold=self.BOLD_TITLE)
        titlebox = layout.textbox(self.data.name)

        hbox = cellpack.HBox(spacing=4)
        hbox.pack(cellpack.align_middle(self.data.icon))
        hbox.pack(cellpack.align_middle(cellpack.TruncatedTextLine(titlebox)), expand=True)
        layout.set_font(0.77)
        layout.set_text_color(widgetutil.WHITE)
        self.pack_bubbles(hbox, layout)
        alignment = cellpack.Alignment(hbox, yscale=0.0, yalign=0.5)
        alignment.render_layout(context)

    def pack_bubbles(self, hbox, layout):
        if self.data.unwatched > 0:
            self.pack_bubble(hbox, layout, self.data.unwatched,
                    self.UNWATCHED_BUBBLE_COLOR)
        if self.data.available > 0:
            self.pack_bubble(hbox, layout, self.data.available,
                    self.AVAILABLE_BUBBLE_COLOR)

    def pack_bubble(self, hbox, layout, count, color):
        radius = (layout.current_font.line_height() + 2) / 2.0
        background = cellpack.Background(layout.textbox(str(count)),
                margin=(1, radius, 1, radius))
        background.set_callback(self.draw_bubble, color)
        hbox.pack(cellpack.align_middle(background))

    def draw_bubble(self, context, x, y, width, height, color):
        radius = height / 2.0
        inner_width = width - radius * 2
        mid = y + radius

        context.move_to(x + radius, y)
        context.rel_line_to(inner_width, 0)
        context.arc(x + width - radius, mid, radius, -PI/2, PI/2)
        context.rel_line_to(-inner_width, 0)
        context.arc(x + radius, mid, radius, PI/2, -PI/2)
        context.set_color(color)
        context.fill()

class StaticTabRenderer(TabRenderer):
    BOLD_TITLE = True
    DOWNLOADING_BUBBLE_COLOR = (0.90, 0.45, 0.08)

    def pack_bubbles(self, hbox, layout):
        if self.data.unwatched > 0:
            self.pack_bubble(hbox, layout, self.data.unwatched,
                    self.UNWATCHED_BUBBLE_COLOR)
        if self.data.downloading > 0:
            self.pack_bubble(hbox, layout, self.data.downloading,
                    self.DOWNLOADING_BUBBLE_COLOR)

class FakeDownloadInfo(object):
    # Fake download info object used to size items
    def __init__(self):
        self.state = 'paused'
        self.rate = 0
        self.downloaded_size = 0

class ItemRenderer(widgetset.CustomCellRenderer):
    MIN_WIDTH = 600
    UNWATCHED_COLOR = (0.26, 0.71, 0.11)
    EXPIRING_COLOR = (0.95, 0.82, 0.11)
    BORDER_COLOR = (0.78, 0.78, 0.78)
    SELECTED_BACKGROUND_COLOR = (0.92, 0.95, 0.97)
    SELECTED_HIGHLIGHT_COLOR = (0.43, 0.63, 0.82)
    UNWATCHED_ITEM_TITLE_COLOR = (0.41, 0.70, 0.08)
    WATCHED_ITEM_TITLE_COLOR = (0.33, 0.33, 0.33)
    ITEM_DESC_COLOR = (0.4, 0.4, 0.4)
    EMBLEM_FONT_SIZE = 0.77
    GRADIENT_HEIGHT = 25

    def __init__(self):
        widgetset.CustomCellRenderer.__init__(self)
        self.progress_bar = imagepool.get_surface(resources.path(
            'wimages/progress-bar.png'))
        self.progress_bar_bg = imagepool.get_surface(resources.path(
            'wimages/progress-bar-bg.png'))
        self.cancel_button = imagepool.get_surface(resources.path(
            'wimages/video-download-cancel.png'))
        self.pause_button = imagepool.get_surface(resources.path(
            'wimages/video-download-pause.png'))
        self.resume_button = imagepool.get_surface(resources.path(
            'wimages/video-download-resume.png'))
        self.play_button = imagepool.get_surface(resources.path(
            'wimages/play-button.png'))
        self.play_button_pressed = imagepool.get_surface(resources.path(
            'wimages/play-button-pressed.png'))
        self.thumb_overlay = imagepool.get_surface(resources.path(
            'wimages/thumb-overlay-small.png'))
        self.thumb_overlay_large = imagepool.get_surface(resources.path(
            'wimages/thumb-overlay-large.png'))
        self.html_stripper = util.HTMLStripper()

    def get_thumbnail(self, info):
        try:
            return info.icon
        except AttributeError:
            info.icon = imagepool.get_surface(info.thumbnail, size=(154, 105))
            return info.icon

    def get_size(self, style, layout):
        # The right side of the cell is what's going to drive the height and
        # the right side is the tallest when we're downloading something.  So
        # use that to calculate the height.
        self.download_info = FakeDownloadInfo()
        self.setup_style(style)
        self.hotspot = None
        self.selected = False
        sizer = self.add_background(self.pack_right(layout))
        return self.MIN_WIDTH, max(140, sizer.get_size()[1])

    def hotspot_test(self, style, layout, x, y, width, height):
        self.download_info = self.data.download_info
        self.setup_style(style)
        self.hotspot = None
        self.selected = False
        packing = self.pack_all(layout)
        hotspot_info = packing.find_hotspot(x, y, width, height)
        if hotspot_info is None:
            return None
        hotspot, x, y, width, height = hotspot_info
        if hotspot == 'description':
            textbox = self.make_description(layout)
            textbox.set_width(width)
            index = textbox.char_at(x, y)
            if index is None:
                return None
            for (start, end, url) in self.description_links:
                if start <= index < end:
                    return 'description-link:%s' % url
            return None
        else:
            return hotspot

    def add_background(self, content):
        inner = cellpack.Background(content, margin=(10, 0, 15, 10))
        if self.use_custom_style:
            if self.selected:
                inner.set_callback(self.draw_background_selected)
            else:
                inner.set_callback(self.draw_background)
        return cellpack.Background(inner, margin=(5, 20, 5, 20))

    def make_description(self, layout):
        layout.set_font(0.85, family="Helvetica")
        layout.set_text_color(self.ITEM_DESC_COLOR)
        text, links = self.html_stripper.strip(self.data.description)
        textbox = layout.textbox("")
        pos = 0
        for start, end, url in links:
            textbox.append_text(text[pos:start])
            textbox.append_text(text[start:end], underline=True, color=self.ITEM_DESC_COLOR)
            pos = end
        if pos < len(text):
            textbox.append_text(text[pos:])
        self.description_links = links
        return textbox

    def pack_video_buttons(self, layout):
        hbox = cellpack.HBox(spacing=5)
        layout.set_font(0.77)
        if self.data.expiration_date:
            button = layout.button(_('Keep'), self.hotspot=='keep')
            button.set_min_width(65)
            hbox.pack(cellpack.Hotspot('keep', button))
        button = layout.button(_('Delete'), self.hotspot=='delete')
        button.set_min_width(65)
        hbox.pack(cellpack.Hotspot('delete', button))
        return hbox

    def pack_main(self, layout):
        layout.set_text_color(self.text_color)
        vbox = cellpack.VBox()
        layout.set_font(1.1, family="Helvetica", bold=True)
        if self.data.downloaded and not self.data.video_watched:
            layout.set_text_color(self.UNWATCHED_ITEM_TITLE_COLOR)
        else:
            layout.set_text_color(self.WATCHED_ITEM_TITLE_COLOR)
        title = layout.textbox(self.data.name)
        vbox.pack(cellpack.TruncatedTextLine(title, 150))
        description = cellpack.ClippedTextBox(self.make_description(layout))
        vbox.pack(cellpack.Hotspot('description', description), expand=True)
        if self.data.downloaded:
            vbox.pack_space(10)
            vbox.pack(self.pack_video_buttons(layout))
        return vbox

    def set_info_right_color(self, layout):
        if self.use_custom_style:
            layout.set_text_color((0.27, 0.27, 0.27))
        else:
            layout.set_text_color(self.text_color)

    def pack_info(self, layout):
        hbox = cellpack.HBox(spacing=10)
        layout.set_font(0.85)
        if self.use_custom_style:
            layout.set_text_color((0.66, 0.66, 0.66))
        else:
            layout.set_text_color(self.text_color)
        left_text = '\n'.join((_("Date:"), _("Length:"), _("Size:")))
        hbox.pack(layout.textbox(left_text))
        if self.data.duration > 0:
            duration = displaytext.time(self.data.duration)
        else:
            duration = ''
        layout.set_font(0.85, bold=True)
        self.set_info_right_color(layout)
        if self.data.release_date > datetime.datetime.min:
            release_date = self.data.release_date.strftime("%b %d %Y")
        else:
            release_date = ''
        right_text = '\n'.join((
                release_date,
                duration,
                displaytext.size(self.data.size)
            ))
        right_textbox = layout.textbox(right_text + "\n")
        right_textbox.append_text(_('Show Details'), underline=True)
        hbox.pack(right_textbox)
        return hbox

    def pack_emblem(self, layout):
        layout.set_font(0.77, bold=True)
        layout.set_text_color((1, 1, 1))
        if not self.data.video_watched:
            emblem_text = layout.textbox(_('Unwatched'))
            emblem_color = self.UNWATCHED_COLOR
        elif self.data.expiration_date:
            text = displaytext.expiration_date(self.data.expiration_date)
            emblem_text = layout.textbox(text)
            emblem_color = self.EXPIRING_COLOR
        else:
            return None
        emblem = cellpack.Background(emblem_text, margin=(4, 0, 4, 0))
        emblem.set_callback(self.draw_emblem, emblem_color)
        return emblem

    def download_textbox(self, layout):
        dl_info = self.download_info
        if dl_info.state == 'paused' or dl_info.rate == 0:
            layout.set_font(0.77, bold=True)
            self.set_info_right_color(layout)
            if dl_info.state == 'paused':
                return layout.textbox(_('paused'))
            else:
                return layout.textbox(dl_info.startup_activity)
        parts = []
        if self.data.size > 0:
            percent = round(100.0 * dl_info.downloaded_size / self.data.size)
            parts.append("%d%%" % percent)
        if dl_info.rate > 0:
            parts.append(displaytext.download_rate(dl_info.rate))
        if self.data.size > 0 and dl_info.rate > 0:
            bytes_left = self.data.size - dl_info.downloaded_size
            parts.append(displaytext.time(bytes_left / dl_info.rate))
        layout.set_font(0.77)
        layout.set_text_color(self.text_color)
        return layout.textbox(' - '.join(parts))

    def pack_download_status(self, layout):
        vbox = cellpack.VBox(spacing=5)
        vbox.pack(self.download_textbox(layout))
        hbox = cellpack.HBox(spacing=5)
        progress_bar = cellpack.DrawingArea(131, 9, self.draw_progress_bar)
        hbox.pack(cellpack.align_middle(progress_bar))
        if self.download_info.state != 'paused':
            hbox.pack(cellpack.Hotspot('pause', self.pause_button))
        else:
            hbox.pack(cellpack.Hotspot('resume', self.resume_button))
        hbox.pack(cellpack.Hotspot('cancel', self.cancel_button))
        vbox.pack(hbox)
        return vbox

    def pack_right(self, layout):
        vbox = cellpack.VBox()
        vbox.pack(self.pack_info(layout))

        if self.data.downloaded:
            extra = self.pack_emblem(layout)
        elif self.download_info is not None:
            extra = self.pack_download_status(layout)
        else:
            layout.set_font(0.77)
            if self.data.file_type == u'application/x-bittorrent':
                button = layout.button(_('Download Torrent'), self.hotspot=='download')
            else:
                button = layout.button(_('Download'), self.hotspot=='download')
            button.set_min_width(80)
            hotspot = cellpack.Hotspot('download', button)
            extra = cellpack.align_left(hotspot)
        if extra is None:
            return vbox
        outer_vbox = cellpack.VBox()
        outer_vbox.pack(cellpack.align_right(vbox))
        outer_vbox.pack_space(15, expand=True)
        outer_vbox.pack(extra)
        return outer_vbox

    def pack_all(self, layout):
        outer_hbox = cellpack.HBox()
        if self.data.downloaded:
            if self.hotspot == 'play':
                button = self.play_button_pressed
            else:
                button = self.play_button
            alignment = cellpack.Alignment(button, xscale=0, xalign=0.0, 
                    yscale=0, yalign=1.0)
            background = cellpack.Background(alignment, 154, 105)
            background.set_callback(self.draw_thumbnail)
            outer_hbox.pack(cellpack.Hotspot('play', background))
        else:
            outer_hbox.pack(cellpack.DrawingArea(154, 105, self.draw_thumbnail))
        inner_hbox = cellpack.HBox()
        status_bump = self.calc_status_bump(layout)
        if status_bump:
            inner_hbox.pack(status_bump)
        else:
            inner_hbox.pack_space(25)
        inner_hbox.pack(self.pack_main(layout), expand=True)
        inner_hbox.pack_space(25)
        inner_hbox.pack(self.pack_right(layout))
        outer_hbox.pack(cellpack.pad(inner_hbox, top=4), expand=True)
        return self.add_background(outer_hbox)

    def calc_status_bump(self, layout):
        bump = None
        if not self.data.item_viewed and not self.data.downloaded:
            bump = imagepool.get_surface(resources.path(
                'wimages/status-icon-new.png'))
        elif self.data.downloaded and not self.data.video_watched:
            bump = imagepool.get_surface(resources.path(
                'wimages/status-icon-newly-downloaded.png'))
        elif not self.data.downloaded and self.download_info is not None:
            bump = imagepool.get_surface(resources.path(
                'wimages/status-icon-downloading.png'))
        if bump is None:
            return None
        layout.set_font(1.1, family="Helvetica", bold=True)
        title_ascent = layout.current_font.ascent()
        return cellpack.DrawingArea(25, bump.height, self.draw_status_bump,
                bump, title_ascent)

    def draw_status_bump(self, context, x, y, width, height, bump,
            title_ascent):
        right = x + width - 6
        bottom = y + title_ascent
        bump.draw(context, right - bump.width, bottom - bump.height, 
                bump.width, bump.height)

    def setup_style(self, style):
        self.use_custom_style = style.use_custom_style
        if style.use_custom_style:
            self.text_color = (0, 0, 0)
        else:
            self.text_color = style.text_color

    def render(self, context, layout, selected, hotspot):
        self.download_info = self.data.download_info
        self.setup_style(context.style)
        self.hotspot = hotspot
        self.selected = selected
        packing = self.pack_all(layout)
        packing.render_layout(context)

    def make_border_path(self, context, x, y, width, height, inset):
        widgetutil.round_rect(context, x + inset, y + inset,
                width - inset*2, height - inset*2, 10)

    def draw_background(self, context, x, y, width, height):
        # Draw the gradient at the bottom
        self.make_border_path(context, x, y, width, height, 0)
        context.clip()
        top = y + height - self.GRADIENT_HEIGHT
        gradient = widgetset.Gradient(0, top, 0, top + self.GRADIENT_HEIGHT)
        bg_color = context.style.bg_color
        gradient.set_start_color(bg_color)
        gradient.set_end_color(tuple(c - 0.06 for c in bg_color))
        context.rectangle(x, top, width, self.GRADIENT_HEIGHT)
        context.gradient_fill(gradient)
        # Draw the border
        context.set_line_width(1)
        self.make_border_path(context, x, y, width, height, 0.5)
        context.set_color(self.BORDER_COLOR)
        context.stroke()
        # Draw the highlight
        self.make_border_path(context, x, y, width, height, 1.5)
        context.set_color(widgetutil.WHITE)
        context.stroke()

    def draw_background_selected(self, context, x, y, width, height):
        self.make_border_path(context, x, y, width, height, 0.5)
        context.set_color(self.SELECTED_BACKGROUND_COLOR)
        context.fill_preserve()
        context.set_line_width(3)
        context.set_color(self.SELECTED_HIGHLIGHT_COLOR)
        context.stroke()

    def draw_thumbnail(self, context, x, y, width, height):
        height = min(height, 105)
        thumbnail = self.get_thumbnail(self.data)
        if width != thumbnail.width or height != thumbnail.height:
            context.rectangle(x, y, width, height)
            context.set_color((0, 0, 0))
            context.fill()
            thumb_x = x + (width - thumbnail.width) / 2
            thumb_y = y + (height - thumbnail.height) / 2
        thumbnail.draw(context, thumb_x, thumb_y, 
                thumbnail.width, thumbnail.height)
        self.thumb_overlay.draw(context, x, y, width, height)

    def draw_emblem(self, context, x, y, width, height, color):
        radius = height / 2.0
        inner_width = width - radius
        if self.selected:
            inner_width -= 2
        context.move_to(x + radius, y)
        context.rel_line_to(inner_width, 0)
        context.rel_line_to(0, height)
        context.rel_line_to(-inner_width, 0)
        context.arc(x, y+radius, radius, PI/2, -PI/2)
        context.set_color(color)
        context.fill()

    def draw_progress_bar(self, context, x, y, width, height):
        dl_info = self.download_info
        split = float(width) * dl_info.downloaded_size / self.data.size
        self.progress_bar_bg.draw(context, x, y, width, height)
        self.progress_bar.draw(context, x, y, split, height)
