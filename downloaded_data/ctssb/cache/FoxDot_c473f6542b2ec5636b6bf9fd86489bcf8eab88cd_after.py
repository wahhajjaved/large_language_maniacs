"""    
    Players are what make FoxDot make music. They are similar in design to
    SuperCollider's `PDef` and `PBind` combo but with slicker syntax. FoxDot
    uses SuperCollider to *actually* make the sound and does so by triggering
    predefined `SynthDefs` - sort of like definitions of a digital instruments.
    To have a look at the list of `SynthDefs`, you can just `print` them to
    the console:

    ```python
    print(SynthDefs)
    ```

    Each one of these represents a `SynthDef` *object*. These objects are then
    given to Players to play - like giving an instrument to someone in your
    orchestra. To give someone the instrument, `pads`, you use a double arrow
    some code syntax like this:

    ```python
    p1 >> pads()
    ```

    To stop a Player, use the `stop` method e.g. `p1.stop()`. If you want to
    stop all players, you can use the command `Clock.clear()` or the keyboard
    shortcut `Ctrl+.`, which executes this command.

    `p1` is the name of a predefined player object. At startup, FoxDot reserves
    all one- and two-character variable names, such as `x`, `p1`, or `bd` for
    player objects but these can be repurposed if you like. If you want to use
    a variable name for a player object with more than two characters, you just
    instantiate a new `Player` object:

    ```python
    foo = Player()

    foo >> pads()
    ```

    Changing parameters
    -------------------

    By default, player objects play the first note of their default scale (more
    below) with a duration of 1 beat per note. To change the pitch just give the
    `SynthDef` a list of numbers.

    ```python
    p1 >> pads([0,7,6,4])
    ```

    Play multiple pitches together by putting them in round brackets:

    ```python
    p1 >> pads([0,2,4,(0,2,4)])
    ```
    
    When you start FoxDot up, your clock is ticking at 120bpm and your player
    objects are all playing in the major scale. With 8 pitches in the major scale,
    the 0 refers to the first pitch and the 7 refers to the pitch one octave
    higher because Python, like most programming languages, uses zero-indexing.
    To change your scale you can specify a new scale as a keyword argument (see
    the documentation on `Scales` for more information on scales) or change the
    default scale for all player objects.

    ```python
    # Changing scale as a keyword argument
    p1 >> pads([0,7,6,4], scale=Scale.minor)

    # Changing the default scalew (the following are equivalent)
    Scale.default.set("minor")
    Scale.default.set(Scale.minor)
    Scale.default.set([0,2,3,5,7,8,10])

    # See a list of scales
    print Scale.names()

    # Change the tempo (this takes effect at the next bar)
    Clock.bpm = 144
    ```

    To change the rhythm of your player object, specify the durations using
    the `dur` keyword. Other keywords can be specified, such as `oct` for the
    octave and `sus` for the sustain, which is the same as the duration by
    default.

    ```python
    p1 >> pads([0,7,6,4], dur=[1,1/2,1/4,1/4], oct=6, sus=1)

    # See a list of possible keyword arguments
    print(Player.get_attributes())
    ```

    Using the `play` SynthDef
    -------------------------

    There is a special case SynthDef object called `play` which allows you
    to play short audio files rather than specify pitches. In this case
    you use a string of characters as the first argument where each character
    refers to a different folder of audio files. You can see more information
    by evaluating `print(Samples)`. The following line of code creates
    a basic drum beat:

    ```python
    d1 >> play("x-o-")
    ```

    To play multiple patterns simultaneously, you can create a new `play` object. This
    is useful if you want to have different attributes for each player.

    ```python
    bd >> play("x( x)  ", dur=1)
    hh >> play("---[--]", dur=[1/2,1/2,1/4], rate=4)
    sn >> play("  o ", rate=(.9,1), pan=(-1,1))
    ```    

    Grouping characters in round brackets laces the pattern so that on each
    play through of the sequence of samples, the next character in the group's
    sample is played. The sequence `(xo)---` would be played back as if it
    were entered `x---o---`. Using square brackets will force the enclosed samples
    to played in the same time span as a single character e.g. `--[--]` will play
    two hi-hat hits at a half beat then two at a quarter beat. You can play a
    random sample from a selection by using curly braces in your Play String
    like so:

    ```
    d1 >> play("x-o{-[--]o[-o]}")
    ```

    FoxDot Player Object Keywords
    -----------------------------

    dur - Durations (defaults to 1 and 1/2 for the Sample Player)

    sus - Sustain (defaults to `dur`)

    amp - Amplitude (defaults to 1)

    rate - Variable keyword used for misc. changes to a signal. E.g. Playback rate of the Sample Player (defaults to 1)

    delay - A duration of time to wait before sending the information to SuperCollider (defaults to 0)

    sample - Special keyword for Sample Players; selects another audio file from the bank of samples for a sample character.
    

"""

from __future__ import absolute_import, division, print_function

from os.path import dirname
from random import shuffle, choice
from copy import copy, deepcopy

from .Settings import SamplePlayer, LoopPlayer
from .Code import WarningMsg, debug_stdout
from .SCLang.SynthDef import SynthDefProxy, SynthDef, SynthDefs
from .Effects import FxList
from .Utils import stdout
from .Buffers import Samples

from .Key import *
from .Repeat import *
from .Patterns import *
from .Midi import *

from .Root import Root
from .Scale import Scale

from .Bang import Bang

from .TimeVar import TimeVar

