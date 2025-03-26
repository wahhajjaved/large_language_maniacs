"""Movement commands."""

from .base import Command
from db import Direction
from socials import socials
from programming import as_function


class Go(Command):
    """Go in a specific direction."""

    def on_init(self):
        self.add_argument('direction', help='The direction to go in.')

    def func(self, character, args, rest):
        x = character.location.match_exit(args.direction)
        if x is None:
            self.exit(message='You cannot go that way.')
        if character.resting:
            self.exit(message='You must stand up first.')
        if x.can_use is not None and not as_function(
            x.can_use, character=character
        ):
            return  # They cannot pass.
        character.do_social(x.use_msg.format(character.style), _others=[x])
        d = Direction.query(name=x.name).first()
        if d is None:
            msg = f'{character.name} arrives.'
        else:
            msg = socials.get_strings(
                x.arrive_msg, [character], direction=d.opposite_string
            )
        x.target.broadcast(msg[-1])
        character.move(x.target)
        character.show_location()
