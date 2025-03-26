# Copyright (C) 2017-2018 DLR
#
# All rights reserved. This program and the accompanying materials are made
# available under the terms of the Eclipse Public License v1.0 which
# accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
# Franz Steinmetz <franz.steinmetz@dlr.de>
# Sebastian Brunner <sebastian.brunner@dlr.de>

import os
import sys
import shutil
import subprocess
import distutils.log

try:
    from gi.repository import Gtk
except ImportError:
    Gtk = None
try:
    from gi.repository import GLib
except ImportError:
    GLib = None

assets_folder = os.path.join('source', 'rafcon', 'gui', 'assets')
share_folder = "share"


def install_fonts(logger=None, restart=False):
    if logger:
        log = logger
    else:
        log = distutils.log
    if not Gtk:
        log.warn("No GTK found. Will not install fonts.")
        return

    tv = Gtk.TextView()
    try:
        context = tv.get_pango_context()
    except Exception as e:
        log.error("Could not get pango context. Will not install fonts: {}".format(e))
        return
    if not context:  # A Pango context is not always available
        log.warn("Could not get pango context. Will not install fonts.")
        return
    existing_fonts = context.list_families()
    existing_font_names = [font.get_name() for font in existing_fonts]

    user_otf_fonts_folder = os.path.join(os.path.expanduser('~'), '.fonts')

    font_installed = False
    try:
        for font_name in ["DIN Next LT Pro", "FontAwesome"]:
            if font_name in existing_font_names:
                log.debug("Font '{0}' found".format(font_name))
                continue

            log.info("Installing font '{0}' to {1}".format(font_name, user_otf_fonts_folder))
            if not os.path.isdir(user_otf_fonts_folder):
                os.makedirs(user_otf_fonts_folder)

            # A font is a folder one or more font faces
            fonts_folder = os.path.join(assets_folder, "fonts", font_name)
            for font_face in os.listdir(fonts_folder):
                target_font_file = os.path.join(user_otf_fonts_folder, font_face)
                source_font_file = os.path.join(fonts_folder, font_face)
                shutil.copy(source_font_file, target_font_file)
            font_installed = True
    except IOError as e:
        log.error("Could not install fonts, IOError: {}".format(e))
        return

    if font_installed:
        log.info("Running font detection ...")
        fail = subprocess.call(['fc-cache', '-fv', '"' + user_otf_fonts_folder + '"'])
        if fail:
            log.warn("Could not run font detection. RAFCON might not find the correct fonts.")
        if restart:
            log.info("Restarting RAFCON to apply new fonts...")
            python = sys.executable
            environ = dict(**os.environ)
            # Passing this to the new RAFCON environment will prevent further checks and thus restarts
            environ["RAFCON_CHECK_INSTALLATION"] = "False"
            args_and_env = list(sys.argv)
            args_and_env.append(environ)
            os.execle(python, python, *args_and_env)


def install_gtk_source_view_styles(logger=None):
    if logger:
        log = logger
    else:
        log = distutils.log
    if GLib:
        user_data_folder = GLib.get_user_data_dir()
    else:
        user_data_folder = os.path.join(os.path.expanduser('~'), '.local', 'share')
    user_source_view_style_path = os.path.join(user_data_folder, 'gtksourceview-2.0', 'styles')

    try:
        if not os.path.exists(user_source_view_style_path):
            os.makedirs(user_source_view_style_path)

        # Copy all .xml source view style files from all themes to local user styles folder
        themes_path = os.path.join(assets_folder, "share", "themes")
        for theme in os.listdir(themes_path):
            theme_source_view_path = os.path.join(themes_path, theme, "gtk-sourceview")
            if not os.path.isdir(theme_source_view_path):
                continue
            for style_filename in os.listdir(theme_source_view_path):
                if not style_filename.endswith(".xml"):
                    continue
                log.info("Installing GTKSourceView style '{}' to {}".format(style_filename, user_source_view_style_path))
                theme_source_view_style_path = os.path.join(theme_source_view_path, style_filename)
                shutil.copy(theme_source_view_style_path, user_source_view_style_path)
    except IOError as e:
        log.error("Could not install GTKSourceView style: {}".format(e))


def install_libraries(logger=None, overwrite=True):
    if logger:
        log = logger
    else:
        log = distutils.log
    if GLib:
        user_data_folder = GLib.get_user_data_dir()
    else:
        user_data_folder = os.path.join(os.path.expanduser('~'), '.local', 'share')
    user_library_path = os.path.join(user_data_folder, 'rafcon', 'libraries')
    library_path = os.path.join(share_folder, "libraries")

    if os.path.exists(user_library_path):
        if not overwrite:
            return
        try:
            log.info("Removing old RAFCON libraries in {}".format(user_library_path))
            shutil.rmtree(user_library_path)
        except (EnvironmentError, shutil.Error) as e:
            log.error("Could not remove old RAFCON libraries in {}: {}".format(user_library_path, e))
            return

    try:
        log.info("Installing RAFCON libraries to {}".format(user_library_path))
        shutil.copytree(library_path, user_library_path)
    except (IOError, shutil.Error) as e:
        log.error("Could not install RAFCON libraries: {}".format(e))


def create_mo_files():
    from os import path
    import subprocess
    data_files = []
    domain = "rafcon"
    localedir = path.join('source', 'rafcon', 'locale')
    po_files = [po_file
                for po_file in next(os.walk(localedir))[2]
                if path.splitext(po_file)[1] == '.po']
    for po_file in po_files:
        po_path = path.join(localedir, po_file)
        lang, extension = path.splitext(po_file)
        mo_file = domain + '.mo'
        mo_dir = path.join(localedir, lang, 'LC_MESSAGES')
        mo_path = path.join(mo_dir, mo_file)
        try:
            os.makedirs(mo_dir)
        except os.error:  # already exists
            pass
        msgfmt_cmd = 'msgfmt -o {} {}'.format(mo_path, po_path)
        result = subprocess.call(msgfmt_cmd, shell=True)
        if result == 0:  # Compilation successful
            # add po file
            target_dir = path.join("share", *localedir.split(os.sep)[1:])  # remove source/ (package_dir)
            data_files.append((target_dir, [os.path.join(localedir, po_file)]))
            # add mo file
            target_dir = path.join("share", *mo_dir.split(os.sep)[1:])  # remove source/ (package_dir)
            data_files.append((target_dir, [mo_path]))
        else:
            distutils.log.warn("Could not compile translation '{}'. RAFCON will not be available in this "
                               "language.".format(lang))

    return data_files
