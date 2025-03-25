# -*- coding: utf-8 -*-
from biothings.www.api.es.transform import ESResultTransformer
from biothings.utils.common import is_str, is_seq
from collections import OrderedDict
#import logging

class ESResultTransformer(ESResultTransformer):
    # Add app specific result transformations
    def __init__(self, max_taxid_count=10000, *args, **kwargs):
        super(ESResultTransformer, self).__init__(*args, **kwargs)
        #logging.debug(self.options)
        self.max_taxid_count = max_taxid_count
        self._children_query_dict = {}

    def _children_query(self, ids, has_gene=True, include_self=False, raw=False):
        if is_str(ids) or isinstance(ids, int) or (is_seq(ids) and len(ids) == 1):
            _ids = ids if is_str(ids) or isinstance(ids, int) else ids[0] 
            _qstring = "lineage:{} AND has_gene:true".format(_ids) if has_gene else "lineage:{}".format(_ids)
            res = self.options.es_client.search(body={"query":{"query_string":{"query": _qstring}}},
                index=self.options.index, doc_type=self.options.doc_type, fields='_id', size=self.max_taxid_count)
            
            if raw:
                return res
            
            taxid_li = [int(x['_id']) for x in res['hits']['hits'] if x['_id'] != _ids or include_self]
            taxid_li += ([_ids] if include_self and _ids not in taxid_li else [])        
            return {_ids: sorted(taxid_li)[:self.max_taxid_count]}
        elif is_seq(ids):
            qs = '\n'.join(['{{}}\n{{"size": {}, "_source": ["_id"], "query": {{"query_string":{{"query": "lineage:{} AND has_gene:true"}}}}}}'.format(self.max_taxid_count, taxid) if has_gene
                else '{{}}\n{{"size": {}, "_source": ["_id"], "query":{{"query_string":{{"query":"lineage:{}"}}}}}}'.format(self.max_taxid_count, taxid) for taxid in ids])
            res = self.options.es_client.msearch(body=qs, index=self.options.index, doc_type=self.options.doc_type)
            if 'responses' not in res or len(res['responses']) != len(ids):
                return {}
            
            _ret = {}

            for (taxid, response) in zip(ids, res['responses']):
                _ret.setdefault(taxid, []).extend([h['_id'] for h in response['hits']['hits'] 
                                                    if h['_id'] != taxid or include_self])
            for taxid in _ret.keys():
                _ret[taxid] = sorted([int(x) for x in list(set(_ret[taxid]))] + 
                    ([int(taxid)] if include_self and taxid not in _ret[taxid] else []))[:self.max_taxid_count]
            return _ret
        else:
            return {}

    def clean_query_GET_response(self, res):
        if self.options.include_children:
            self._children_query_dict = self._children_query(ids=[o['_id'] for o in res['hits']['hits']], 
                                                            has_gene=self.options.has_gene)
        return self._clean_query_GET_response(res)

    def clean_query_POST_response(self, qlist, res, single_hit=True):
        if self.options.include_children:
            self._children_query_dict = self._children_query(ids=list(set([hit['_id'] for hit_list in res['responses'] 
                for hit in hit_list['hits']['hits']])), has_gene=self.options.has_gene)
        return self._clean_query_POST_response(qlist, res, single_hit)

    def clean_annotation_GET_response(self, res):
        if self.options.include_children:
            self._children_query_dict = self._children_query(ids=res.get('_id', []) if 'hits' not in res 
                             else [o['_id'] for o in res['hits']['hits']], has_gene=self.options.has_gene)
        return self._clean_annotation_GET_response(res)

    def clean_annotation_POST_response(self, bid_list, res, single_hit=True):
        if self.options.include_children or self.options.expand_species:
            self._children_query_dict = self._children_query(ids=list(set([hit['_id'] for hit_list in res['responses'] 
                for hit in hit_list['hits']['hits']])), has_gene=self.options.has_gene)
            if self.options.expand_species:
                return sorted(list(set([v for v_list in self._children_query_dict.values() for v in v_list] + [int(x) for x in bid_list])))[:self.max_taxid_count]
        return self._clean_annotation_POST_response(bid_list, res, single_hit)

    def clean_metadata_response(self, res, fields=False):
        _res = self._clean_metadata_response(res, fields=fields)
        if not fields and "stats" in _res and "distribution of taxonomy ids by rank" in _res["stats"]:
            _res["stats"]["distribution of taxonomy ids by rank"] = OrderedDict(sorted(list(_res["stats"]["distribution of taxonomy ids by rank"].items()), key=lambda v: v[1], reverse=True))
        return _res

    def _modify_doc(self, doc):
        if self.options.include_children and doc['_id'] in self._children_query_dict:
            doc['children'] = self._children_query_dict[doc['_id']]
