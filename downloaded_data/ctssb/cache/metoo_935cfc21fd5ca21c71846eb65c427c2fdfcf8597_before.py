import qiime
from qiime.core.registry import plugin_registry
from qiime.core.tornadotools import route, GET, POST, PUT, DELETE, yield_urls
from qiime.db import Artifact, ArtifactProxy, Study

def get_urls():
    return list(yield_urls())

@route('/system', GET)
def system_info():
    return {'version': qiime.__version__}

@route('/system/methods', GET, params=['plugin'])
def list_methods(plugin=None):
    return {'methods': [m.uri for m in plugin_registry.get_methods(plugin=plugin)]}

@route('/sytem/methods/(.+)', GET)
def method_info(method_uri):
    method = plugin_registry.get_method(method_uri)
    return {
        'uri': method.uri,
        'name': method.name,
        'help': method.docstring,
        'annotations': {
            'artifacts': [],  # (parameterized) artifacts (defined in org.qiime.plugins.[plugin-name].artifacts)
            'parameters': {}, # (parameterized) primitives (defined in org.qiime.types.primitives|parameterized)
            'return': []      # (parameterized) artifacts
        }
    }

@route('/system/plugins', GET)
def list_plugins():
    return {'plugins': list(plugin_registry.get_plugin_uris())}

@route('/system/plugins/([^/]+)', GET)
def plugin_info(plugin_uri):
    plugin = plugin_registry.get_plugin(plugin_uri)

    plugin_info = {
        'uri': plugin_uri,
        'name': plugin.name,
        'version': plugin.version,
        'author': plugin.author,
        'description': plugin.description
    }
    plugin_info.update(list_methods(plugin=plugin_uri))

    return plugin_info

@route('/studies', GET)
def list_studies():
    return {
        'studies': [study.id for study in Study.select()]
    }

@route('/studies', POST, params=['name', 'description'])
def create_study(request, name, description):
    study = Study(name=name, description=description)
    study.save()
    return {
        'study_id': study.id
    }

@route('/studies/([^/]+)', GET)
def study_info(study_id):
    study = Study.get(Study.id == study_id)

    return {
        'study_id': study.id,
        'name': study.name,
        'description': study.description,
        'created': str(study.created)
    }

@route('/studies/([^/]+)', PUT, params=['name', 'description'])
def study_info(request, study_id, name=None, description=None):
    study = Study.get(Study.id == study_id)
    if name is not None:
        study.name = name
    if description is not None:
        study.description = description
    study.save()

    return {} # TODO normalize responses with status

@route('/studies/([^/]+)', DELETE)
def study_info(study_id):
    study = Study.get(Study.id == study_id)
    study.delete_instance() # TODO think about cascading deletes

    return {} # TODO normalize responses with status

@route('/studies/([^/]+)/artifacts', POST, params=['name', 'artifact_type'])
def create_artifact(request, study_id, name, artifact_type):
    data = get_file_data(request)
    if data is None:
        raise ValueError("Cannot create artifact: missing uploaded file.")

    # TODO remove when using postgresql and foreign keys are actually supported
    study = Study.get(id=study_id)
    artifact = Artifact(type=artifact_type, data=data, study=study)
    artifact.save()

    artifact_proxy = ArtifactProxy(name=name, artifact=artifact, study=study)
    artifact_proxy.save()

    return {
        'artifact_id': artifact_proxy.id
    }

@route('/studies/([^/]+)/artifacts', GET)
def list_artifacts(study_id):
    artifacts = Study.get(id=study_id).artifacts

    return {
        'artifact_ids': [a.id for a in artifacts]
    }

@route('/studies/([^/]+)/artifacts', PUT, params=['artifact_id'])
def link_artifact(request, study_id, artifact_id):
    parent_artifact = ArtifactProxy.get(id=artifact_id)
    linked_artifacts = ArtifactProxy.select().where(
        ArtifactProxy.artifact == parent_artifact.artifact,
        ArtifactProxy.study == study_id)

    if linked_artifacts.count() == 0:
        linked_artifact = ArtifactProxy(artifact=parent_artifact.artifact,
                                        name=parent_artifact.name,
                                        study=study_id)
        linked_artifact.save()
    else:
        linked_artifact = linked_artifacts.get()

    return {
        'artifact_id': linked_artifact.id
    }

@route('/studies/([^/]+)/artifacts/([^/]+)', GET, params=['export'])
def artifact_info(study_id, artifact_id, export=None):
    proxy = ArtifactProxy.select().where(
        ArtifactProxy.id == artifact_id,
        ArtifactProxy.study == study_id).get()

    return {
            'arifact_id': proxy.id,
            'name': proxy.name,
            'type': proxy.artifact.type
    }

@route('/studies/([^/]+)/artifacts/([^/]+)', PUT, params=['name'])
def delete_artifact(request, study_id, artifact_id, name=None):
    proxy = ArtifactProxy.get(id=artifact_id)
    if proxy.study.id == int(study_id): # TODO fix int hack!
        if name is not None:
            proxy.name = name

        proxy.save()
    else:
        raise ValueError("Wrong study")

    return {}

@route('/studies/([^/]+)/artifacts/([^/]+)', DELETE)
def delete_artifact(study_id, artifact_id):
    proxy = ArtifactProxy.get(id=artifact_id)
    if proxy.study.id == int(study_id): # TODO fix int hack!
        proxy.delete_instance()
    else:
        raise ValueError("Wrong study")

    return {}

#@route('/artifacts/(.+)', PUT, params=['name', 'artifact_type'])
#def update_artifact(request, artifact_id, name=None, artifact_type=None):
#    data = get_file_data(request)
#
#    update_fields = []
#    update_values = []
#
#    # TODO we'll need to be smarter about updating type and/or data
#    if name is not None:
#        update_fields.append('name = ?')
#        update_values.append(name)
#    if artifact_type is not None:
#        update_fields.append('type = ?')
#        update_values.append(artifact_type)
#    if data is not None:
#        update_fields.append('data = ?')
#        update_values.append(data)
#
#    conn = get_connection()
#    c = conn.cursor()
#
#    query = "UPDATE artifact SET %s WHERE id = ?" % ', '.join(update_fields)
#    c.execute(query, update_values + [artifact_id])
#
#    c.close()
#    conn.commit()
#    return {
#        'status': 'success'
#    }
#
#@route('/artifacts/(.+)', DELETE)
#def delete_artifact(artifact_id):
#    conn = get_connection()
#    c = conn.cursor()
#
#    # TODO handle the case where the artifact doesn't exist
#    c.execute("DELETE FROM artifact WHERE id = ?", (artifact_id,))
#
#    c.close()
#    conn.commit()
#
#    return {
#        'status': 'success'
#    }
#
def get_file_data(request):
    files = request.files
    if not files:
        return None

    if len(files) > 1:
        raise ValueError("Need 1 named file to upload as artifact, found %d."
                         % len(files))

    upload_name, file_infos = files.popitem()
    if len(file_infos) != 1:
        raise ValueError("Need exactly 1 file to upload as artifact, found "
                         "named file %s with %d payloads." %
                         (repr(upload_name), len(file_infos)))
    file_info = file_infos[0]
    return file_info['body'] # bytes
