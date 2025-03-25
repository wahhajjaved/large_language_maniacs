from datetime import datetime
from itertools import chain

from elasticsearch.helpers import streaming_bulk
from elasticsearch_dsl import DocType, String, Date, Nested, InnerObjectWrapper, Integer


def get_index_name(repo):
    if 'git-index.index' in repo.config:
        return repo.config['git-index.index']
    elif 'origin' in repo.remotes:
        return repo.remotes['origin'].url.split(':')[1].split('/')[1].split('.')[0]
    elif len(repo.remotes) != 0:
        return next(repo.remotes).url.split(':')[1].split('/')[1].split('.')[0]
    else:
        return 'test'


def expand_doc_callback(name):
    def expand_doc(doc):
        return dict(index=dict(_index=name, _type=doc._doc_type.name)), doc.to_dict()

    return expand_doc


class Author(InnerObjectWrapper):
    pass


class DiffLine(InnerObjectWrapper):
    pass


class Commit(DocType):
    sha = String()
    author = Nested(properties={
        'name': String(),
        'email': String()
    })
    committed_date = Date()
    message = String()


class DiffHunk(DocType):
    commit_sha = String()
    path = String()
    old_start = Integer()
    old_lines = Integer()
    new_start = Integer()
    new_lines = Integer()
    lines = Nested(properties={
        'type': String(index='not_analyzed'),
        'content': String(analyzer='code')  # TODO: make configurable
    })


def index(repo, es, commit, follow=False, mappings=True):
    commit = repo.revparse_single(commit)
    if mappings:
        Commit.init(get_index_name(repo))
        DiffHunk.init(get_index_name(repo))
    if not follow:
        documents = commit_documents(repo, commit)
    else:
        documents = chain.from_iterable(commit_documents(repo, c) for c in repo.walk(commit.id))
    res = [rv for rv in streaming_bulk(es, documents, expand_action_callback=expand_doc_callback(get_index_name(repo)))]
    print("Successfully indexed {}/{} documents".format(sum(1 for r, _ in res if r), len(res)))


def commit_documents(repo, commit):
    yield Commit(sha=str(commit.id), author=dict(name=commit.author.name, email=commit.author.email),
                 committed_date=datetime.fromtimestamp(commit.commit_time), message=commit.message)
    if commit.parents:
        diff = repo.diff(commit, commit.parents[0])
    else:
        diff = commit.tree.diff_to_tree()
    for patch_or_delta in diff:
        for hunk in patch_or_delta.hunks:
            yield DiffHunk(commit_sha=str(commit.id),
                           path=patch_or_delta.delta.new_file.path,
                           old_start=hunk.old_start,
                           old_lines=hunk.old_lines,
                           new_start=hunk.new_start,
                           new_lines=hunk.new_lines,
                           lines=[dict(type=l.origin, content=l.content) for l in hunk.lines])
