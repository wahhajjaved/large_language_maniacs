# Copyright (c) 2018 SAP SE or an SAP affiliate company. All rights reserved. This file is licensed
# under the Apache Software License, v. 2 except as noted otherwise in the LICENSE file
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
import os

import elasticsearch

import model.elasticsearch
import util


def from_cfg(
    elasticsearch_cfg:model.elasticsearch.ElasticSearchConfig
):
    return ElasticSearchClient(
        elasticsearch=_from_cfg(elasticsearch_cfg=elasticsearch_cfg)
    )


def _from_cfg(
    elasticsearch_cfg:model.elasticsearch.ElasticSearchConfig
):
    credentials = elasticsearch_cfg.credentials()
    return elasticsearch.Elasticsearch(
        elasticsearch_cfg.endpoints(),
        http_auth=(credentials.username(), credentials.passwd()),
    )


@functools.lru_cache()
def _metadata_dict():
    # XXX mv to concourse package; deduplicate with notify step
    if not util._running_on_ci():
        return {}

    # XXX do not hard-code meta-dir
    meta_dir = util.existing_dir(os.path.join(util._root_dir()))
    attrs = (
        'atc-external-url',
        'build-team-name',
        'build-pipeline-name',
        'build-job-name',
        'build-name',
    )

    def read_attr(name):
        with open(os.path.join(meta_dir, name)) as f:
            return f.read().strip()

    meta_dict = {
        name: read_attr(name) for name in attrs
    }

    return meta_dict


class ElasticSearchClient(object):
    def __init__(
        self,
        elasticsearch: elasticsearch.Elasticsearch,
    ):
        self._api = elasticsearch

    def store_document(
        self,
        index: str,
        body: dict,
        inject_metadata=True,
        *args,
        **kwargs,
    ):
        util.check_type(index, str)
        util.check_type(body, dict)
        if 'doc_type' in kwargs:
            raise ValueError(
                '''
                doc_type attribute has been deprecated - see:
                https://www.elastic.co/guide/en/elasticsearch/reference/6.0/removal-of-types.html
                '''
            )

        if inject_metadata and _metadata_dict():
            md = _metadata_dict()
            body['cc_meta'] = md
            # XXX deduplicate; mv to concourse package
            md['concourse_url'] = util.urljoin(
                md['atc-external-url'],
                'teams',
                md['build-team-name'],
                'pipelines',
                md['build-pipeline-name'],
                'jobs',
                md['build-job-name'],
                'builds',
                md['build-name'],
            )

        return self._api.index(
            index=index,
            doc_type='_doc',
            body=body,
            *args,
            **kwargs,
        )
