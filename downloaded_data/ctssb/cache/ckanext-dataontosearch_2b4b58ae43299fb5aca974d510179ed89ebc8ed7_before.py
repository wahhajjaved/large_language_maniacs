# encoding: utf-8
import logging
import ckan.plugins.toolkit as toolkit
try:
    from ckanext.dcat.utils import dataset_uri
except ImportError:
    raise RuntimeError(
        u'ckanext-dataontosearch is dependent on ckanext-dcat, but could not '
        u'find the latter'
    )

from ckanext.dataontosearch.utils import (
    make_tagger_get_request, make_tagger_delete_request,
    make_tagger_post_request, make_search_get_request, get_use_autotag
)

logger = logging.getLogger(__name__)


@toolkit.side_effect_free
def dataontosearch_concept_list(context, data_dict):
    '''
    List concepts available from DataOntoSearch.

    :rtype: dict where key is a concept's URI, and value is a dict where the
        human-readable label is stored under 'label'.
    '''
    toolkit.check_access(u'dataontosearch_concept_list', context, data_dict)
    r = make_tagger_get_request(u'/concept')
    r.raise_for_status()

    data = r.json()

    return {
        uri: {u'label': label} for uri, label in data.items()
    }


@toolkit.side_effect_free
def dataontosearch_tag_list_all(context, data_dict):
    '''
    List existing DataOntoSearch tags for all datasets.

    :rtype: dictionary where key is ID of a dataset, and value is a list of
        concepts. Each concept is a dict, with 'label' being human-readable
        label and 'uri' being the URI identifying this concept.
    '''
    toolkit.check_access(u'dataontosearch_tag_list_all', context, data_dict)
    r = make_tagger_get_request(u'/tag')
    r.raise_for_status()

    data = r.json()

    tags = dict()

    for uri, details in data.iteritems():
        # Try to extract the ID of this dataset
        dataset_id = uri.split(u'/')[-1]

        # Was this actually a URI for this CKAN?
        model = context[u'model']

        result = model.Package.get(dataset_id)
        if result:
            tags[dataset_id] = details[u'concepts']

    return tags


@toolkit.side_effect_free
def dataontosearch_tag_list(context, data_dict):
    '''
    List concepts associated with the specified dataset.

    :param id: id or name of the dataset to fetch tags for
    :type id: string
    :rtype: list of concepts. Each concept is a dict, with 'label' being
        human-readable label and 'uri' being the URI identifying this concept
    '''
    toolkit.check_access(u'dataontosearch_tag_list', context, data_dict)

    # What dataset is specified?
    dataset_id_or_name = toolkit.get_or_bust(data_dict, u'id')
    dataset = toolkit.get_action(u'package_show')(None, {u'id': dataset_id_or_name})

    # Generate the RDF URI for this dataset, using the very same code used by
    # ckanext-dcat. We need this to be consistent with what DataOntoSearch found
    # when it retrieved the dataset RDF, thus this use of the internal DCAT API.
    dataset_rdf_uri = dataset_uri(dataset)

    r = make_tagger_get_request(u'/tag', {u'dataset_id': dataset_rdf_uri})
    r.raise_for_status()

    data = r.json()

    if data is None:
        return []
    else:
        return data[u'concepts']


def dataontosearch_tag_create(context, data_dict):
    '''
    Create a new association between the specified dataset and concept.

    :param dataset: Name or ID of the dataset to associate with a concept
    :type dataset: string
    :param concept: RDF URI or human-readable label for the concept to associate
        with the dataset
    :type dataset: string
    :return: The dataset, concept and id for the newly created tag
    :rtype: dictionary
    '''
    toolkit.check_access(u'dataontosearch_tag_create', context, data_dict)

    # Extract parameters from data_dict
    dataset_id_or_name = toolkit.get_or_bust(data_dict, u'dataset')
    concept_url_or_label = toolkit.get_or_bust(data_dict, u'concept')

    # We must provide DataOntoSearch with a URL of where to download metadata,
    # so generate this URL. First, what dataset was specified?
    dataset = toolkit.get_action(u'package_show')(
        None,
        {u'id': dataset_id_or_name}
    )

    # We assume the RDF is available at the usual dataset URL, but with a
    # .rdf suffix
    dataset_id = dataset.get(u'id')
    dataset_url = toolkit.url_for(
        u'dataset_read',
        id=dataset_id,
        qualified=True
    )
    rdf_url = u'{}.rdf'.format(dataset_url)

    # Now we are equipped to actually create the tag
    r = make_tagger_post_request(
        u'/tag',
        {
            u'dataset_url': rdf_url,
            u'concept': concept_url_or_label,
        }
    )
    r.raise_for_status()

    # Handle response
    data = r.json()

    if not data[u'success']:
        raise RuntimeError(data[u'message'])

    return {
        u'dataset': dataset_id,
        u'concept': concept_url_or_label,
        u'id': data[u'id'],
    }


