from celery import shared_task
from django_discord_connector.models import DiscordUser, DiscordGroup, DiscordClient, DiscordChannel, DiscordToken
from django_discord_connector.request import DiscordRequest
from django.contrib.auth.models import Group
from django.conf import settings
from http.client import responses
import logging


logger = logging.getLogger(__name__)


"""
Cron Tasks
These are tasks to be set up on a crontab schedule
"""


@shared_task
def sync_all_discord_users_accounts():
    """
    Updates discord users with tokens, removes users without tokens.
    """
    for discord_user in DiscordUser.objects.all().exclude(discord_token__isnull=True):
        update_discord_user.apply_async(args=[discord_user.external_id])

    for discord_user in DiscordUser.objects.filter(discord_token__isnull=True):
        remove_discord_user.apply_async(args=[discord_user.external_id])


@shared_task
def remote_sync_all_discord_users_groups():
    for discord_user in DiscordUser.objects.all().exclude(discord_token__isnull=True):
        remote_sync_discord_user_discord_groups.apply_async(
            args=[discord_user.external_id])


@shared_task
def verify_all_discord_users_groups():
    for discord_user in DiscordUser.objects.all().exclude(discord_token__isnull=True):
        verify_discord_user_groups.apply_async(
            args=[discord_user.external_id]
        )


@shared_task
def enforce_discord_nicknames():
    """
    Paid feature request: https://github.com/KryptedGaming/krypted/issues/302
    Quick task to pass over all DiscordUsers and enforce nickames as EVE Online character names
    """

    user_settings = DiscordClient.get_instance()
    schema = user_settings.name_enforcement_schema
    if not schema:
        return
    eve_online_variables = ["%character", "%corporation", "%alliance"]

    if any(variable in schema for variable in eve_online_variables):
        from django_eveonline_connector.models import PrimaryEveCharacterAssociation
        is_eve_online_variables = True
    else:
        is_eve_online_variables = False

    # Lazy algorithm, would rather check for names that don't follow nickname schema in future
    for discord_user in DiscordUser.objects.all():
        try:
            user = DiscordToken.objects.get(discord_user=discord_user).user
            name = schema
            if '%username' in name:
                name = name.replace("%username", user.username)

            if is_eve_online_variables:
                character = PrimaryEveCharacterAssociation.objects.get(
                    user=user).character
                if '%character' in name:
                    name = name.replace("%character", character.name)
                if '%corporation' in name:
                    name = name.replace(
                        "%corporation", character.corporation.ticker)
                if '%alliance' in name:
                    name = name.replace(
                        "%alliance", character.corporation.alliance.ticker)

            # only call updates for names that have changed (can call more freqeuently)
            if discord_user.nickname != name:
                discord_user.nickname = name
                discord_user.save()
                update_remote_discord_user_nickname.apply_async(
                    args=[discord_user.external_id])

        except PrimaryEveCharacterAssociation.DoesNotExist:
            logger.info(
                f"Failed to update nickname for {discord_user}, no EVE Online character set.")
        except DiscordToken.DoesNotExist:
            logger.info(
                f"Failed to update nickname for {discord_user}, missing Discord token.")
        except Exception as e:
            logger.error(
                f"Failed to update nickname for {discord_user}, unknown exception. See additional logs.")
            logger.exception(e)


@shared_task
def sync_discord_groups():
    response = DiscordRequest.get_instance().get_guild_roles()
    if responses[response.status_code] != 'OK':
        raise Exception(
            "Failed to pull discord groups. Check your Discord Settings.")
    # convert role list into dict of IDs
    discord_guild_roles = {
        int(role['id']): role for role in response.json()}
    discord_local_roles = list(DiscordGroup.objects.all().values_list(
        'external_id', flat=True))  # get list of local roles we know about from database

    # build role change lists
    discord_roles_to_remove = set(
        discord_local_roles) - set(discord_guild_roles.keys())
    discord_roles_to_add = set(
        discord_guild_roles.keys()) - set(discord_local_roles)

    for role_id in discord_roles_to_remove:
        logger.info("Removing Discord role %s" % role_id)
        DiscordGroup.objects.get(external_id=role_id).delete()

    for role_id in discord_roles_to_add:
        if discord_guild_roles[role_id]['name'] in ['@everyone']:
            logger.info("Skipping Discord role %s" % role_id)
            continue
        if not DiscordGroup.objects.filter(external_id=role_id).exists():
            logger.info("Creating Discord role %s" % role_id)
            DiscordGroup.objects.create(
                name=discord_guild_roles[role_id]['name'], external_id=role_id)
        else:
            logger.info("Updating name for Discord role %s" % role_id)
            DiscordGroup.objects.update(
                name=discord_guild_roles[role_id]['name'])


