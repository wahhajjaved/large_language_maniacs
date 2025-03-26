from tools.password import generate_hash, verify_hash
from services.repository.sql.ideas import idea_repository
from services.repository.sql.users import user_repository

from core import exceptions

from . import idea_entities

import uuid
import arrow


#######################################
## Idea
#######################################

def create_idea(owner, idea_for_create):
    idea = idea_entities.Idea(
        uuid = uuid.uuid4().hex,
        is_active = True,
        title = idea_for_create.title,
        description = idea_for_create.description,
        owner_id = owner.id,
        created_at = arrow.now(),
        is_public = idea_for_create.is_public,
        forked_from = None,
        comments_count = 0,
        reactions_counts = {},
    )
    idea = idea_repository.create(idea)

    if idea_for_create.invited_usernames:
        if idea.is_public:
            raise exceptions.InconsistentData("Only private ideas can have invited users")
        for invited_username in idea_for_create.invited_usernames:
            invited_user = user_repository.retrieve_by_username(invited_username)
            if not invited_user:
                raise exceptions.InconsistentData("Can't find user {}".format(invited_username))
            if invited_user.id == idea.owner_id:
                raise exceptions.InconsistentData("You cannot invite yourself to the idea")
            idea_repository.create_invited(
                idea_entities.IdeaInvited(
                    idea_id = idea.id,
                    user_id = invited_user.id,
                )
            )

    return idea


def update_idea(owner, idea):
    return idea_repository.update(idea)


def list_ideas():
    return idea_repository.list()


def get_idea(idea_uuid):
    return idea_repository.retrieve_by_uuid(idea_uuid)


def promote_idea(user, idea):
    if idea.owner_id != user.id:
        raise exceptions.Forbidden("Only owner can promote an idea")

    idea.deactivate()
    idea_repository.update(idea)

    from core.projects import project_entities
    project = project_entities.Project(
        uuid = uuid.uuid4().hex,
        title = idea.title,
        description = idea.description,
        technologies = [],
        needs = "",
        logo = "",
        piweek_id = 1, # TODO
        idea_from_id = idea.id,
        owner_id = idea.owner_id,
        created_at = arrow.utcnow(),
        comments_count=0,
        reactions_counts={}
    )

    from services.repository.sql.projects import project_repository
    return project_repository.create(project)


#######################################
## Inviteds
#######################################

def invite_users(user, idea, invited_usernames):
    if idea.owner_id != user.id:
        raise exceptions.Forbidden("Only owner can invite users")
    if idea.is_public:
        raise exceptions.InconsistentData("Only private ideas can have invited users")

    for invited_username in invited_usernames:
        invited_user = user_repository.retrieve_by_username(invited_username)
        if not invited_user:
            raise exceptions.InconsistentData("Can't find user {}".format(invited_username))
        if invited_user.id == user.id:
            raise exceptions.InconsistentData("You cannot invite yourself to the idea")
        invited = idea_repository.retrieve_invited(idea.id, invited_user.id)
        if invited:
            raise exceptions.InconsistentData("User {} was already invited to the idea".format(invited_username))

        idea_repository.create_invited(
            idea_entities.IdeaInvited(
                idea_id = idea.id,
                user_id = invited_user.id,
            )
        )

def list_invited(idea):
    return idea_repository.retrieve_invited_list(idea.id)


def remove_invited_user(user, idea, invited_username):
    if idea.owner_id != user.id:
        raise exceptions.Forbidden("Only owner can invite users")
    if idea.is_public:
        raise exceptions.InconsistentData("Only private ideas can have invited users")

    invited_user = user_repository.retrieve_by_username(invited_username)
    if not invited_user:
        raise exceptions.InconsistentData("Can't find user {}".format(invited_username))

    invited = idea_repository.retrieve_invited(idea.id, invited_user.id)
    if not invited:
        raise exceptions.InconsistentData("User {} was not invited to the idea".format(invited_username))

    idea_repository.delete_invited(invited)


#######################################
## Comment
#######################################

def create_comment(owner, idea,  comment_for_create):
    if not idea.is_public and idea.owner_id != owner.id:
        invited = idea_repository.retrieve_invited(idea.id, owner.id)
        if not invited:
            raise exceptions.Forbidden("Only invited users can comment")

    comment = idea_entities.IdeaComment(
        uuid = uuid.uuid4().hex,
        content = comment_for_create.content,
        owner_id = owner.id,
        idea_id = idea.id,
        created_at = arrow.now(),
    )

    idea.increase_comment_count()
    idea_repository.update(idea)

    return idea_repository.create_comment(comment)


def list_comments(idea):
    comments = idea_repository.retrieve_comment_list(idea)
    return comments
