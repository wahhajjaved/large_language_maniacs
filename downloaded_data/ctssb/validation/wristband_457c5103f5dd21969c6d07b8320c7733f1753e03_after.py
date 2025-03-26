import requests
from django.conf import settings

from wristband.common.utils import extract_stage

from wristband.common.providers import JsonDataProvider


class ParentReleaseAppDataProvider(JsonDataProvider):
    def _get_raw_data(self):
        url = settings.RELEASES_APP_URI
        response = requests.get(url)
        return response.json()

    @staticmethod
    def extract_stage_from_env(env):
        return extract_stage(env)


class NestedReleaseAppDataProvider(ParentReleaseAppDataProvider):
    def _get_list_data(self):
        """
        Show only the latest version per stage, filter by last seen
        """
        return [{'name': app['an'],
                 'version': app['ver'],
                 'stage': self.extract_stage_from_env(app['env'])}
                for app in self.raw_data]


class ReleaseAppDataProvider(ParentReleaseAppDataProvider):
    def _get_list_data(self):
        """
        We need to get this format from the current releases app format
        Releases app also returns some history, so we need to sort by last seen first.
        A relational database would simplify this code because this is nasty and slow


        Releases app output:
        [
            {
                "an": "a-b-test",
                "env": "qa-left",
                "ver": "1.7.7"
            },
            {
                "an": "a-b-test",
                "env": "staging-left",
                "ver": "1.7.2"
            }
        ]

        Expected output:
        [
            {
                "name": "a-b-test",
                    "stages": [
                        {
                           "name": "qa",
                           "version": "1.7.7"
                        },
                        {
                           "name": "staging",
                           "version": "1.7.2"
                        }
                    ]
            },
            {...}
        ]
        """
        data = []
        # this assumes that last seen corresponds to the latest version
        ordered_data = sorted(self.raw_data, key=lambda x: x['ls'], reverse=True)
        apps_indexes = {}
        for app in ordered_data:
            app_name = app['an']
            app_stage = extract_stage(app['env'])
            if app_name in apps_indexes.keys():
                # we've already seen this app
                # check if we already have the relevant stage,
                # the data has been ordered, if we have this stage then we should already have the latest one

                already_seen_app_index = apps_indexes[app_name]
                app_stages_names = [stage['name'] for stage in data[already_seen_app_index]['stages']]
                if app_stage not in app_stages_names:
                    # we don't have this stage at all, just add it
                    data[already_seen_app_index]['stages'].append({
                        'name': app_stage,
                        'version': app['ver']
                    })
            else:
                # this is the best case
                # we've never seen this app before, just add the app and the stage+version
                app_to_be_added = {
                    'name': app_name,
                    'stages': [{
                        'name': app_stage,
                        'version': app['ver']
                    }]
                }
                data.append(app_to_be_added)
                apps_indexes[app_name] = len(data) - 1
        return sorted(data, key=lambda x: x['name'], reverse=True)