class Player(Repeatable):

    """
    FoxDot generates music by creating instances of `Player` and giving them instructions
    to follow. At startup FoxDot creates many instances of `Player` and assigns them to
    any valid two character variable. This is so that when you start playing you don't 
    have to worry about typing `myPlayer = Player()` and `myPlayer_2 = Player()` every
    time you want to do something new. Of course there is nothing stopping you from 
    doing that if yo so wish.

    Instances of `Player` are given instructions to generate music using the `>>` syntax,
    overriding the bitshift operator, and should be given an instance of `SynthDefProxy`.
    A `SynthDefProxy` is created when calling an instance of `SynthDef` - these are the
    "instruments" used by player objects and are written in SuperCollider code. You can
    see more information about these in the `SCLang` module. Below describes how to assign
    a `SynthDefProxy` of the `SynthDef` `pads` to a `Player` instance called `p1`:

    ```python
    # Calling pads as if it were a function returns a 
    # pads SynthDefProxy object which is assigned to p1
    p1 >> pads()

    # You could store several instances and assign them at different times
    proxy_1 = pads([0,1,2,3], dur=1/2)
    proxy_2 = pads([4,5,6,7], dur=1)

    p1 >> proxy_1 # Assign the first to p1
    p1 >> proxy_2 # This replaces the instructions being followed by p1
    ```
    """

    # Set private values

    debug = 0

    __vars = []
    __init = False

    # Really need to tidy this up

    keywords   = ('degree', 'oct', 'freq', 'dur', 'delay', 'buf',
                  'blur', 'amplify', 'scale', 'bpm', 'sample', "env")

    envelope_keywords = ("atk", "decay", "rel", "legato", "curve", "gain")

    # Base attributes
    
    base_attributes = ('sus', 'fmod', 'pan', 'rate', 'amp', 'midinote', 'channel') 

    required_keys = ("amp", "sus")
    
    internal_keywords = tuple(value for value in keywords if value != "degree")

    # Aliases

    alias = { "pitch" : "degree",
              "char"  : "degree" }

    fx_attributes = FxList.all_kwargs()
    fx_keys       = FxList.kwargs()

    # Load default sample bank
    samples = Samples

    # Set in __init__.py
    metro   = None

    default_scale = Scale.default()
    default_root  = Root.default()

    after_update_methods = ["stutter"]

    # Tkinter Window
    widget = None

    def __init__(self, name=None):

        # Inherit from repeatable i.e. x.every

        Repeatable.__init__(self)

        self.method_synonyms["->"] = "rshift"
        self.method_synonyms["<-"] = "lshift"
    
        # General setup
        
        self.synthdef = None
        self.id = name

        self.current_event_size   = 0
        self.current_event_length = 0
        self.current_event_depth  = 0

        # Stopping flag
        self.stopping = False
        self.stop_point = 0

        # Reference to other objects in the clock played at the same time
        self.queue_block = None
        self.bus = None

        # The string representation of the degree of the player
        self.playstring = ""

        # Information used in generating OSC messages
        self.buf_delay = []
        self.timestamp = 0
        self.condition = lambda: True
        self.sent_messages = []

        self.case_modulation = {
            "sus"   : lambda val, i, *args, **kwargs: val * float(self.metro.beat_dur()) * float(self.get_key("blur", i, **kwargs)),
            "amp"   : lambda val, i, *args, **kwargs: val * float(self.get_key("amplify", i, **kwargs)),
            "delay" : lambda val, i, *args, **kwargs: val + float(self.get_key("_delay_offset", i, **kwargs))
            }

        # Visual feedback information

        self.envelope    = None
        self.line_number = None
        self.whitespace  = None
        self.bang_kwargs = {}

        # Keeps track of which note to play etc

        self.event_index = 0
        self.event_n = 0
        self.notes_played = 0
        self.event = {}

        # Used for checking clock updates

        self.current_dur = None
        self.old_pattern_dur = None
        self.old_dur = None
        
        self.isplaying = False
        self.isAlive = True

        # These dicts contain the attribute and modifier values that are sent to SuperCollider     

        self.attr  = {}
        self.modifier = Pattern()
        self.mod_data = 0

        # Keyword arguments that are used internally

        self.scale = None
        self.offset  = 0
        self.following = None
        
        # List the internal variables we don't want to send to SuperCollider

        self.__vars = list(self.__dict__.keys())
        self.__init = True

        self.reset()

    # Class methods

    @classmethod
    def get_attributes(cls):
        """ Returns a list of possible keyword arguments for FoxDot players and effects """
        return cls.keywords + cls.base_attributes + cls.fx_attributes

    @classmethod
    def Attributes(cls):
        """ To be replaced by `Player.get_attributes()` """
        return cls.get_attributes()

    @classmethod
    def set_clock(cls, tempo_clock):
        cls.metro = tempo_clock

    # Should this also be instance method?
    @classmethod
    def set_sample_bank(cls, sample_bank):
        cls.samples = sample_bank

    # Player Object Manipulation
    
    def __rshift__(self, other):
        """ Handles the allocation of SynthDef objects using >> syntax, other must be
            an instance of `SynthDefProxy`, which is usually created when calling a
            `SynthDef`
        """
        
        if isinstance(other, SynthDefProxy):
            # Call the update method
            self.update(other.name, other.degree, **other.kwargs)
            
            # Perform any methods
            
            for method, arguments in other.methods:
            
                args, kwargs = arguments
            
                getattr(self, method).__call__(*args, **kwargs)
            
            # Add the modifier
            
            self + other.mod # need to account for minus
            
            return self
        
        raise TypeError("{} is an innapropriate argument type for PlayerObject".format(other))

        return self

    def test_for_circular_reference(self, attr, value, last_parent=None, last_key=None):
        """ Used to raise an exception if a player's attribute refers to itself e.g. `p1 >> pads(dur=p1.dur)` """

        # If we are setting a group of values, check each one in turn

        if isinstance(value, PGroup):
            
            for item in value:
            
                self.test_for_circular_reference(attr, item, last_parent,  last_key)

        elif isinstance(value, PlayerKey):
          
            # If the original Player is *this* player and we are referencing the same attr, throw and exception
         
            if value.parent is self and attr == value.key:

                ident_self  = "{}.{}".format(self.id if self.id is not None else str(self), attr)
                
                if last_parent is not None:
                    
                    ident_other = "{}.{}".format(last_parent.id if last_parent.id is not None else str(last_parent), last_key)
                
                else:
                
                    ident_other = ident_self

                err = "Circular reference found: {} to itself via {}".format(ident_self, ident_other)
                
                raise ValueError(err)
            
            # If we get the same parent and key, stop

            elif last_parent == value.parent and last_key == value.key:
            
                return
            
            else:

                # Check if other values in the parent might have a circular reference e.g. p1 >> pads([0,1,p2.degree])
            
                for item in value.parent.attr[value.key]:
            
                    self.test_for_circular_reference(attr, item, last_parent=value.parent, last_key=value.key)
        return
       
    def __setattr__(self, name, value):

        # Possibly replace with slots?

        if self.__init:

            # Force the data into a Pattern if the attribute is used with SuperCollider
            
            if name not in self.__vars:

                # Get any alias

                name = self.alias.get(name, name)

                if name == "dur":

                    value, self._delay_offset = CalculateDelaysFromDur(value)

                value = asStream(value)

                # raise a ValueError if trying to reference itself -- doesn't handle indirect references to itself

                for item in value:

                    self.test_for_circular_reference(name, item)

                # Update the attribute dict
                
                self.attr[name] = value

                # keep track of what values we change with +-

                if (self.synthdef == SamplePlayer and name == "sample") or (self.synthdef != SamplePlayer and name == "degree"):

                    self.modifier = value

                # Update any playerkey

                if name in self.__dict__:

                    if isinstance(self.__dict__[name], PlayerKey):

                        self.__dict__[name].update_pattern()
                else:

                    self.update_player_key(name, self.now(name), 0) # self.now might be an issue

                return
            
        self.__dict__[name] = value
        return

    def __getattr__(self, name):
        return self.__dict__[self.alias.get(name, name)]

    def __getitem__(self, name):
        if self.__init:
            if name not in self.__vars:
                return self.attr[name]
            pass
        return self.__dict__[name]

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return not self is other

    # --- Startup methods

    def reset(self):
        """ Sets all Player attributes to 0 unless their default is specified by an effect """

        # Add all keywords to the dict, then set non-zero defaults

        reset = []

        for key in Player.Attributes():

            if key not in ("scale", "dur", "sus", "blur", "amp",
                            "amplify", "degree", "oct", "bpm"):

                setattr(self, key, 0)

            reset.append(key)

        # Set any non zero defaults for effects, e.g. verb=0.25

        for key in Player.fx_attributes:

            value = FxList.defaults[key]

            setattr(self, key, value)

            reset.append(key)

        # Any other attribute that might have been used - set to 0

        for key in self.attr:

            if key not in reset:

                setattr(self, key, 0)

        # Set any non-zero values for FoxDot

        # Sustain & Legato
        self.sus     = 0.5 if self.synthdef == SamplePlayer else 1
        self.blur    = 1

        # Amplitude
        self.amp     = 1
        self.amplify = 1

        # Duration of notes
        self.dur     = 0.5 if self.synthdef == SamplePlayer else 1

        # Modifier for affecting delay
        self._delay_offset = 0

        # Degree of scale / Characters of samples
        self.degree  = " " if self.synthdef is SamplePlayer else 0

        # Octave of the note
        self.oct     = 5
        
        # Tempo
        self.bpm     = None
        
        return self

    # --- Update methods

    def __call__(self, **kwargs):
        """ Sends the next osc message event to SuperCollider and schedules this
            Player in the clock based on the current clock time and this player's
            current duration value. """

        # If stopping, kill the event

        if self.stopping and self.metro.now() >= self.stop_point:
            
            self.kill()
            
            return

        # If the duration has changed, work out where the internal markers should be

        # This could be in its own private function

        force_count = kwargs.get("count", False)
        dur_updated = self.dur_updated()

        if dur_updated or force_count is True:

            try:

                self.event_n, self.event_index = self.count(self.event_index if not force_count else None)

            except TypeError as e:

                print(e)

                print("TypeError: Innappropriate argument type for 'dur'")

        # Get the current state -- tidy this up

        dur = 0

        while True:

            # This could be in a separate method

            self.get_event()
            
            # Set a 'None' to 0

            if self.event['dur'] is None:

                dur = 0

            # If there are more than one dur (happens sometimes because of threading), only use first

            try:

                if len(self.event['dur']) > 0:

                    self.event['dur'] = self.event['dur'][0]                    

            except TypeError:

                pass

            finally:

                dur = float(self.event['dur'])

            # Skip events with durations of 0

            if dur == 0:

                self.event_n += 1

            else:

                break

        # Play the note

        self.sent_messages = []
        
        self.send(verbose=(self.metro.solo == self and kwargs.get('verbose', True) and type(self.event['dur']) != rest))
        
        # If using custom bpm

        if self.event['bpm'] is not None:

            try:

                tempo_shift = float(self.metro.bpm) / float(self.event['bpm'])

            except (AttributeError, TypeError, ZeroDivisionError):

                tempo_shift = 1

            dur *= tempo_shift

        # Schedule the next event

        self.event_index = self.event_index + dur

        self.metro.schedule(self, self.event_index, kwargs={})

        # Change internal marker

        self.event_n += 1 
        self.notes_played += 1

        return

    def count(self, time=None, event_after=False):
        """ Counts the number of events that will have taken place between 0 and `time`. If
            `time` is not specified the function uses self.metro.now(). Setting `event_after`
            to `True` will find the next event *after* `time`"""

        n = 0
        acc = 0
        dur = 0
        now = (time if time is not None else self.metro.now())
        # bpm = float(self.metro.bpm if self.bpm == None else self.bpm) # TODO: use this to better caclulate event_index -- why?

        durations = self.rhythm() if self.current_dur is None else self.current_dur
        total_dur = float(sum(durations))

        if total_dur == 0:

            WarningMsg("Player object has a total duration of 0. Set to 1")

            durations = [1]
            total_dur =  1 
            self.dur  =  1
    
        acc = now - (now % total_dur)

        try:

            n = int(len(durations) * (acc / total_dur))

        except TypeError as e:

            WarningMsg(e)

            self.stop()

            return 0, 0

        if acc != now:

            while True:

                dur = float(modi(durations, n))

                if acc + dur == now:

                    acc += dur

                    n += 1

                    break

                elif acc + dur > now:

                    if event_after:

                        acc += dur
                        n += 1

                    break

                else:
                    
                    acc += dur
                    n += 1

        # Returns value for self.event_n and self.event_index

        return n, acc

    def dur_updated(self):
        """ Returns True if the players duration has changed since the last call """
        dur = self.rhythm()
        if dur != self.old_dur:
            self.old_dur = dur
            return True
        return False


    def rhythm(self):
        """ Returns the "now" value of the duration """
        rhythm = []
        for value in self.attr['dur']:
            if isinstance(value, TimeVar):
                rhythm.append(value.now())
            else:
                rhythm.append(value)
        self.current_dur = asStream(rhythm)
        return self.current_dur

    def update(self, synthdef, degree, **kwargs):
        """ Updates the attributes of the player. Called using the >> syntax.
        """

        # SynthDef name
        
        self.synthdef = synthdef

        # Make sure all values are reset to start

        if self.isplaying is False:

            self.reset() # <-- need to reset effects

        # If there is a designated solo player when updating, add this at next bar
        
        if self.metro.solo.active() and self.metro.solo != self:

            self.metro.schedule(lambda *args, **kwargs: self.metro.solo.add(self), self.metro.next_bar())

        # Update the attribute values

        special_cases = ["scale", "root", "dur"]

        # Set the degree

        if synthdef == SamplePlayer:

            if type(degree) == str:

                self.playstring = degree

            else:

                self.playstring = None

            if degree is not None:

                setattr(self, "degree", degree if len(degree) > 0 else " ")

        elif degree is not None:

            self.playstring = str(degree) # this doesn't work for var!

            setattr(self, "degree", degree)

        # Set special case attributes

        self.scale = kwargs.get("scale", self.__class__.default_scale )
        self.root  = kwargs.get("root",  self.__class__.default_root )

        # If only duration is specified, set sustain to that value also

        if "dur" in kwargs:

            # If we use tuples / PGroups in setting duration, use it to modify delay using the PDur algorithm

            setattr(self, "dur", kwargs["dur"])

            if "sus" not in kwargs:

                self.sus = self.attr['dur']

        # Set any other attributes

        for name, value in kwargs.items():

            if name not in special_cases:

                setattr(self, name, value)

        # Calculate new position if not already playing

        if self.isplaying is False:

            # Add to clock
            
            self.isplaying = True
            self.stopping = False

            # If we want to update now, set the start point to now

            if kwargs.get("now", False) == True:

                start_point = self.metro.now()

            else:
            
                start_point = self.metro.next_bar()

            self.event_n = 0

            self.event_n, self.event_index = self.count(start_point, event_after=True)

            self.metro.schedule(self, self.event_index)

        return self

    def stutter(self, n=2, **kwargs):
        """ Plays the current note n-1 times. You can specify keywords. """

        # Get the current values (this might be called between events)
        
        self.get_event()
        new_event = {}

        n = int(n)

        if self.metro.solo == self and n > 0:

            dur = float(kwargs.get("dur", self.dur)) / n

            delay = 0

            for key, val in kwargs.items():

                new_event[key] = [self.unpack(group_modi(val, i)) for i in range(n-1)]

            # Get PGroup delays

            new_event["timestamp"] = self.metro.osc_message_time()
            
            new_event["delay"] = self.event.get("delay", 0) + asStream([dur * (i+1) for i in range(n-1)])

            self.send(**new_event)
                
        return self

    def lshift(self, n=1):
        """ Plays the event behind """
        self.event_n -= (n+1)
        return self

    def rshift(self, n=1):
        """ Plays the event in front """
        self.event_n += n
        return self

    def spread(self, on=1):
        """ Sets pan to (-1, 1) and pshift to (0, 0.125)"""
        if on:
            self.pan=(-1,1)
            self.pshift=(0,0.125)
        else:
            self.pan=0
            self.pshift=0
        return self

    def reverse(self):
        """ Reverses every attribute stream """
        for attr in self.attr:
            try:
                self.attr[attr] = self.attr[attr].pivot(self.event_n)
            except AttributeError:
                pass
        return self

    def shuffle(self):
        """ Shuffles the degree of a player. """
        # If using a play string for the degree
        if self.synthdef == SamplePlayer and self.playstring is not None:
            # Shuffle the contents of playgroups among the whole string
            new_play_string = PlayString(self.playstring).shuffle()
            new_degree = Pattern(new_play_string).shuffle()
        else:            
            new_degree = self.attr['degree'].shuffle()
        self._replace_degree(new_degree)
        return self

    def mirror(self):
        """ The degree pattern is reversed """
        self._replace_degree(self.attr['degree'].mirror())
        return self

    def rotate(self, n=1):
        """ Rotates the values in the degree by 'n' """
        self._replace_degree(self.attr['degree'].rotate(n))
        return self

    def map(self, key1, key2, mapping):
        """ Sets the attribute for self.key2 to self.key1
            altered with a mapping dictionary.
        """
        self.attr[key2] = self.attr[key1].map(mapping)
        return self

    def smap(self, kwargs):
        """ Like map but maps the degree to the sample attribute
        """
        self.map("degree", "sample", kwargs)
        return self
    
    # --- Misc. Standard Object methods

    def __int__(self):
        return int(self.now('degree'))

    def __float__(self):
        return float(self.now('degree'))

    def __add__(self, data):
        """ Change the degree modifier stream """
        self.mod_data = data
        if self.synthdef == SamplePlayer:
            self.attr['sample'] = self.modifier + self.mod_data
        else:
            self.attr['degree'] = self.modifier + self.mod_data
        return self

    def __sub__(self, data):
        """ Change the degree modifier stream """
        self.mod_data = 0 - data
        if self.synthdef == SamplePlayer:
            self.attr['sample'] = self.modifier + self.mod_data
        else:
            self.attr['degree'] = self.modifier + self.mod_data
        return self

    def __mul__(self, data):
        return self

    def __div__(self, data):
        return self

    # --- Data methods

    def __iter__(self):
        for _, value in self.event.items():
            yield value

    def number_of_layers(self, **kwargs):
        """ Returns the deepest nested item in the event """
        num = 1
        for attr, value in self.event.items():
            value = kwargs.get(attr, value)
            if isinstance(value, PGroup):
                l = pattern_depth(value)
            else:
                l = 1                
            if l >  num:
                num = l
        return num                

    def largest_attribute(self, **kwargs):
        """ Returns the length of the largest nested tuple in the current event dict """

        size = 1
        values = []

        for attr, value in self.event.items():
            value = kwargs.get(attr, value)
            l = get_expanded_len(value)
            if l > size:
                size = l
        return size

    def get_event_length(self, **kwargs):
        sizes = []
        for attr, value in self.event.items():
            value = kwargs.get(attr, value)
            sizes.append( get_expanded_len(value) )
        return LCM(*sizes)

    def number_attr(self, attr):
        """ Returns true if the attribute should be a number """
        return not (self.synthdef == SamplePlayer and attr in ("degree", "freq"))

    def update_player_key(self, key, value, time):
        """  Forces object's dict uses PlayerKey instances
        """
        
        if key not in self.__dict__:

            self.__dict__[key] = PlayerKey(value, parent=self, attr=key)

        elif not isinstance(self.__dict__[key], PlayerKey):

            self.__dict__[key] = PlayerKey(value, parent=self, attr=key) 

        else:

            # Force values if not playing

            if self.isplaying is False:

                self.__dict__[key].set(value, time)

            else:

                self.__dict__[key].update(value, time)

        return

    def update_all_player_keys(self, index, ignore=[], **kwargs):
        delay = float(group_modi(self.event.get('delay', 0), index))
        if delay > 0:
            time  = self.event_index + delay
            # TODO -- avoid scheduling lots of functions
            def delay_update(event, i, t):
                for key in event:
                    if key not in ignore:
                        self.update_player_key(key, group_modi(kwargs.get(key, event.get(key, 0)), i), t)
            self.metro.schedule(delay_update, time, args=(self.event, index, time))
        else:
            for key in self.event.keys():
                if key not in ignore:
                    self.update_player_key(key, group_modi(kwargs.get(key, self.event.get(key, 0)), index), self.event_index)
        return


    # --- Methods for preparing and sending OSC messages to SuperCollider

    def unpack(self, item, debug=False):
        """ Converts a pgroup to floating point values and updates and time var or playerkey relations """

        if isinstance(item, TimeVar):

            item = item.now()

        if isinstance(item, NumberKey):

            # If this *is* the parent, just get the current value

            if item.parent is self:

                self.update_player_key(item.key, self.now(item.key), 0)

                item = item.now()

            elif item.parent in self.queue_block:

                # Update the parent with an up-to-date value

                if not self.queue_block.already_called(item.parent):

                    item.parent.update_player_key(item.key, item.parent.now(item.key), 0)

                else:

                    item.parent.update_player_key(item.key, item.parent.now(item.key, -1), 0)

                item = item.now()


            else:

                item = item.now()

        if isinstance(item, GeneratorPattern):

            # Unpack any generator patterns nested in a PGroup

            item = item.getitem() ## TODO -- get the correct index

        if isinstance(item, PGroup):

            # Make sure any values in the PGroup have their "now" methods called

            item = item.convert_data(self.unpack)    

        return item

    def get_key(self, key, i, **kwargs):
        return group_modi(kwargs.get(key, self.event[key]), i)

    # Private method

    def __get_current_delay(self, i, kwargs):
        delay = float(group_modi(kwargs.get('delay', self.event.get('delay', 0)), i))
        func = self.case_modulation["delay"]
        return func(delay, i)

    def now(self, attr="degree", x=0):
        """ Calculates the values for each attr to send to the server at the current clock time """

        index = self.event_n + x

        try:

            attr_value = self.attr[attr][index]

        except KeyError:

            print(attr, self.attr[attr], index)

        except ZeroDivisionError as e:

            print(self, attr, self.attr[attr], index)
            raise(e)

        if attr_value is not None:

            attr_value = self.unpack(attr_value)

        return attr_value

    def get_prime_funcs(self, event):
        """ Finds and PGroupPrimes in event and returns the modulated event dictionary """
        # Look for PGroupPrimes

        prime_funcs = {}

        for key, value in event.items():

            if isinstance(value, PGroup) and value.has_behaviour():

                name = value.get_name()
                
                getaction = True

                # Only add the largest prime_func for the largest element in the event

                if name in prime_funcs:

                    if len(value) <= len(prime_funcs[name][1]):

                        getaction = False

                if getaction:

                    prime_funcs[name] = [key, value, value.get_behaviour()]

        # Add largest PGroupPrime function

        for name, func in prime_funcs.items():

            prime_call = func[-1]

            if prime_call is not None:

                event = prime_call(event, func[0])

        return event

    def get_event(self):
        """ Returns a dictionary of attr -> now values """

        attributes = copy(self.attr)
        
        for key in attributes:

            if len(attributes[key]) > 0:

                self.event[key] = self.now(key)

        self.event = self.get_prime_funcs(self.event)

        return self

    def new_message(self, index=0, **kwargs):
        """ Returns the header of an osc message to be added to by osc_message() """

        # Start with the envelope
        
        message = {"env": group_modi(kwargs.get("env", self.event['env']), index)}

        if self.synthdef == SamplePlayer:

            degree = group_modi(kwargs.get("degree", self.event['degree']), index)
            sample = group_modi(kwargs.get("sample", self.event["sample"]), index)
            rate   = group_modi(kwargs.get("rate", self.event["rate"]), index)

            if rate < 0:

                sus = group_modi(kwargs.get("sus", self.event["sus"]), index)

                pos = self.metro.beat_dur(sus)

            else:

                pos = 0 
 
            buf  = int(self.samples[str(degree)].bufnum(sample))
            
            message = {'buf': buf, 'pos': pos}

        elif self.synthdef == LoopPlayer:

            pos = group_modi(kwargs.get("degree", self.event["degree"]), index)
            buf = group_modi(kwargs.get("buf", self.event["buf"]), index)

            # Get a user-specified tempo

            given_tempo = group_modi(kwargs.get("tempo", self.event.get("tempo", self.metro.bpm)), index)

            if given_tempo is None:

                tempo = 1

            else:

                tempo = self.metro.bpm / given_tempo

            # Set the position in "beats"

            pos = pos * tempo * self.metro.beat_dur(1)

            # If there is a negative rate, move the pos forward

            rate = group_modi(kwargs.get("rate", self.event["rate"]), index)

            if rate == 0:

                rate = 1

            # Adjust the rate to a given tempo

            rate = tempo * rate

            if rate < 0:

                sus = group_modi(kwargs.get("sus", self.event["sus"]), index)

                pos += self.metro.beat_dur(sus)

            message = {'pos': pos, 'buf': buf, 'rate': rate}

        else:

            degree = group_modi(kwargs.get("degree", self.event["degree"]), index)
            octave = group_modi(kwargs.get("oct", self.event["oct"]), index)
            root   = group_modi(kwargs.get("root", self.event["root"]), index)

            midinote = midi( kwargs.get("scale", self.scale), octave, degree, root )

            freq   = miditofreq(midinote)
            
            message.update({'freq':  freq, 'midinote': midinote})
            
        return message

    def osc_message(self, index=0, **kwargs):
        """ Creates an OSC packet to play a SynthDef in SuperCollider,
            use kwargs to force values in the packet, e.g. pan=1 will force ['pan', 1] """

        fx_dict = {}
        message = self.new_message(index, **kwargs)

        attributes = self.attr.copy()

        # Go through the attr dictionary and add kwargs

        for key in attributes:

            try:

                # Don't use fx keywords or foxdot keywords except "degree"

                if (key not in self.keywords) and (key not in self.fx_attributes or key in self.base_attributes):

                    # Ignore any keys we might already have processed

                    if key in message:

                        continue

                    # Convert to float

                    val = float(group_modi(kwargs.get(key, self.event[key]), index))

                    # Special case modulation

                    if key in self.case_modulation:

                        func = self.case_modulation[key]

                        val = func(val, index, **kwargs)

                    # Only send non-zero values

                    if val != 0 or key in self.required_keys or key in self.envelope_keywords: 

                        message[key] = val

            except KeyError as e:

                WarningMsg("KeyError in function 'osc_message'", key, e)

        # See if any fx_attributes 

        for key in self.fx_keys:

            if key in attributes: 

                # Only use effects where the "title" effect value is not 0

                val = group_modi(kwargs.get(key, self.event[key]), index)

                if val != 0:

                    fx_dict[key] = []

                    # Look for any other attributes require e.g. room and verb

                    for n, sub_key in enumerate(FxList[key].args):

                        if sub_key in self.event:

                            # If the sub_key is another attribute like sus, get it from the message

                            if sub_key in message:

                                val = message[sub_key]

                            # Get the value from the event

                            else:

                                try:

                                    val = group_modi(kwargs.get(sub_key, self.event[sub_key]), index)

                                except TypeError as e:

                                    val = 0

                                except KeyError as e:

                                    del fx_dict[key]

                                    break

                            fx_dict[key] += [sub_key, val]

        return message, fx_dict


    def send(self, **kwargs):
        """ Sends the current event data to SuperCollder.
            Use kwargs to overide values in the current event """

        timestamp = kwargs.get("timestamp", self.queue_block.time)
        verbose   = kwargs.get("verbose", True)
        banged = False
        freq = []
        bufnum = []
        last_msg = None

        self.current_event_length = self.get_event_length(**kwargs)

        for i in range(self.current_event_length):

            # Get the basic osc_msg

            osc_msg, effects = self.osc_message(i, **kwargs)

            # Keep track of the frequency

            if "freq" in osc_msg:

                freq_value = osc_msg["freq"]

                if freq_value not in freq:

                    freq.append(freq_value)

            # Update internal player keys

            self.update_all_player_keys(i, **kwargs)

            if verbose:

                # Look at delays and schedule events later if need be

                delay = self.__get_current_delay(i, kwargs)

                ### ----

                if 'buf' in osc_msg:
                        
                    buf = group_modi(kwargs.get('buf', osc_msg['buf']), i)

                else:

                    buf = 0

                if buf not in bufnum:

                    bufnum.append( buf )

                amp = group_modi(kwargs.get('amp', osc_msg['amp']), i)

                # Any messages with zero amps or 0 buf are not sent <- maybe change that for "now" classes

                if (self.synthdef != SamplePlayer and amp > 0) or (self.synthdef == SamplePlayer and buf > 0 and amp > 0):

                    synthdef = self.get_synth_name(buf)

                    key = (osc_msg, effects, delay)

                    if key not in self.sent_messages:

                        # Keep note of what messages we are sending

                        self.sent_messages.append(key)

                        # Compile the message with time tag

                        delay = self.metro.beat_dur(delay)

                        compiled_msg = self.metro.server.get_bundle(synthdef, osc_msg, effects, timestamp = timestamp + delay)

                        # We can set a condition to only send messages

                        if self.condition(): 

                            self.queue_block.osc_messages.append(compiled_msg)

                        # "bang" the line

                        if not banged and self.bang_kwargs:

                            self.bang()

                            banged = True

        # Store (and update PlayerKeys) the calculated values

        if self.synthdef == SamplePlayer:

            self.buf = bufnum

        else:

            self.freq = freq
        
        return

    def set_queue_block(self, queue_block):
        """ Gives this player object a reference to the other items that are 
            scheduled at the same time """
        self.queue_block = queue_block
        return

    def get_synth_name(self, buf=0):
        """ Returns the real SynthDef name of the player. Useful only for "play" 
            as there is a play1 and play2 SynthDef for playing audio files with
            one or two channels respectively. """
        if self.synthdef == SamplePlayer:
            numChannels = self.samples.getBuffer(buf).channels
            if numChannels == 1:
                synthdef = "play1"
            else:
                synthdef = "play2"
        else:
            synthdef = str(self.synthdef)
        return synthdef

    def addfx(self, **kwargs):
        """ Not implemented - add an effect to the SynthDef bus on SuperCollider
            after it has been triggered. """
        return self

    #: Methods for stop/starting players

    def kill(self):
        """ Removes this object from the Clock and resets itself"""
        
        self.isplaying = False
        
        self.stop_calling_all()
        
        self.reset()

        if self in self.metro.playing:
        
            self.metro.playing.remove(self)
        
        return
        
    def stop(self, N=0):
        
        """ Removes the player from the Tempo clock and changes its internal
            playing state to False in N bars time
            - When N is 0 it stops immediately"""

        self.stopping = True        
        self.stop_point = self.metro.now()

        if N > 0:

            self.stop_point = self.metro.next_bar() + ((N-1) * self.metro.bar_length())

        else:

            self.kill()

        return self

    def pause(self):

        self.isplaying = False

        return self

    def play(self):

        self.isplaying = True
        self.stopping = False
        self.isAlive = True

        self.__call__()

        return self

    # Methods for collaborative performance
    #
    # e.g. follow
    #

    def accompany(self, other, values=[0,2,4], debug=False):
        """ Similar to "follow" but when the value has changed """

        if isinstance(other, self.__class__):

            self.degree = AccompanyKey(other.degree, values, debug)
        
        return self

    def follow(self, lead=False):
        """ Takes a Player object and then follows the notes """

        if isinstance(lead, self.__class__):

            self.degree = lead.degree

        return self

    def only(self):
        """ Stops all players except this one """
        for player in self.metro.playing:
            if player is not self:
                player.stop()
        return self

    def solo(self, action=1):
        """ Silences all players except this player. Undo the solo
            by using `Player.solo(0)` """

        action=int(action)

        if action == 0:

            self.metro.solo.reset()

        elif action == 1:

            self.metro.solo.set(self)

        elif action == 2:

            pass

        return self

    def versus(self, other, key = lambda x: x.freq, f=max):
        """ Takes another Player object and a function that takes
            two player arguments and returns one, default is the higher
            pitched
        """
        if other is not None:
            assert(other.__class__ == self.__class__) # make sure it's using another player
            func = lambda x, y: f(x, y, key=key)
            self.condition  = lambda: func(self, other) == self
            other.condition = lambda: func(self, other) == other
            self._versus = other
        else:
            self.condition  = lambda: True
            self._versus.condition = lambda: True
            self._versus = None
        return self

    

    # Utils

    def num_key_references(self):
        """ Returns the number of 'references' for the
            attr which references the most other players """
        num = 0
        for attr in self.attr.values():
            if isinstance(attr, PlayerKey):
                if attr.num_ref > num:
                    num = attr.num_ref
        return num

    def _replace_degree(self, new_degree):
        # Update the GUI if possible
        #if self.widget:
        #    if self.synthdef == SamplePlayer:
        #        if self.playstring is not None:
        #            # Replace old_string with new string (only works with plain string patterns)
        #            new_string = new_degree.string()
        #            self.widget.addTask(target=self.widget.replace, args=(self.line_number, self.playstring, new_string))
        #            self.playstring = new_string
        #    else:
        #        # Replaces the degree pattern in the widget (experimental)
        #        # self.widget.addTask(target=self.widget.replace_re, args=(self.line_number,), kwargs={'new':str(new_degree)})
        #        self.playstring = str(new_degree)
        setattr(self, 'degree', new_degree)
        return

    def multiply(self, n=2):
        self.attr['degree'] = self.attr['degree'] * n
        return self

    def degrade(self, amount=0.5):
        """ Sets the amp modifier to a random array of 0s and 1s
            amount=0.5 weights the array to equal numbers """
        if float(amount) <= 0:
            self.amplify = 1
        else:
            self.amplify = PwRand([0, self.attr["amplify"]],[int(amount*10), max(10 - int(amount),0)])
        return self

    def changeSynth(self, list_of_synthdefs):
        new_synth = choice(list_of_synthdefs)
        if isinstance(new_synth, SynthDef):
            new_synth = str(new_synth.name)
        self.synthdef = new_synth
        return self

    """

        Modifier Methods
        ----------------

        Other modifiers for affecting the playback of Players

    """

    def offbeat(self, dur=0.5):
        """ Off sets the next event occurence """

        self.attr['delay'] += (dur-self.offset)

        self.offset = dur

        return self

    def strum(self, dur=0.025):
        """ Adds a delay to a Synth Envelope """
        x = self.largest_attribute()
        if x > 1:
            self.delay = asStream([tuple(a * dur for a in range(x))])
        else:
            self.delay = asStream(dur)
        return self

    def __repr__(self):
        if self.id is not None:
            return "<{} - {}>".format(self.id, self.synthdef)
        else:
            return "a '{}' Player Object".format(self.synthdef)

    def info(self):
        s = "Player Instance using '%s' \n\n" % self.synthdef
        s += "ATTRIBUTES\n"
        s += "----------\n\n"
        for attr, val in self.attr.items():
            s += "\t{}\t:{}\n".format(attr, val)
        return s

    def bang(self, **kwargs):
        """
        Triggered when sendNote is called. Responsible for any
        action to be triggered by a note being played. Default action
        is underline the player
        """
        if kwargs:

            self.bang_kwargs = kwargs

        elif self.bang_kwargs:

            bang = Bang(self, self.bang_kwargs)

        return self
        