def dataontosearch_tag_delete(context, data_dict):
    '''
    Remove an existing association between the specified dataset and concept.

    :param dataset: Name or ID of the dataset to disassociate with a concept
    :type dataset: string
    :param concept: RDF URI or human-readable label for the concept to no longer
        associate with the dataset
    :type dataset: string
    :return: True
    :rtype: bool
    '''
    toolkit.check_access(u'dataontosearch_tag_delete', context, data_dict)

    # Extract parameters from data_dict
    dataset_id_or_name = toolkit.get_or_bust(data_dict, u'dataset')
    concept_url_or_label = toolkit.get_or_bust(data_dict, u'concept')

    # What dataset is specified?
    dataset = toolkit.get_action(u'package_show')(None, {
        u'id': dataset_id_or_name,
    })
    dataset_rdf_uri = dataset_uri(dataset)

    # Make the request
    r = make_tagger_delete_request(u'/tag', {
        u'dataset_id': dataset_rdf_uri,
        u'concept': concept_url_or_label,
    })
    r.raise_for_status()
    data = r.json()

    return data[u'success']


def dataontosearch_dataset_delete(context, data_dict):
    '''
    Remove all existing association between the specified dataset and concepts.

    This will also remove the dataset from DataOntoSearch's data store.

    :param id: Name or ID of the dataset to remove from DataOntoSearch
    :type id: string
    :return: True if the dataset was removed, or False if the dataset was not
        found.
    :rtype: bool
    '''
    toolkit.check_access(u'dataontosearch_dataset_delete', context, data_dict)

    # Extract parameters from data_dict
    dataset_id_or_name = toolkit.get_or_bust(data_dict, u'id')

    # What dataset is specified?
    dataset = toolkit.get_action(u'package_show')(None, {
        u'id': dataset_id_or_name,
    })
    dataset_rdf_uri = dataset_uri(dataset)

    # Make the request
    r = make_tagger_delete_request(u'/dataset', {
        u'dataset_id': dataset_rdf_uri,
    })
    r.raise_for_status()
    data = r.json()

    return data[u'success']


@toolkit.side_effect_free
def dataontosearch_dataset_search(context, data_dict):
    '''
    Perform a semantic search using DataOntoSearch.

    The parameters and returned JSON is designed to be compatible with the
    regular search (package_search) as far as possible, though only the q
    parameter is supported. Some additional information from DataOntoSearch is
    also available.

    :param q: the query to use when searching
    :type q: string
    :rtype: dictionary with 'concepts' that matched the query, a 'count' of
        results and 'results' with a list of datasets that matched. For each
        dataset, their similarity 'score' and similar 'concepts' are available
        in addition to the usual information given in package_show. For each
        concept, their RDF IRI is available as 'uri', human-readable label as
        'label' and similarity score as 'similarity'
    '''
    toolkit.check_access(u'dataontosearch_dataset_search', context, data_dict)

    query = toolkit.get_or_bust(data_dict, u'q')

    parameters = {
        u'q': query,
        u'd': 0,
    }
    if get_use_autotag():
        parameters[u'a'] = 1

    r = make_search_get_request(u'/search', parameters)
    r.raise_for_status()
    data = r.json()

    results = data[u'results']
    query_concepts = data[u'concepts']

    processed_results = []

    for result in results:
        # Extract the ID of this dataset
        dataset_id = result[u'uri'].split(u'/')[-1]

        # Fetch information about this dataset
        try:
            dataset_info = toolkit.get_action(u'package_show')(context, {
                u'id': dataset_id,
            })
        except toolkit.ObjectNotFound:
            # Perhaps not part of this CKAN? This should generally not happen,
            # and can indicate some trouble with configurations in
            # DataOntoSearch or changed ID or name in CKAN
            logger.warning(
                u'Skipping dataset %(uri)s returned from DataOntoSearch, not '
                u'found in CKAN',
                {u'uri': result[u'uri']},
                exc_info=True
            )
            continue
        except toolkit.NotAuthorized:
            # This may be a private dataset or something, so don't show it
            # TODO: Does CKAN reveal that the dataset exists, but is private?
            logger.debug(
                u'Skipping dataset %(uri)s since user is not authorized to see '
                u'it',
                {u'uri': result[u'uri']},
                exc_info=True
            )
            continue

        # Enrich with information from DataOntoSearch's result
        extra_info = {
            u'concepts': result[u'concepts'],
            u'score': result[u'score'],
        }
        dataset_info.update(extra_info)

        # Processed!
        processed_results.append(dataset_info)

    return {
        u'count': len(processed_results),
        u'results': processed_results,
        u'concepts': query_concepts,
        # Include dummy data for keys present in package_search
        u'sort': u'',
        u'facets': {},
        u'search_facets': {}
    }
