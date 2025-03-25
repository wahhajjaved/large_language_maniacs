from plugins.plugin_base import PluginBase
import pychromecast
import logging


def get_available_settings():
    return ['name']


def get_type():
    return ChromecastDevice


def auto_detect(current_plugins):
    current_names = [device.get_setting('name') for device in current_plugins]

    chromecasts = pychromecast.get_chromecasts()

    new_casts = [cast for cast in chromecasts if
                 len([name for name in current_names if name == cast.device.friendly_name]) < 1]

    return [{'settings': {'name': cast.device.friendly_name}, 'title': 'Chromecast %s' % cast.device.friendly_name}
            for cast in new_casts]


class ChromecastStatusSubscriber:
    def __init__(self, cast_name):
        self._cast_name = cast_name
        self._trigger = None

    def start(self, trigger):
        self._trigger = trigger

        chromecasts = pychromecast.get_chromecasts()

        cast = next(cc for cc in chromecasts if cc.device.friendly_name == self._cast_name)

        cast.wait()

        logging.info('Setting up status listener for cast "%s"' % cast.device.friendly_name)

        cast.media_controller.register_status_listener(self)

    def stop(self):
        self._trigger = None

    def new_media_status(self, new_status):
        logging.info('Cast "%s" status updated (%s)' % (self._cast_name, str(new_status)))

        if self._trigger is not None:
            self._trigger(new_status.__dict__)


class ChromecastDevice(PluginBase):
    def __init__(self, plugin_id, settings_manager):
        super().__init__(plugin_id, settings_manager, default_state={'current_states': {'is_playing': False}})

        self.cast = None

    def _get_cast(self):
        if self.cast is not None:
            return self.cast

        chromecasts = pychromecast.get_chromecasts()

        name = self._get_setting('name')

        self.cast = next(cc for cc in chromecasts if cc.device.friendly_name == name)

        self.cast.wait()

        return self.cast

    def pause(self):
        self._get_cast().media_controller.pause()

    def play(self):
        self._get_cast().media_controller.play()

    def play_media(self, media, media_type):
        self._get_cast().media_controller.play_media(media, media_type)

    def update_status(self):
        new_status = self._get_cast().media_controller.status

        is_playing = new_status.player_is_playing or new_status.player_is_paused
        name = self._get_setting('name')

        logging.info('Chromecast "%s" updated playing status to %s' % (name, str(is_playing)))

        if is_playing != self._state['current_states']['is_playing']:
            if is_playing:
                self._apply('cast_started_casting', {'name': name})
            else:
                self._apply('cast_stopped_casting', {'name': name})

    def get_status(self):
        return self._get_cast().media_controller.status.__dict__

    def get_automations(self):
        return [{
            'definition': {'initial_step': {
                'id': 'update_chromecast_status_for_%s' % self._get_setting('name'),
                'type': '.workflows.steps.execute_plugin_command',
                'plugin_id': self._plugin_id,
                'command': 'update_status',
                'parameters': {}
            }},
            'triggers': [{'type': '.workflows.triggers.background_task_trigger',
                          'task': 'plugins.entertainment.chromecast.ChromecastStatusSubscriber',
                          'parameters': {
                              'cast_name': self._get_setting('name')
                          }}]
        }]

    def _on_cast_started_casting(self, _):
        self._state['current_states']['is_playing'] = True

    def _on_cast_stopped_casting(self, _):
        self._state['current_states']['is_playing'] = False
