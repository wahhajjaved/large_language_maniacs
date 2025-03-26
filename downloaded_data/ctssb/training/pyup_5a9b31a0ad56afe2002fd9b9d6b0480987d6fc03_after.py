# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals
import logging
import yaml
from .requirements import RequirementsBundle
from .providers.github import Provider as GithubProvider
from .errors import NoPermissionError, BranchExistsError
from .config import Config

logger = logging.getLogger(__name__)


class Bot(object):
    def __init__(self, repo, user_token, bot_token=None,
                 provider=GithubProvider, bundle=RequirementsBundle, config=Config):
        self.bot_token = bot_token
        self.req_bundle = bundle()
        self.provider = provider(self.req_bundle)
        self.user_token = user_token
        self.bot_token = bot_token
        self.fetched_files = []
        self.repo_name = repo

        self._user = None
        self._user_repo = None
        self._bot = None
        self._bot_repo = None
        self.config = config()

        self._fetched_prs = False

    @property
    def user_repo(self):
        if self._user_repo is None:
            self._user_repo = self.provider.get_repo(token=self.user_token, name=self.repo_name)
        return self._user_repo

    @property
    def user(self):
        if self._user is None:
            self._user = self.provider.get_user(token=self.user_token)
        return self._user

    @property
    def bot(self):
        if self._bot is None:
            self._bot = self.provider.get_user(token=self.bot_token)
        return self._bot

    @property
    def bot_repo(self):
        if self._bot_repo is None:
            self._bot_repo = self.provider.get_repo(token=self.bot_token, name=self.repo_name)
        return self._bot_repo

    @property
    def pull_requests(self):
        if not self._fetched_prs:
            self.req_bundle.pull_requests = [pr for pr in self.provider.iter_issues(
                repo=self.user_repo, creator=self.bot if self.bot_token else self.user)]
            self._fetched_prs = True
        return self.req_bundle.pull_requests

    def get_repo_config(self, repo):
        try:
            content, _ = self.provider.get_file(repo, "/.pyup.yml", self.config.branch)
            if content is not None:
                return yaml.load(content)
        except yaml.YAMLError:
            logger.warning("Unable to parse config file /.pyup.yml", exc_info=True)
        return None

    def configure(self, **kwargs):
        # if the branch is not set, get the default branch
        if kwargs.get("branch", False) in [None, False]:
            self.config.branch = self.provider.get_default_branch(repo=self.user_repo)
        # set the config for this update run
        self.config.update(kwargs)
        repo_config = self.get_repo_config(repo=self.user_repo)
        if repo_config:
            self.config.update(repo_config)

    def update(self, **kwargs):
        """
        Main entrypoint to kick off an update run.
        :param kwargs:
        :return: RequirementsBundle
        """
        self.configure(**kwargs)
        self.get_all_requirements()
        self.apply_updates(
            initial=kwargs.get("initial", False),
        )

        return self.req_bundle

    def apply_updates(self, initial):

        InitialUpdateClass = self.req_bundle.get_initial_update_class()

        if initial:
            # get the list of pending updates
            try:
                _, _, _, updates = list(
                    self.req_bundle.get_updates(initial=initial, config=self.config)
                )[0]
            except IndexError:
                # need to catch the index error here in case the intial update is completely
                # empty
                updates = False
            # if this is the initial run and the update list is empty, the repo is already
            # up to date. In this case, we create an issue letting the user know that the bot is
            # now set up for this repo and return early.
            if not updates:
                self.create_issue(
                    title=InitialUpdateClass.get_title(),
                    body=InitialUpdateClass.get_empty_update_body()
                )
                return

        # check if we have an initial PR open. If this is the case, we attach the initial PR
        # to all updates and are done. The `Initial Update` has to be merged (or at least closed)
        # before we continue to do anything here.
        initial_pr = next(
            (pr for pr in self.pull_requests if
             pr.title == InitialUpdateClass.get_title() and pr.is_open),
            False
        )

        # todo: This block needs to be refactored
        for title, body, update_branch, updates in self.iter_updates(initial):
            if initial_pr:
                pull_request = initial_pr
            elif title not in [pr.title for pr in self.pull_requests]:
                pull_request = self.commit_and_pull(
                    initial=initial,
                    base_branch=self.config.branch,
                    new_branch=update_branch,
                    title=title,
                    body=body,
                    updates=updates
                )
            else:
                pull_request = next((pr for pr in self.pull_requests if pr.title == title), None)

            for update in updates:
                update.requirement.pull_request = pull_request
                if self.config.close_prs and pull_request and not initial:
                    self.close_stale_prs(update=update, pull_request=pull_request)

    def close_stale_prs(self, update, pull_request):
        """
        Closes stale pull requests for the given update, links to the new pull request and deletes
        the stale branch.
        A stale PR is a PR that:
         - Is not merged
         - Is not closed
         - Has no commits (except the bot commit)
        :param update:
        :param pull_request:
        """
        logger.info("Preparing to close stale PRs for {}".format(pull_request.title))
        if self.bot_token and pull_request.type != "initial":
            for pr in self.pull_requests:
                logger.info("Checking PR {}".format(pr.title))
                # check that, the pr is an update, is open, the titles are not equal and that
                # the requirement matches
                if pr.type == "update" and \
                    pr.is_open and \
                        pr.title != pull_request.title and \
                        pr.requirement == update.requirement.key:
                    committer = self.provider.get_pull_request_committer(
                        self.user_repo, pr)
                    # check that there's exactly one committer in this PRs commit history and
                    # that the committer is the bot
                    if len(committer) == 1 and self.provider.is_same_user(self.bot, committer[0]):
                        self.provider.close_pull_request(
                            bot_repo=self.bot_repo,
                            user_repo=self.user_repo,
                            pull_request=pr,
                            comment="Closing this in favor of #{}".format(pull_request.number)
                        )

    def create_branch(self, base_branch, new_branch, delete_empty=False):
        """
        Creates a new branch.
        :param base_branch: string name of the base branch
        :param new_branch: string name of the new branch
        :param delete_empty: bool -- delete the branch if it is empty
        :return: bool -- True if successfull
        """
        logger.info("Preparing to create branch {} from {}".format(new_branch, base_branch))
        try:
            # create new branch
            self.provider.create_branch(
                base_branch=base_branch,
                new_branch=new_branch,
                repo=self.user_repo
            )
            logger.info("Created branch {} from {}".format(new_branch, base_branch))
            return True
        except BranchExistsError:
            logger.info("Branch {} exists.".format(new_branch))
            # if the branch exists, is empty and delete_empty is set, delete it and call
            # this function again
            if delete_empty:
                if self.provider.is_empty_branch(self.user_repo, base_branch, new_branch):
                    self.provider.delete_branch(self.user_repo, new_branch)
                    logger.info("Branch {} was empty and has been deleted".format(new_branch))
                    return self.create_branch(base_branch, new_branch, delete_empty=False)
                logger.info("Branch {} is not empty".format(new_branch))
        return False

    def commit_and_pull(self, initial, base_branch, new_branch, title, body, updates):
        logger.info("Preparing commit {}".format(title))
        if self.create_branch(base_branch, new_branch, delete_empty=False):
            updated_files = {}
            for update in self.iter_changes(initial, updates):
                if update.requirement_file.path in updated_files:
                    sha = updated_files[update.requirement_file.path]["sha"]
                    content = updated_files[update.requirement_file.path]["content"]
                else:
                    sha = update.requirement_file.sha
                    content = update.requirement_file.content
                old_content = content
                content = update.requirement.update_content(content)
                if content != old_content:
                    new_sha = self.provider.create_commit(
                        repo=self.user_repo,
                        path=update.requirement_file.path,
                        branch=new_branch,
                        content=content,
                        commit_message=update.commit_message,
                        sha=sha,
                        committer=self.bot if self.bot_token else self.user,
                    )
                    updated_files[update.requirement_file.path] = {"sha": new_sha,
                                                                   "content": content}
                else:
                    logger.error("Empty commit at {repo}, unable to update {title}.".format(
                        repo=self.user_repo.full_name, title=title)
                    )

            if updated_files:
                pr = self.create_pull_request(
                    title=title,
                    body=body,
                    base_branch=base_branch,
                    new_branch=new_branch
                )
                self.pull_requests.append(pr)
                return pr
        return None

    def create_issue(self, title, body):
        return self.provider.create_issue(
            repo=self.bot_repo if self.bot_token else self.user_repo,
            title=title,
            body=body,
        )

    def create_pull_request(self, title, body, base_branch, new_branch):

        # if we have a bot user that creates the PR, we might run into problems on private
        # repos because the bot has to be a collaborator. We try to submit the PR before checking
        # the permissions because that saves us API calls in most cases
        if self.bot_token:
            try:
                return self.provider.create_pull_request(
                    repo=self.bot_repo,
                    title=title,
                    body=body,
                    base_branch=base_branch,
                    new_branch=new_branch,
                )
            except NoPermissionError:
                self.provider.get_pull_request_permissions(self.bot, self.user_repo)

        return self.provider.create_pull_request(
            repo=self.bot_repo if self.bot_token else self.user_repo,
            title=title,
            body=body,
            base_branch=base_branch,
            new_branch=new_branch,
        )

    def iter_git_tree(self, branch):
        return self.provider.iter_git_tree(branch=branch, repo=self.user_repo)

    def iter_updates(self, initial):
        return self.req_bundle.get_updates(initial=initial, config=self.config)

    def iter_changes(self, initial, updates):
        return iter(updates)

    # if this function gets updated, the gist at https://gist.github.com/jayfk/45862b05836701b49b01
    # needs to be updated too
    def get_all_requirements(self):
        if self.config.search:
            logger.info("Searching requirement files")
            for file_type, path in self.iter_git_tree(self.config.branch):
                if file_type == "blob":
                    if "requirements" in path:
                        if path.endswith("txt") or path.endswith("pip"):
                            self.add_requirement_file(path)
        for req_file in self.config.requirements:
            self.add_requirement_file(req_file.path)

    # if this function gets updated, the gist at https://gist.github.com/jayfk/c6509bbaf4429052ca3f
    # needs to be updated too
    def add_requirement_file(self, path):
        logger.info("Adding requirement file at {}".format(path))
        if not self.req_bundle.has_file_in_path(path):
            req_file = self.provider.get_requirement_file(
                path=path, repo=self.user_repo, branch=self.config.branch)
            if req_file is not None:
                self.req_bundle.append(req_file)
                for other_file in req_file.other_files:
                    self.add_requirement_file(other_file)


class DryBot(Bot):
    def commit_and_pull(self, initial, base_branch, new_branch, title, body,
                        updates):  # pragma: no cover
        return None