###### GROUP OBJECT

class Group:

    metro = None

    def __init__(self, *args):

        self.players = list(args)

    def add(self, other):
        self.players.append(other)

    def __len__(self):
        return len(self.players)

    def __str__(self):
        return str(self.players)

    def solo(self, arg=True):

        if self.metro is None:

            self.__class__.metro = Player.metro

        if arg:
            
            self.metro.solo.set(self.players[0])

            for player in self.players[1:]:

                self.metro.solo.add(player)

        else:

            self.metro.solo.reset()

        return self
        

    def iterate(self, dur=4):
        if dur == 0 or dur is None:
            self.amplify=1
        else:
            delay, on = 0, float(dur) / len(self.players)
            for player in self.players:
                player.amplify=TimeVar([0,1,0],[delay, on, dur-delay])
                delay += on
        return           

    def __setattr__(self, name, value):
        try:
            for p in self.players:
                try:
                    setattr(p, name, value)
                except:
                    WarningMsg("'%s' object has no attribute '%s'" % (str(p), name))
        except:
            self.__dict__[name] = value 
        return self        

    def __getattr__(self, name):
        """ Returns a Pattern object containing the desired attribute for each player in the group  """
        if name == "players":
            return self.players
        attributes = GroupAttr()
        for player in self.players:
            if hasattr(player, name):
                attributes.append(getattr(player, name))
        return attributes