@shared_task
def sync_discord_channels():
    discord_guild_channels = {
        channel['id']: channel for channel in DiscordRequest.get_instance().get_guild_channels().json()}
    discord_local_channels = list(DiscordChannel.objects.all().values_list(
        'external_id', flat=True))

    # build channel change lists
    discord_channels_to_remove = set(
        discord_local_channels) - set(discord_guild_channels.keys())
    discord_channels_to_add = set(
        discord_guild_channels.keys()) - set(discord_local_channels)

    for channel_id in discord_channels_to_remove:
        DiscordChannel.objects.get(external_id=channel_id).delete()

    for channel_id in discord_channels_to_add:
        if discord_guild_channels[channel_id]['type'] == 0:
            DiscordChannel.objects.create(
                external_id=channel_id, name="#%s" % discord_guild_channels[channel_id]['name'])


"""
Discord User tasks
Tasks related to keeping DiscordUser objects up to date.
"""


@shared_task(rate_limit="1/s")
def update_remote_discord_user_nickname(discord_user_id):
    discord_user = DiscordUser.objects.get(external_id=discord_user_id)
    response = DiscordRequest.get_instance().update_discord_user_nickname(
        discord_user_id, discord_user.nickname.split("#")[0])
    if responses[response.status_code] == 'No Content':
        logger.info("Successfully updated Discord nickname for %s" %
                    discord_user_id)
    elif responses[response.status_code] == "Too Many Requests":
        logger.warning(
            "[RATELIMIT] Updating nickname for Discord User %s" % (discord_user_id))
        update_remote_discord_user_nickname.apply_async(
            args=[discord_user_id], countdown=600)
    else:
        logger.error(
            "[%s Response] Failed to update discord user nickname" % response.status_code)


@shared_task(rate_limit="1/s")
def update_discord_user(discord_user_id):
    discord_user = DiscordUser.objects.get(external_id=discord_user_id)
    response = DiscordRequest.get_instance().get_discord_user(discord_user_id)
    if responses[response.status_code] == 'OK':
        response = response.json()

        discord_user.username = response['user']['username'] + \
            "#" + response['user']['discriminator']

        if 'nick' in response and response['nick']:
            discord_user.nickname = response['nick'] + \
                "#" + response['user']['discriminator']
        else:
            discord_user.nickname = discord_user.username

        discord_user.save()
    else:
        if 'code' in response.json():
            if response.json()['code'] == 10007:
                logger.info(
                    f"Deleting discord user {discord_user_id}, reason: LEFT SERVER")
                discord_user.delete()
                return
        raise Exception(
            "[%s Response] Failed to update discord user" % response.status_code)


@shared_task()
def remove_discord_user(discord_user_id):
    discord_user = DiscordUser.objects.filter(
        external_id=discord_user_id).first()

    if not discord_user:
        return

    for discord_group in DiscordGroup.objects.all():
        # only purge groups that are mapped
        if discord_group.group:
            remove_discord_group_from_discord_user(
                discord_group.external_id, discord_user.external_id)

    discord_user.delete()


