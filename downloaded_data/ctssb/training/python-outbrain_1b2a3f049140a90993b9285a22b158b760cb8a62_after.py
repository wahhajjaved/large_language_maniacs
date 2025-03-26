import pytz
import requests
import simplejson as json
import yaml


class OutbrainAmplifyApi(object):

    def __init__(self, outbrain_config=None):
        if not outbrain_config:
            outbrain_config = yaml.load(open('outbrain.yml', 'r'))
        self.user = outbrain_config['user']
        self.password = outbrain_config['password']
        self.base_url = outbrain_config['base_url']
        if not self.base_url.endswith('/'):
            self.base_url += '/'
            
        self.token = self.get_token(self.user, self.password)
        self.locale = pytz.timezone("US/Eastern")  # Outbrain's reporting is in Eastern time

    def _request(self, path, params={}):
        url = self.base_url + path
        r = requests.get(url, headers={'OB-TOKEN-V1': self.token}, params=params)
        return json.loads(r.text)

    def get_token(self, user, password):
        token_url = self.base_url + 'login'
        basic_auth = requests.auth.HTTPBasicAuth(user, password)
        r = requests.get(token_url, auth=basic_auth)
        results = json.loads(r.text)
        return results['OB-TOKEN-V1']

    # ----------------------------------------------------------------------------------------------
    # Methods to acquire marketer information
    # ----------------------------------------------------------------------------------------------
    def get_marketer(self, marketer_id):
        path = 'marketers/{0}'.format(marketer_id)
        result = self._request(path)
        return result

    def get_marketers(self):
        path = 'marketers'
        results = self._request(path)
        return results.get('marketers', [])

    def get_marketer_ids(self):
        marketers = self.get_marketers()
        return [marketer['id'] for marketer in marketers]

    # ----------------------------------------------------------------------------------------------
    # Methods to acquire budget information
    # ----------------------------------------------------------------------------------------------
    def get_budget(self, budget_id):
        path = 'budgets/{0}'.format(budget_id)
        result = self._request(path)
        return result

    def get_budgets_per_marketer(self, marketer_ids):
        budgets = {}
        for marketing_id in marketer_ids:
            path = '/marketers/{0}/budgets'.format(marketing_id)
            results = self._request(path)
            marketer_budgets = results.get('budgets', [])
            budgets[marketing_id] = marketer_budgets
        return budgets

    # ----------------------------------------------------------------------------------------------
    # Methods to acquire campaign information
    # ----------------------------------------------------------------------------------------------
    def get_campaign(self, campaign_id):
        path = 'campaigns/' + campaign_id
        result = self._request(path)
        return result

    def get_campaign_ids(self):
        return [c['id'] for c in self.get_campaigns()]

    def get_campaigns(self):
        return [c for c in self._yield_all_campaigns()]

    def _yield_all_campaigns(self):
        marketer_ids = self.get_marketer_ids()
        marketer_campaigns = self.get_campaigns_per_marketer(marketer_ids)
        for m in marketer_campaigns.keys():
            for c in marketer_campaigns[m]:
                yield c

    def get_campaigns_per_budget(self, budget_ids):
        campaigns = {}
        for budget_id in budget_ids:
            path = 'budgets/{0}/campaigns'.format(budget_id)
            results = self._request(path)
            budget_campaigns = results.get('campaigns', [])
            campaigns[budget_id] = budget_campaigns
        return campaigns

    def get_campaigns_per_marketer(self, marketing_ids, include_archived=True):
        campaigns = {}
        for marketing_id in marketing_ids:
            path = 'marketers/{0}/campaigns'.format(marketing_id)
            params = {'includeArchived': 'true' if include_archived else 'false'}
            results = self._request(path, params)
            marketer_campaigns = results.get('campaigns', [])
            campaigns[marketing_id] = marketer_campaigns
        return campaigns

    # ----------------------------------------------------------------------------------------------
    # Methods to acquire specific performance information
    # ----------------------------------------------------------------------------------------------
    def get_campaign_performace_per_promoted_link(self, campaign_ids, start_day, end_day):
        """
        :returns: dict[campaign_id][publisher_id] = performance_data
        """
        performance = dict()
        for c in campaign_ids:
            path = 'campaigns/{0}/performanceByPromotedLink'.format(c)
            performance[c] = dict()
            result = self._page_performance_data(path, start_day, end_day)
            for data in result:
                performance[c][data['id']] = data
        return performance

    def get_campaign_performace_per_publisher(self, campaign_ids, start_day, end_day):
        """
        :returns: dict[campaign_id][publisher_id] = performance_data
        """
        performance = dict()
        for c in campaign_ids:
            path = 'campaigns/{0}/performanceByPublisher'.format(c)
            performance[c] = dict()
            result = self._page_performance_data(path, start_day, end_day)
            for data in result:
                performance[c][data['id']] = data
        return performance

    def get_marketers_performace_per_section(self, marketer_ids, start_day, end_day):
        """
        :returns: dict[marketer_id][section] = performance_data
        """
        performance = dict()
        for m in marketer_ids:
            path = 'marketers/{0}/performanceBySection'.format(m)
            performance[m] = dict()
            result = self._page_performance_data(path, start_day, end_day)
            for data in result:
                performance[m][data['id']] = data
        return performance

    def get_publisher_performace_per_marketer(self, marketer_ids, start_day, end_day):
        """
        :returns: dict[marketer_id][publisher_id] = performance_data
        """
        performance = dict()
        for m in marketer_ids:
            path = 'marketers/{0}/performanceByPublisher'.format(m)
            performance[m] = dict()
            result = self._page_performance_data(path, start_day, end_day)
            for data in result:
                performance[m][data['id']] = data
        return performance

    def get_campaign_performace_per_section(self, campaign_ids, start_day, end_day):
        """
        :returns: dict[campaign_id][section] = performance_data
        """
        performance = dict()
        for c in campaign_ids:
            path = 'campaigns/{0}/performanceBySection'.format(c)
            performance[c] = dict()
            result = self._page_performance_data(path, start_day, end_day)
            for data in result:
                performance[c][data['id']] = data
        return performance

    # ----------------------------------------------------------------------------------------------
    # "Private" helper methods for acquiring/paging performance information
    # ----------------------------------------------------------------------------------------------
    def _page_performance_data(self, path, start, end):
        result = []
        offset = 0

        performance = self._get_performance_data(path, start, end, 50, offset)
        while performance:
            result.extend(performance)

            offset += len(performance)
            performance = self._get_performance_data(path, start, end, 50, offset)
        return result

    def _get_performance_data(self, path, start, end, limit, offset):
        if not start.tzinfo:
            start = start.replace(tzinfo=pytz.UTC)
        if not end.tzinfo:
            end = end.replace(tzinfo=pytz.UTC)
        start = start.astimezone(self.locale)
        end = end.astimezone(self.locale)

        params = {'limit': limit,
                  'offset': offset,
                  'from': start.strftime('%Y-%m-%d'),
                  'to': end.strftime('%Y-%m-%d')}
        result = self._request(path, params)
        return result.get('details', [])

    # ----------------------------------------------------------------------------------------------
    # Methods to acquire promoted link information
    # ----------------------------------------------------------------------------------------------
    def get_promoted_link(self, promoted_link_id):
        path = 'promotedLinks/{id}'.format(id=promoted_link_id)
        result = self._request(path)
        return result

    def get_promoted_links_per_campaign(self, campaign_ids=[], enabled=None, statuses=[]):
        campaign_ids = campaign_ids or self.get_campaign_ids()
        promoted_links = dict()
        for c in campaign_ids:
            promoted_links[c] = self.get_promoted_links_for_campaign(c, enabled, statuses)
        return promoted_links

    def get_promoted_links_for_campaign(self, campaign_id, enabled=None, statuses=[]):
        return [link for link in self._yield_promoted_links_for_campaign(campaign_id, enabled, statuses)]

    def _yield_promoted_links_for_campaign(self, campaign_id, enabled=None, statuses=[]):
        offset = 0
        path = 'campaigns/{0}/promotedLinks'.format(campaign_id)
        promoted_links = self._page_promoted_links_for_campaign(path, enabled, statuses, 50, offset)
        while promoted_links:
            for pl in promoted_links:
                yield pl

            offset += len(promoted_links)
            promoted_links = self._page_promoted_links_for_campaign(path, enabled, statuses, 50, offset)

    def _page_promoted_links_for_campaign(self, path, enabled, statuses, limit, offset):
        params = {'limit': limit,
                  'offset': offset}

        if enabled is not None:
            params['enabled'] = 'true' if enabled else 'false'
        if statuses:
            params['statuses'] = ','.join(statuses)

        return self._request(path, params).get('promotedLinks', [])

    # ----------------------------------------------------------------------------------------------
    # Other methods
    # ----------------------------------------------------------------------------------------------
    def get_currencies(self):
        results = self._request('currencies')
        return results.get('currencies', [])
