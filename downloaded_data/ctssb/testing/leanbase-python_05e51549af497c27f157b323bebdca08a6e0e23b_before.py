import typing
import requests
from six.moves.urllib.parse import urljoin, urlparse, urlencode, urlunparse

from leanbase import api
from leanbase.models.condition import Condition
from leanbase.models.feature import FeatureDefinition
from leanbase.models.segment import SegmentDefinition, ConditionCombinator

API_KEY = lambda: api._configuration.api_key
CONVEY_HOST = lambda: api._configuration.convey_host

def _make_request(url, params={}):
    parts = urlparse(CONVEY_HOST())
    path = urljoin(parts.path, url)
    query = urlencode(params)
    built_url = urlunparse((parts.scheme, parts.netloc, path, parts.params, query, parts.fragment))
    
    return requests.get(built_url, headers={'X-API-Token': API_KEY()})

def get_staff_segment_definition(team_id:str)->SegmentDefinition:
    response = _make_request('v1/reply/teams/{}/staff-segment'.format(team_id)).json()
    return SegmentDefinition(
        conditions=list(map(Condition.from_encoding, response['mc'])),
        combinator=response['cmb'] == 'OR' and ConditionCombinator.OR or ConditionCombinator.AND,
    )

def list_all_features(team_id:str)->typing.List[str]:
    return _make_request('v1/reply/teams/{}/features/'.format(team_id)).json()['features']

def get_feature_status(team_id:str, feature_id:str)->FeatureDefinition:
    response = _make_request('v1/reply/teams/{}/features/{}/'.format(team_id, feature_id)).json()
    if response:
        return FeatureDefinition.from_encoding(
            gs=response.get('gs'),
            _id=response.get('id'),
            es=response.get('es', []),
            ss=response.get('ss', [])
        )