from core import GitHubObject
from issue import Issue

class Repository(GitHubObject):

    def __init__(self, session, data):
        super().__init__(session, data)
        self.ISSUES_URL = data['issues_url']
        self.ISSUE_URL = data['issues_url'].replace('{/number}', '/{}')

    def get_issue(self, id):
        url = self.ISSUE_URL.format(id)
        r = self.session.get(url)
        r.raise_for_status()
        return Issue(self.session, r.json())
