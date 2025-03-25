#!/usr/bin/env python3
from datetime import datetime, timezone
import locale
import os.path
from urllib.request import urlopen

from bs4 import BeautifulSoup

from gi.repository import Gtk, GdkPixbuf, GLib

tracked_projects = ['playroom/killer-bunnies-quest-deluxe',
                    'hiddenpath/defense-grid-2',
                    'ouya/ouya-a-new-kind-of-video-game-console',
                    '597507018/pebble-e-paper-watch-for-iphone-and-android',
                   ]

class TrackerWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self)
        self.set_default_size(400, 100)
        icon_path = os.path.join(os.path.split(__file__)[0], 'favicon.ico')
        self.set_default_icon(GdkPixbuf.Pixbuf.new_from_file(icon_path))

        notebook = Gtk.Notebook()
        active_scroll = Gtk.ScrolledWindow()
        complete_scroll = Gtk.ScrolledWindow()
        self.active = Gtk.VBox()
        self.complete = Gtk.VBox()

        for project in tracked_projects:
            url = 'http://www.kickstarter.com/projects/{0}'.format(project)
            proj_box = ProjectBox(url)
            if proj_box.end_date > datetime.now(timezone.utc):
                self.active.pack_start(proj_box, False, False, 0)
            else:
                proj_box.left.set_text('Done!')
                self.complete.pack_start(proj_box, False, False, 0)

        GLib.timeout_add(30000, refresh, self.active)
        active_scroll.add_with_viewport(self.active)
        complete_scroll.add_with_viewport(self.complete)
        notebook.append_page(active_scroll, Gtk.Label('Acive Projects'))
        notebook.append_page(complete_scroll, Gtk.Label('Completed Projects'))
        self.add(notebook)


class ProjectBox(Gtk.VBox):
    def __init__(self, url):
        Gtk.VBox.__init__(self)
        metadata = project_scrape(url)
        linkbar = Gtk.HBox()

        self.title = Gtk.LinkButton(url, metadata['title'])
        linkbar.pack_start(self.title, True, True, 0)

        self.updates = Gtk.LinkButton(url + '/posts', metadata['updates'])
        linkbar.pack_start(self.updates, False, False, 0)
        self.add(linkbar)

        self.progress = Gtk.ProgressBar()
        self.progress.set_fraction(metadata['percent_raised'])
        self.add(self.progress)

        details = Gtk.HBox()

        self.pledged = Gtk.Label(metadata['pledged'])
        details.add(self.pledged)

        self.percent = Gtk.Label(metadata['pretty_percent'])
        details.add(self.percent)

        self.end_date = metadata['end_date']
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.left = Gtk.Label(str(self.end_date - now))
        details.add(self.left)

        self.add(details)


def project_scrape(url):
    raw_html = urlopen(url)
    soup = BeautifulSoup(raw_html)
    pledge_div = soup.find('div', {'id': 'pledged'})
    time_div = soup.find('span', {'id': 'project_duration_data'})

    metadata = dict()
    metadata['title'] = soup.find('h1', {'id': 'title'}).a.string
    percent_raised = float(pledge_div['data-percent-raised'])
    metadata['percent_raised'] = min(percent_raised, 1.0)
    metadata['pretty_percent'] = '%.2f%%' % (percent_raised * 100)
    metadata['pledged'] = locale.currency(float(pledge_div['data-pledged']),
                                          grouping=True)
    metadata['end_date'] = datetime.strptime(time_div['data-end_time'],
                                             '%a, %d %b %Y %H:%M:%S %z')
    updates = soup.find('span', {'id': 'updates_count'})
    metadata['updates'] = int(updates['data-updates-count'])

    return metadata


def refresh(container):
    """
    Refresh the contents of the projects.

    @param container: The VBox full of ProjBox to update.

    @return True.  This is to keep timeout rescheduling the callback.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)

    for widget in container.get_children():
        metadata = project_scrape(widget.title.get_uri())
        widget.progress.set_fraction(min(1.0, metadata['percent_raised']))
        widget.pledged.set_text(metadata['pledged'])
        widget.percent.set_text(metadata['pretty_percent'])
        if widget.end_date > now:
            widget.left.set_text(str(widget.end_date - now))
        else:
            widget.left.set_text('Done!')
            win.complete.pack_start(widget, False, False, 0)
            container.remove(widget)

    # Keep going.
    return True


if __name__ == '__main__':
    win = TrackerWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