@shared_task(rate_limit="1/s")
def remote_sync_discord_user_discord_groups(discord_user_id):
    discord_user = DiscordUser.objects.get(external_id=discord_user_id)
    response = DiscordRequest.get_instance().get_discord_user(discord_user_id)
    discord_user_remote_role_ids = set(
        [int(role_id) for role_id in response.json()['roles']])

    discord_group_managed_ids = set(DiscordGroup.objects.exclude(
        group=None).values_list('external_id', flat=True))
    discord_user_local_role_ids = set(
        discord_user.groups.all().values_list('external_id', flat=True))

    logger.debug("remote: %s" % discord_user_remote_role_ids)
    logger.debug("local: %s" % discord_user_local_role_ids)
    # Test value DJANGO_DISCORD_REMOTE_PRIORITY in settings, but make it optional
    try:
        if settings.DJANGO_DISCORD_REMOTE_PRIORITY:
            remote_priority = True
        else:
            remote_priority = False
    except AttributeError:
        remote_priority = False

    if responses[response.status_code] == 'OK':
        if remote_priority:
            logger.info(
                "Setting DJANGO_DISCORD_REMOTE_PRIORITY set. Adding groups to local DiscordUser store.")
            discord_groups_to_add = discord_user_remote_role_ids - discord_user_local_role_ids
            discord_groups_to_remove = discord_user_local_role_ids - discord_user_remote_role_ids
            logger.info("Discord groups to add: %s" % discord_groups_to_add)
            logger.info("Discord groups to remove: %s" %
                        discord_groups_to_remove)
            for discord_group_id in discord_groups_to_add:
                if discord_group_id not in discord_group_managed_ids:
                    continue
                discord_group = DiscordGroup.objects.get(
                    external_id=discord_group_id)
                discord_user.groups.add(discord_group)
                if discord_group.group:
                    discord_user.discord_token.user.groups.add(
                        discord_group.group)

            for discord_group_id in discord_groups_to_remove:
                if discord_group_id not in discord_group_managed_ids:
                    continue
                discord_group = DiscordGroup.objects.get(
                    external_id=discord_group_id)
                discord_user.groups.remove(discord_group)
                if discord_group.group:
                    discord_user.discord_token.user.groups.remove(
                        discord_group.group)
        else:
            logger.info(
                "Setting DJANGO_DISCORD_REMOTE_PRIORITY unset. Removing groups from remote DiscordUser.")
            discord_groups_to_remove = discord_user_remote_role_ids - discord_user_local_role_ids
            discord_groups_to_add = discord_user_local_role_ids - discord_user_remote_role_ids
            logger.info("Discord groups to add: %s" % discord_groups_to_add)
            logger.info("Discord groups to remove: %s" %
                        discord_groups_to_remove)
            for discord_group_id in discord_groups_to_remove:
                if discord_group_id not in discord_group_managed_ids:
                    continue
                remove_discord_group_from_discord_user.apply_async(
                    args=[discord_group_id, discord_user_id])
                logger.info("Removing group %s from user %s due to mismatched local groups" % (
                    discord_group_id, discord_user_id))

            for discord_group_id in discord_groups_to_add:
                if discord_group_id not in discord_group_managed_ids:
                    continue
                add_discord_group_to_discord_user.apply_async(
                    args=[discord_group_id, discord_user_id])
                logger.info("Adding group %s to user %s due to mismatched local groups" % (
                    discord_group_id, discord_user_id))

    else:
        raise Exception("[%s Response] Failed to sync discord groups for user %s" % (
            response.status_code, discord_user_id))


@shared_task()
def verify_discord_user_groups(discord_user_id):
    discord_user = DiscordUser.objects.get(external_id=discord_user_id)

    # Test value DJANGO_DISCORD_REMOTE_PRIORITY in settings, but make it optional
    try:
        if settings.DJANGO_DISCORD_REMOTE_PRIORITY:
            remote_priority = True
        else:
            remote_priority = False
    except AttributeError:
        remote_priority = False

    if remote_priority:
        user = discord_user.discord_token.user
        django_enabled_group_ids = set(
            [group.pk for group in discord_user.discord_token.user.groups.all()])
        discord_enabled_group_ids = set(
            [discord_group.group.pk for discord_group in discord_user.groups.all()])
        group_pks_to_add = discord_enabled_group_ids - django_enabled_group_ids
        group_pks_to_remove = django_enabled_group_ids - discord_enabled_group_ids

        for group_pk in group_pks_to_add:
            group = Group.objects.get(pk=group_pk)
            logger.warning(
                "Local group %s out of sync with Discord remote. Check your setup, this shouldn't happen." % group)
            user.groups.add(group)
        for group_pk in group_pks_to_remove:
            group = Group.objects.get(pk=group_pk)
            logger.warning(
                "Local group %s out of sync with Discord remote. Check your setup, this shouldn't happen." % group)
            user.groups.remove(Group.objects.get(pk=group_pk))
    else:
        user = discord_user.discord_token.user
        django_enabled_group_ids = set(
            [group.pk for group in discord_user.discord_token.user.groups.all()])
        discord_enabled_group_ids = set()
        for discord_group in discord_user.groups.all():
            if discord_group.group:
                discord_enabled_group_ids.add(discord_group.group.pk)
        group_pks_to_add = django_enabled_group_ids - discord_enabled_group_ids
        group_pks_to_remove = discord_enabled_group_ids - django_enabled_group_ids

        for group_pk in group_pks_to_remove:
            discord_groups = DiscordGroup.objects.filter(group__pk=group_pk)
            for discord_group in discord_groups:
                remove_discord_group_from_discord_user.apply_async(
                    args=[discord_group.external_id, discord_user_id])
                logger.info("Removing group %s from user %s due to mismatched local groups" % (
                    discord_group.external_id, discord_user_id))

        for group_pk in group_pks_to_add:
            discord_groups = DiscordGroup.objects.filter(group__pk=group_pk)
            for discord_group in discord_groups:
                add_discord_group_to_discord_user.apply_async(
                    args=[discord_group.external_id, discord_user_id])
                logger.info("Adding group %s from user %s due to mismatched local groups" % (
                    discord_group.external_id, discord_user_id))


