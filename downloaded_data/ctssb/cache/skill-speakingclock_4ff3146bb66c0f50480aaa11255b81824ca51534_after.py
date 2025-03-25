from time import gmtime, strftime

from opsdroid.skills import match_crontab
from opsdroid.message import Message

@match_crontab('* * * * *')
async def speaking_clock(opsdroid):
    connector = opsdroid.default_connector
    message = Message("", None, connector.default_room, connector)
    await message.respond(strftime("The time is now %H:%M", gmtime()))