class GroupAttr(list):
    def __call__(self, *args, **kwargs):
        for p in self:
            if callable(p):
                p.__call__(*args, **kwargs)

class rest(object):
    ''' Represents a rest when used with a Player's `dur` keyword
    '''
    def __init__(self, dur=1):
        self.dur = dur
    def __repr__(self):
        return "<rest: {}>".format(self.dur)
    def __add__(self, other):
        return rest(self.dur + other)
    def __radd__(self, other):
        return rest(other + self.dur)
    def __sub__(self, other):
        return rest(self.dur - other)
    def __rsub__(self, other):
        return rest(other - self.dur)
    def __mul__(self, other):
        return rest(self.dur * other)
    def __rmul__(self, other):
        return rest(other * self.dur)
    def __div__(self, other):
        return rest(self.dur / other)
    def __rdiv__(self, other):
        return rest(other / self.dur)
    def __truediv__(self, other):
        return rest(float(self.dur) / other)
    def __rtruediv__(self, other):
        return rest(other / float(self.dur))
    def __mod__(self, other):
        return rest(self.dur % other)
    def __rmod__(self, other):
        return rest(other % self.dur)
    def __int__(self):
        return int(self.dur)
    def __float__(self):
        return float(self.dur)

class PlayerKeyException(Exception):
    pass