@shared_task(rate_limit="1/s")
def add_discord_group_to_discord_user(discord_group_id, discord_user_id):
    discord_group = DiscordGroup.objects.get(external_id=discord_group_id)
    discord_user = DiscordUser.objects.get(external_id=discord_user_id)
    response = DiscordRequest.get_instance().add_role_to_user(
        discord_group_id, discord_user_id)
    if responses[response.status_code] == "No Content":
        logger.info("Succesfully added Discord role %s to Discord user %s" % (
            discord_group_id, discord_user_id))
        discord_user.groups.add(discord_group)
        try:
            if discord_group.group and discord_group.group not in discord_user.discord_token.user.groups.all():
                discord_user.discord_token.user.groups.add(discord_group.group)
        except DiscordUser.discord_token.RelatedObjectDoesNotExist:
            pass

    elif responses[response.status_code] == "Too Many Requests":
        logger.warning("[RATELIMIT] adding Discord group %s to Discord User %s" % (
            discord_group_id, discord_user_id))
        add_discord_group_to_discord_user.apply_async(
            args=[discord_group_id, discord_user_id], countdown=600)
    else:
        if 'code' in response.json():
            if response.json()['code'] == 10007:
                logger.info(
                    f"Deleting discord user {discord_user_id}, reason: LEFT SERVER")
                discord_user.delete()
                return
        raise Exception("[%s Response] Failed to add discord group %s to discord user %s: %s" % (
            response.status_code, discord_group_id, discord_user_id, response.json()))


@shared_task(rate_limit="1/s")
def remove_discord_group_from_discord_user(discord_group_id, discord_user_id):
    discord_group = DiscordGroup.objects.get(external_id=discord_group_id)
    discord_user = DiscordUser.objects.get(external_id=discord_user_id)
    response = DiscordRequest.get_instance().remove_role_from_user(
        discord_group_id, discord_user_id)
    if responses[response.status_code] == "No Content":
        logger.info("Succesfully removed Discord role %s from Discord user %s" % (
            discord_group_id, discord_user_id))
        discord_user.groups.remove(
            DiscordGroup.objects.get(external_id=discord_group_id))
        try:
            if discord_group.group and discord_group.group in discord_user.discord_token.user.groups.all():
                discord_user.discord_token.user.groups.remove(
                    discord_group.group)
        except DiscordUser.discord_token.RelatedObjectDoesNotExist:
            pass
    elif responses[response.status_code] == "Too Many Requests":
        logger.warning("[RATELIMIT] removing Discord group %s from Discord User %s" % (
            discord_group_id, discord_user_id))
        remove_discord_group_from_discord_user.apply_async(
            args=[discord_group_id, discord_user_id], countdown=600)
    else:
        if 'code' in response.json():
            if response.json()['code'] == 10007:
                logger.info(
                    f"Deleting discord user {discord_user_id}, reason: LEFT SERVER")
                discord_user.delete()
                return
        raise Exception("[%s Response] Failed to remove discord group %s from discord user %s : %s" % (
            response.status_code, discord_group_id, discord_user_id, response.json()))
