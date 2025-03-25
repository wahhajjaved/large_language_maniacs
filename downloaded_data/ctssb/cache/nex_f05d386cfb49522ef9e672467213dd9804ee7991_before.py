from typing import Union

import math
import operator
import logging
from enum import Enum
from collections import deque

from .constants.instructions import (Instructions,
                                     h_add_glue_instructions,
                                     v_add_glue_instructions)
from .constants.parameters import Parameters, is_parameter_type
from .constants.specials import Specials
from .constants.codes import CatCode
from .constants.units import (Unit, MuUnit, InternalUnit,
                              units_in_sp, MAX_DIMEN)
from .utils import UserError, LogicError, pt_to_sp
from .router import (make_primitive_control_sequence_instruction,
                     make_unexpanded_control_sequence_instruction)
from .accessors import is_register_type, SpecialsAccessor
from . import box
from .box import (HBox, VBox, Rule, Glue, Character, FontDefinition,
                  FontSelection, Kern, Penalty)
from .paragraphs import get_best_h_lists
from . import evaluator as evaler
from .fonts import GlobalFontState
from .scopes import (ScopedCodes, ScopedRegisters, ScopedRouter,
                     ScopedParameters, ScopedFontState, Operation)
from .tokens import BuiltToken, InstructionToken, instructions_to_types

logger = logging.getLogger(__name__)


class Mode(Enum):
    # Building the main vertical list.
    vertical = 'V'
    # Building a vertical list for a vbox.
    internal_vertical = 'IV'
    # Building a horizontal list for a paragraph.
    horizontal = 'H'
    # Building a horizontal list for an hbox.
    restricted_horizontal = 'RH'
    # Building a formula to be placed in a horizontal list.
    math = 'M'
    # Building a formula to be placed on a line by itself,
    # interrupting the current paragraph.
    display_math = 'DM'


vertical_modes = (Mode.vertical, Mode.internal_vertical)
horizontal_modes = (Mode.horizontal, Mode.restricted_horizontal)
math_modes = (Mode.math, Mode.display_math)
# Defined for \ifinner, TeXBook page 209.
inner_modes = (Mode.internal_vertical, Mode.restricted_horizontal, Mode.math)


class Group(Enum):

    # Note, this is *not* the same as 'global scope'. We could enter
    # sub-groups that do not start a new scope, such as a math group.
    outside = 0
    # For 'local structure'.
    local = 1
    # \hbox{...}.
    h_box = 2
    # \hbox{...} in vertical mode.
    adjusted_h_box = 3
    # \vbox{...}.
    v_box = 4
    # \vtop{...}.
    v_top = 5
    # \halign{...} and \valign{...}.
    align = 6
    # \noalign{...}.
    no_align = 7
    # Output routine.
    output = 8
    # For things such as '^{...}'
    math = 9
    # \discretionary{...}{...}{...}.
    discretionary = 10
    # \insert{...} and \vadjust{...}
    insert = 11
    # \vcenter{...}
    v_center = 12
    # \mathchoice{...}{...}{...}{...}
    math_choice = 13
    # \begingroup...\endgroup
    local_verbose = 14
    # $...$
    math_shift = 15
    # \left...\right
    math_left_right = 16


sub_executor_groups = (
    Group.h_box,
    Group.adjusted_h_box,
    Group.v_box,
    Group.v_top,
)


shift_to_horizontal_instructions = (
    Instructions.char,
    Instructions.char_def_token,
    Instructions.un_h_box,
    Instructions.un_h_copy,
    # Instructions.v_align
    Instructions.v_rule,
    Instructions.accent,
    # Instructions.discretionary,
    # Instructions.control_hyphen,
    # TODO: Add control-space primitive, parsing and control sequence.
    # Instructions.control_space,
) + tuple(h_add_glue_instructions)
shift_to_horizontal_types = instructions_to_types(shift_to_horizontal_instructions)
shift_to_horizontal_cat_codes = (CatCode.letter,
                                 CatCode.other,
                                 CatCode.math_shift)


shift_to_vertical_instructions = (
    Instructions.un_v_box,
    Instructions.un_v_copy,
    # Instructions.h_align
    Instructions.h_rule,
    Instructions.end,
    # Instructions.dump,
) + tuple(v_add_glue_instructions)
shift_to_vertical_types = instructions_to_types(shift_to_vertical_instructions)


def command_shifts_to_horizontal(command):
    if command.type in shift_to_horizontal_types:
        return True
    if (command.type == 'character' and
            command.value['cat'] in shift_to_horizontal_cat_codes):
        return True
    return False


def command_shifts_to_vertical(command):
    return command.type in shift_to_vertical_types


def check_not_vertical(method):
    def inner(self, *args, **kwargs):
        if self.mode in vertical_modes:
            raise UserError(f'Cannot do {method} in mode {self.mode}')
        method(self, *args, **kwargs)
    return inner


def check_not_horizontal(method):
    def inner(self, *args, **kwargs):
        if self.mode in horizontal_modes:
            raise UserError(f'Cannot do {method} in mode {self.mode}')
        method(self, *args, **kwargs)
    return inner


def after_assignment(method):
    def inner(self, token_source, *args, **kwargs):
        method(self, token_source, *args, **kwargs)
        if self.after_assignment_token is not None:
            token_source.replace_tokens_on_input([self.after_assignment_token])
            self.after_assignment_token = None
    return inner


class ExecuteCommandError(Exception):

    def __init__(self, command, position_str, *args, **kwargs):
        self.command = command
        self.position_str = position_str

    def __str__(self):
        return (f'\n{self.position_str}\n'
                f'While running {self.command}:\n')


class TidyEnd(Exception):
    pass


class EndOfSubExecutor(Exception):
    pass


class GlobalState:

    def __init__(self, global_font_state,
                 specials,
                 codes, registers, scoped_font_state, router, parameters):
        self.global_font_state = global_font_state
        self.specials = specials

        self.codes = codes
        self.registers = registers
        self.scoped_font_state = scoped_font_state
        self.router = router
        self.parameters = parameters

        # At the beginning, TeX is in vertical mode, ready to construct pages.
        self.modes = []
        self.push_mode(Mode.vertical)
        self.groups = []
        self.push_group(Group.outside)

        self.current_page = []
        self.completed_pages = []
        self.start_new_page()

        self.after_assignment_token = None

    @classmethod
    def from_defaults(cls, font_search_paths=None, global_font_state=None):
        # We allow passing this in for testing purposes, because it touches the
        # outside world (the file system, to search for fonts).
        if global_font_state is None:
            global_font_state = GlobalFontState(font_search_paths)
        specials = SpecialsAccessor.from_defaults()
        codes = ScopedCodes.from_defaults()
        registers = ScopedRegisters.from_defaults()
        scoped_font_state = ScopedFontState.from_defaults()
        router = ScopedRouter.from_defaults()
        parameters = ScopedParameters.from_defaults()
        return cls(global_font_state, specials,
                   codes, registers, scoped_font_state, router, parameters)

    # Mode.

    @property
    def mode(self):
        return self.modes[-1][0]

    @property
    def _layout_list(self):
        return self.modes[-1][1]

    @property
    def mode_depth(self):
        return len(self.modes)

    def return_to_mode(self, depth):
        """Pop modes until returning to a certain depth, packaging boxes along
        the way."""
        if self.mode_depth <= depth:
            raise ValueError(f'Cannot return to a mode depth {depth}, as '
                             'state is only at depth {self.mode_depth}')
        # For all but the last mode to pop, package the results in a box, and
        # add it to the parent mode's list.
        while self.mode_depth > depth + 1:
            box_item = self.pop_mode_to_box()
            self.append_to_list(box_item)
        # For the last mode pop, we might not intend to package it in a box, so
        # just pop and return the list.
        return self.pop_mode()

    def push_mode(self, mode):
        logger.info(f'Entering {mode}')
        # The space factor 'f' is 1000 at the beginning of a horizontal list.
        # You can say `\spacefactor=<number>' to assign any particular value
        # to the space factor.
        if mode in horizontal_modes:
            self.specials.set(Specials.space_factor, 1000)
        # \prevdepth is set to the sentinel value -1000 pt at the beginning of
        # a vertical list [...]; this serves to suppress the next interline
        # glue.
        elif mode in vertical_modes:
            self.specials.set(Specials.prev_depth, pt_to_sp(-1000))
        self.modes.append((mode, deque()))

    def pop_mode_to_box(self):
        if self.mode in horizontal_modes:
            BoxCls = HBox
        elif self.mode in vertical_modes:
            BoxCls = VBox
        else:
            raise NotImplementedError
        layout_list = self.pop_mode()
        # Add what we just constructed to the upper list.
        item = BoxCls(layout_list)
        return item

    def pop_mode(self):
        mode, layout_list = self.modes.pop()
        logger.info(f'Exited {mode}')
        return layout_list

    def append_to_list(self, item):
        if self.mode in horizontal_modes:
            # "[the space factor] is set to 1000 just after a non-character box
            # or a math formula has been put onto the current horizontal list."
            # TODO: I made up these list element conditions from my head.
            if isinstance(item, (HBox, VBox, Rule)):
                self.specials.set(Specials.space_factor, 1000)
            elif isinstance(item, (FontDefinition, FontSelection,
                                   Glue, Kern, Penalty)):
                pass
            # TODO: Ligatures? TeXbook page 76
            # "When ligatures are formed, or when a special character is
            # specified via \char, the space factor code is computed from the
            # individual characters that generated the ligature. For example,
            # plain TeX sets the space factor code for single-right-quote to
            # zero, so that the effects of punctuation will be propagated.  Two
            # adjacent characters '' combine to form a ligature that is in
            # character position octal(042); but the space factor code of this
            # double-right-quote ligature is never examined by TeX, so plain
            # TeX does not assign any value to
            # \sfcode'042.
            # [the space factor] gets set to a number other than 1000 only when
            # a simple character box goes on the list."
            elif isinstance(item, Character):
                # TeXbook page 76 (in later editions): "A character whose
                # character code is 128 or more is required to have a space
                # factor code of 1000, since TeX maintains a changeable \sfcode
                # only for characters 0 to 127."
                code = item.code
                if not 0 <= code <= 127:
                    g = 1000
                else:
                    g = self.codes.get_space_factor_code(chr(code))
                # "Each character has a space factor code, and when a character
                # whose space factor code is 'g' enters the current list the
                # normal procedure is simply to assign 'g' as the new space
                # factor. However, if 'g' is zero, 'f' is not changed; and if
                # 'f < 1000 < g', the space factor is set to 1000. (In other
                # words, 'f' doesn't jump from a value less than 1000 to a
                # value greater than 1000 in a single step.) The maximum space
                # factor is 32767 (which is much higher than anybody would ever
                # want to use)."
                f = self.specials.get(Specials.space_factor)
                if g == 0:
                    pass
                elif f < 1000 < g:
                    self.specials.set(Specials.space_factor, 1000)
                else:
                    self.specials.set(Specials.space_factor, g)
            else:
                raise NotImplementedError
            self._layout_list.append(item)
        elif self.mode in vertical_modes:
            # TODO: I made up these list element conditions from my head.
            if isinstance(item, (FontDefinition, FontSelection,
                                 Glue, Kern, Penalty)):
                self._layout_list.append(item)
            elif isinstance(item, Rule):
                # \prevdepth is set to the sentinel value -1000 pt [...] just
                # after a rule box; this serves to suppress the next interline
                # glue.
                self._layout_list.append(item)
                self.specials.set(Specials.prev_depth, pt_to_sp(-1000))
            elif isinstance(item, (HBox, VBox)):
                # "Assume that a new box of height h (not a rule box) is about
                # to be appended to the bottom of the current vertical list."
                h = item.height
                # "Let \prevdepth = p,"
                p = self.specials.get(Specials.prev_depth)
                # "\lineskiplimit = el,"
                el = self.parameters.get(Parameters.line_skip_limit)
                # "and \baselineskip = b plus y minus z."
                b_skip = self.parameters.get(Parameters.base_line_skip)
                b, y, z = b_skip['dimen'], b_skip['stretch'], b_skip['shrink']
                # "If p <= -1000pt, no interline glue is added."
                base_dimen = b - p - h
                if p <= pt_to_sp(-1000):
                    pass
                # "Otherwise if b - p - h >= el, the interline glue '(b - p -
                # h) plus y minus z' will be appended just above the new box."
                elif base_dimen >= el:
                    g = Glue(base_dimen, stretch=y, shrink=z)
                    self._layout_list.append(g)
                # "Otherwise the \lineskip glue will be appended."
                else:
                    line_skip = self.parameters.get(Parameters.line_skip)
                    g = Glue(**line_skip)
                    self._layout_list.append(g)
                self._layout_list.append(item)
                # "Finally, \prevdepth is set to the depth of the new box."
                self.specials.set(Specials.prev_depth, item.depth)
            else:
                raise NotImplementedError
            if self.mode == Mode.vertical:
                self.fill_page()

    def start_new_page(self):
        # TeXbook page 114.
        # "When the current page contains no boxes, \pagetotal and its
        # relatives are zero and '\pagegoal' is 16383.99998 pt (TeX's largest
        # dimen); changing their values has no effect at such times."
        self.current_page.clear()
        for s in (Specials.page_total,
                  Specials.page_stretch,
                  Specials.page_fil_stretch,
                  Specials.page_fill_stretch,
                  Specials.page_filll_stretch,
                  Specials.page_shrink,
                  Specials.page_goal,
                  ):
            self.specials.set(s, MAX_DIMEN)
        self.best_page_break_so_far = None
        self.best_page_break_cost_so_far = math.inf
        self.seen_box_or_insertion = False
        self.seen_box = False

    def fill_page(self):
        while self._layout_list:
            new_item = self._layout_list.popleft()

            # TeXbook page 112.
            # "Whenever TeX is moving an item from the top of the 'recent
            # contributions' to the bottom of the 'current page,' it discards a
            # discardable item (glue, kern, or penalty) if the current page
            # does not contain any boxes. This is how glue disappears at a page
            # break."
            if new_item.discardable and not self.seen_box:
                continue

            # TeXbook page 114.
            # "TeX salts away the values of \vsize and \maxdepth when [...] the
            # first box or insertion occurs on the current page; subsequent
            # changes to those two parameters have no effect until the next
            # current page is started."
            if isinstance(new_item, (box.AbstractBox, box.Rule,
                                     box.Insertion)):
                if not self.seen_box_or_insertion:
                    v_size = self.parameters.get(Parameters.v_size)
                    self.specials.set(Specials.page_goal, v_size)
                    max_depth = self.parameters.get(Parameters.max_depth)
                    # TODO: I guessed that this is where the parameter is
                    # 'salted away', but I'm not sure.
                    self.specials.set(Specials.page_depth, max_depth)
                self.seen_box_or_insertion = True
            # TeXbook page 114 continued...
            # "On the other hand, TeX looks at '\topskip' only when the first
            # box is being contributed to the current page. If insertions occur
            # before the first box, the \topskip glue before that box is
            # considered to be a valid breakpoint; this is the only case in
            # which a completed page might not contain a box."
            if isinstance(new_item, (box.AbstractBox, box.Rule)):
                if not self.seen_box:
                    pass
                    # TODO: \topskip.
                self.seen_box = True

            self.current_page.append(new_item)

            page_goal = self.specials.get(Specials.page_goal)
            hypot_box = box.VBox(self.current_page, to=page_goal,
                                 set_glue=False)

            # # Update page total.
            # TODO: Make this matter: page break cost always considers the
            # actual length of the list, but I think we actually want to
            # consider the value of \pagetotal.
            # page_total = self.specials.get(Specials.page_total)
            # page_total += hypot_box.get_length(new_item)
            # self.specials.set(Specials.page_total, page_total)

            # TeXbook page 112 continued...
            # "Otherwise if a discardable item is a legitimate breakpoint, TeX
            # calculates the cost 'c' of breaking at this point, using the
            # formula that we have just discussed."
            if box.is_break_point(self.current_page,
                                  i=len(self.current_page) - 1):
                insert_penalties = self.specials.get(Specials.insert_penalties)
                c, p = hypot_box.page_break_cost_and_penalty(break_item=new_item,
                                                             insert_penalties=insert_penalties)
                # "[...] If the resulting 'c' is less than or equal to the
                # smallest cost seen so far on the current page, TeX remembers
                # the current breakpoint as the best so far."
                if c <= self.best_page_break_cost_so_far:
                    self.best_page_break_cost_so_far = c
                    # TODO: Indexing might be one too big or small here.
                    self.best_page_break_so_far = len(self.current_page)
                # "[...] And if c = infinity or if p <= -10000, TeX seizes the
                # initiative and breaks the page at the best remembered
                # breakpoint. Any material on the current page following that
                # best breakpoint is moved back onto the list of recent
                # contributions, where it will be considered again; thus the
                # 'current page' typically gets more than one page's worth of
                # material before the breakpoint is chosen."
                if c == math.inf or p <= -10000:
                    i_break = self.best_page_break_so_far
                    completed_page, remainder_page = (self.current_page[:i_break],
                                                      self.current_page[i_break:])
                    completed_box = box.VBox(completed_page, to=page_goal,
                                             set_glue=True)
                    self.completed_pages.append(completed_box)
                    self._layout_list.extendleft(reversed(remainder_page))
                    self.start_new_page()

    def extend_list(self, items):
        for item in items:
            self.append_to_list(item)

    # Group.

    @property
    def group(self):
        return self.groups[-1][0]

    @property
    def after_group_queue(self):
        return self.groups[-1][1]

    def push_group(self, group):
        logger.info(f'Entering {group}')
        # Each group comes with a queue for the 'after_group' tokens.
        self.groups.append((group, deque()))

    def pop_group(self, banisher):
        group, after_group_queue = self.groups.pop()
        logger.info(f'Exited {group}')
        banisher.replace_tokens_on_input(after_group_queue)
        return group

    # Scope

    @property
    def _scoped_accessors(self):
        return [self.codes, self.registers, self.scoped_font_state,
                self.router, self.parameters]

    def push_new_scope(self):
        for acc in self._scoped_accessors:
            acc.push_new_scope()

    def pop_scope(self):
        for acc in self._scoped_accessors:
            acc.pop_scope()
        if self.current_font_id != GlobalFontState.null_font_id:
            self._select_font(is_global=False, font_id=self.current_font_id)

    # Fonts.

    def load_new_font(self, file_name, at_clause):
        # Affects both global and scoped state: fonts are stored in the global
        # state, but the current font and control sequences to access them are
        # scoped.
        # Load the font.
        logger.info(f"Loading font at '{file_name}'")
        new_font_id = self.global_font_state.define_new_font(file_name,
                                                             at_clause)
        # Add an instruction in the layout list to define a font.
        font_info = self.global_font_state.get_font(new_font_id)
        # Commands like font commands aren't exactly boxes, but they go through
        # as DVI commands. Just put them in the box for now to deal with later.
        font_define_item = FontDefinition(font_nr=new_font_id,
                                          font_name=font_info.font_name,
                                          file_name=font_info.file_name,
                                          at_clause=font_info.at_clause)
        self.append_to_list(font_define_item)
        return new_font_id

    @property
    def current_font_id(self):
        return self.scoped_font_state.current_font_id

    @property
    def current_font(self):
        return self.global_font_state.get_font(self.current_font_id)

    # Evaluate quantities.

    def get_box_dimen(self, i, type_):
        box_item = self.registers.get(Instructions.set_box.value, i=i)
        if type_ == Instructions.box_dimen_height.value:
            return box_item.height
        elif type_ == Instructions.box_dimen_width.value:
            return box_item.width
        elif type_ == Instructions.box_dimen_depth.value:
            return box_item.depth
        else:
            raise ValueError(f'Unknown box dimension requested: {v.type}')

    def get_infinite_dimen(self, nr_fils, nr_units) -> BuiltToken:
        return BuiltToken(
            type_='fil_dimension',
            value={'factor': nr_units,
                   'number_of_fils': nr_fils}
        )

    def get_finite_dimen(self, unit, nr_units, is_true_unit) -> int:
        # Only one unit in mu units, a mu. I don't know what a mu is
        # though...
        if unit == MuUnit.mu:
            unit_scale = 1
        elif unit == InternalUnit.em:
            unit_scale = self.current_font.quad
        elif unit == InternalUnit.ex:
            unit_scale = self.current_font.x_height
        else:
            unit_scale = units_in_sp[unit]
            if is_true_unit:
                magnification = self.parameters.get(Parameters.mag)
                # ['true'] unmagnifies the units, so that the subsequent
                # magnification will cancel out. For example, `\vskip 0.5
                # true cm' is equivalent to `\vskip 0.25 cm' if you have
                # previously said `\magnification=2000'.
                unit_scale *= 1000.0 / magnification
        size = round(nr_units * unit_scale)
        return size

    # Evaluate conditions.

    def evaluate_if_num(self, left_number, right_number, relation):
        operator_map = {
            '<': operator.lt,
            '=': operator.eq,
            '>': operator.gt,
        }
        op = operator_map[relation]
        outcome = op(left_number, right_number)
        return outcome

    evaluate_if_dim = evaluate_if_num

    def evaluate_if_odd(self, number) -> bool:
        return number % 2

    def evaluate_if_v_mode(self) -> bool:
        return self.mode in vertical_modes

    def evaluate_if_h_mode(self) -> bool:
        return self.mode in horizontal_modes

    def evaluate_if_m_mode(self) -> bool:
        return self.mode in math_modes

    def evaluate_if_inner_mode(self) -> bool:
        return self.mode in inner_modes

    def evaluate_if_chars_equal(self, tok_1, tok_2) -> bool:
        # TODO: we will assume tokens are not expandable. Maybe check for this?
        # Instructions in TeXBook page 209.
        raise NotImplementedError

    def evaluate_if_cats_equal(self, tok_1, tok_2) -> bool:
        # Instructions in TeXBook page 209.
        raise NotImplementedError

    def evaluate_if_tokens_equal(self, tok_1, tok_2) -> bool:
        # Instructions in TeXBook page 210.
        raise NotImplementedError

    def evaluate_if_box_register_void(self, reg_nr) -> bool:
        # Instructions in TeXBook page 210.
        raise NotImplementedError

    def evaluate_if_box_register_h_box(self, reg_nr) -> bool:
        # Instructions in TeXBook page 210.
        raise NotImplementedError

    def evaluate_if_box_register_v_box(self, reg_nr) -> bool:
        # Instructions in TeXBook page 210.
        raise NotImplementedError

    def evaluate_if_end_of_file(self, input_stream_nr) -> bool:
        # Instructions in TeXBook page 210.
        logger.warning(f"TODO: if end-of-file of "
                       f"input stream '{input_stream_nr}'")
        # raise NotImplementedError
        return False

    def evaluate_if_case(self, number) -> int:
        if number < 0:
            raise ValueError(f'if-case should not return negative number: '
                             f'{number}')
        return number

    # Do chunky commands.

    def do_paragraph(self):
        if self.mode in vertical_modes:
            # The primitive \par command has no effect when TeX is in
            # vertical mode, except that the page builder is exercised in
            # case something is present on the contribution list, and the
            # paragraph shape parameters are cleared.
            return
        elif self.mode == Mode.restricted_horizontal:
            # The primitive \par command, also called \endgraf in plain
            # \TeX, does nothing in restricted horizontal mode.
            return
        elif self.mode == Mode.horizontal:
            logger.info(f'Adding paragraph')

            # "But it terminates horizontal mode: The current list is
            # finished off by doing, '\unskip \penalty10000
            # \hskip\parfillskip' then it is broken into lines as explained
            # in Chapter 14, and TeX returns to the enclosing vertical or
            # internal vertical mode. The lines of the paragraph are
            # appended to the enclosing vertical list, interspersed with
            # interline glue and interline penalties, and with the
            # migration of vertical material that was in the horizontal
            # list. Then TeX exercises the page builder."

            self.do_un_skip()
            # Do \hskip\parfillskip.
            par_fill_glue = self.parameters.get(Parameters.par_fill_skip)
            self.add_h_glue(**par_fill_glue)
            line_penalty = self.parameters.get(Parameters.line_penalty)
            self.add_penalty(line_penalty)
            # Get the horizontal list
            horizontal_list = deque(self.pop_mode())
            h_size = self.parameters.get(Parameters.h_size)
            # TODO: This is temporary; not correct
            tolerance = self.parameters.get(Parameters.tolerance)

            # It's a deque for some reason I haven't sussed.
            h_lists = get_best_h_lists(list(horizontal_list),
                                       h_size, tolerance, line_penalty)

            # for best_route in all_routes:
            for h_list in h_lists:
                h_box = HBox(h_list, to=h_size)
                # Add it to the enclosing vertical list.
                self.append_to_list(h_box)
        else:
            raise NotImplementedError

    def _get_character_item(self, code):
        return Character(code,
                         width=self.current_font.width(code),
                         height=self.current_font.height(code),
                         depth=self.current_font.depth(code))

    @check_not_vertical
    def add_character_code(self, code):
        self.append_to_list(self._get_character_item(code))

    def add_character_char(self, char):
        return self.add_character_code(ord(char))

    def _add_accented_character(self, accent_code, char_code):
        char_item = self._get_character_item(char_code)
        char_w = self.current_font.width(char_code)
        acc_w = self.current_font.width(accent_code)
        # Go back to the middle of the character, than go back half the accent
        # width, so that the middle of the accent will be the same as that of
        # the character.
        kern_item = Kern(round(-char_w / 2 - acc_w / 2))
        # TeXbook page 54: The accent is assumed to be properly positioned for
        # a character whose height equals the x-height of the current font;
        # taller or shorter characters cause the accent to be raised or
        # lowered, taking due account of the slantedness of the fonts of
        # accenter and accentee.
        # TODO: Slantedness.
        char_h = self.current_font.height(char_code)
        height_to_raise = char_h - self.current_font.x_height
        acc_char_item = self._get_character_item(accent_code)
        acc_item = HBox(contents=[acc_char_item], offset=height_to_raise)
        # TeXbook page 54: The width of the final construction is the width of
        # the character being accented, regardless of the width of the accent.
        item = HBox(contents=[char_item, kern_item, acc_item],
                    to=char_item.width)
        self.append_to_list(item)

    @check_not_vertical
    def do_accent(self, accent_code, target_code=None):
        logger.info(f"Adding accent \"{accent_code}\"")
        # TeXbook page 286.
        # Syntax: \accent <8-bit number> <optional assignments>

        # Here <optional assignments> stands for zero or more <assignment>
        # commands other than \setbox.

        # If the assignments are not followed by a <character>, where
        # <character> stands for [see page 286], TeX treats \accent as if it
        # were \char, except that the space factor is set to 1000.
        if target_code is None:
            self.add_character_code(accent_code)
        # Otherwise, the character that follows the assignment is accented by
        # the character that corresponds to the <8-bit number>. (The purpose of
        # the intervening assignments is to allow the accenter and accentee to
        # be in different fonts.) If the accent must be moved up or down, it is
        # put into an hbox that is raised or lowered. Then the accent is
        # effectively superposed on the character by means of kerns, in such a
        # way that the width of the accent does not influence the width of the
        # resulting horizontal list.
        else:
            self._add_accented_character(accent_code, target_code)
        # Finally, TeX sets \spacefactor=1000.
        self.specials.set(Specials.space_factor, 1000)

    def add_kern(self, length):
        return self.append_to_list(Kern(length))

    def do_un_skip(self):
        if isinstance(self._layout_list[-1], Glue):
            self._layout_list.pop()

    def add_penalty(self, size):
        logger.info(f'Adding penalty {size}')
        self.append_to_list(Penalty(size))

    def _add_glue(self, dimen, stretch, shrink):
        item = Glue(dimen, stretch, shrink)
        logger.info(f'Adding glue {item}')
        self.append_to_list(item)

    def _add_stretch_or_shrink_glue(self):
        one_fil = self.get_infinite_dimen(nr_fils=1, nr_units=1)
        item = Glue(dimen=0, stretch=one_fil, shrink=one_fil)
        logger.info(f'Adding infinite stretch and shrink glue')
        self.append_to_list(item)

    def _add_fil_glue(self):
        one_fil = self.get_infinite_dimen(nr_fils=1, nr_units=1)
        item = Glue(dimen=0, stretch=one_fil, shrink=0)
        logger.info(f'Adding first-order infinite-stretch glue')
        self.append_to_list(item)

    def _add_fill_glue(self):
        two_fils = self.get_infinite_dimen(nr_fils=2, nr_units=1)
        item = Glue(dimen=0, stretch=two_fils, shrink=0)
        logger.info(f'Adding second-order infinite-stretch glue')
        self.append_to_list(item)

    def _add_neg_fil_glue(self):
        one_neg_fil = self.get_infinite_dimen(nr_fils=1, nr_units=-1)
        item = Glue(dimen=0, stretch=one_neg_fil, shrink=one_neg_fil)
        logger.info(f'Adding first-order infinite-negative-stretch glue')
        self.append_to_list(item)

    @check_not_vertical
    def add_h_glue(self, *args, **kwargs):
        return self._add_glue(*args, **kwargs)

    @check_not_horizontal
    def add_v_glue(self, *args, **kwargs):
        return self._add_glue(*args, **kwargs)

    @check_not_vertical
    def add_h_stretch_or_shrink_glue(self):
        return self._add_stretch_or_shrink_glue()

    @check_not_horizontal
    def add_v_stretch_or_shrink_glue(self):
        return self._add_stretch_or_shrink_glue()

    @check_not_vertical
    def add_h_fil_glue(self):
        return self._add_fil_glue()

    @check_not_horizontal
    def add_v_fil_glue(self):
        return self._add_fil_glue()

    @check_not_vertical
    def add_h_fill_glue(self):
        return self._add_fill_glue()

    @check_not_horizontal
    def add_v_fill_glue(self):
        return self._add_fill_glue()

    @check_not_vertical
    def add_h_neg_fil_glue(self):
        return self._add_neg_fil_glue()

    @check_not_horizontal
    def add_v_neg_fil_glue(self):
        return self._add_neg_fil_glue()

    def do_space(self):
        if self.mode in vertical_modes:
            # "Spaces have no effects in vertical modes".
            pass
        elif self.mode in horizontal_modes:
            # When TeX is processing a horizontal list of boxes and glue, it
            # keeps track of a positive integer called the current 'space
            # factor' The space factor is normally 1000, which means that the
            # interword glue should not be modified. If the space factor 'f' is
            # different from 1000, the interword glue is computed as follows:
            # Take the normal space glue for the current font, and add the
            # extra space if f >= 2000. (Each font specifies a normal space,
            # normal stretch, normal shrink, and extra space; for example,
            # these quantities are 3.33333pt, 1.66666pt, 1.11111pt, and
            # 1.11111pt, respectively, in cmr10. Then the stretch component is
            # multiplied by f / 1000, while the shrink component is multiplied
            # by 1000 / f.

            # However, TeX has two parameters \spaceskip and \xspaceskip that
            # allow you to override the normal spacing of the current font. If
            # f >= 2000 and if \xspaceskip is nonzero, the \xspaceskip glue is
            # used for an interword space. Otherwise if \spaceskip is nonzero,
            # the \spaceskip glue is used, with stretch and shrink components
            # multiplied by f / 1000 and 1000 / f. For example, the
            # \raggedright macro of plain TeX\ uses \spaceskip and \xspaceskip
            # to suppress all stretching and shrinking of interword spaces.
            extra_space_skip = self.parameters.get(Parameters.x_space_skip)
            space_skip = self.parameters.get(Parameters.space_skip)
            f = self.specials.get(Specials.space_factor)

            if f > 2000 and extra_space_skip['dimen'] != 0:
                dimen = extra_space_skip['dimen']
                stretch = extra_space_skip['stretch']
                shrink = extra_space_skip['shrink']
            elif space_skip['dimen'] != 0:
                dimen = extra_space_skip['dimen']
                stretch = extra_space_skip['stretch']
                shrink = extra_space_skip['shrink']

                stretch *= round(f / 1000)
                shrink *= round(1000 / f)
            else:
                dimen = self.current_font.spacing
                stretch = self.current_font.space_stretch
                shrink = self.current_font.space_shrink
                if f > 2000:
                    dimen += self.current_font.extra_space

                stretch *= round(f / 1000)
                shrink *= round(1000 / f)

            space_glue_item = Glue(dimen, stretch, shrink)
            self.append_to_list(space_glue_item)
        else:
            raise NotImplementedError

    def _add_rule(self, width, height, depth):
        self.append_to_list(Rule(width, height, depth))

    @check_not_vertical
    def add_v_rule(self, width, height, depth):
        if self.mode not in horizontal_modes:
            raise UserError(f'Cannot add V Rule in non-horizontal '
                            f'mode: {self.mode}')
        if width is None:
            width = pt_to_sp(0.4)
        if height is None:
            height = self.parameters.get(Parameters.v_size)
        if depth is None:
            depth = self.parameters.get(Parameters.v_size)
        self._add_rule(width, height, depth)

    @check_not_horizontal
    def add_h_rule(self, width, height, depth):
        if self.mode not in vertical_modes:
            raise UserError(f'Cannot add V Rule in non-vertical '
                            f'mode: {self.mode}')
        if width is None:
            width = self.parameters.get(Parameters.h_size)
        if height is None:
            height = pt_to_sp(0.4)
        if depth is None:
            depth = 0
        self._add_rule(width, height, depth)

    def do_indent(self):
        def append_parindent_box():
            par_indent_width = self.parameters.get(Parameters.par_indent)
            par_indent_hbox_item = HBox(contents=[], to=par_indent_width)
            self.append_to_list(par_indent_hbox_item)

        if self.mode in vertical_modes:
            # "The \parskip glue is appended to the current list, unless
            # TeX is in internal vertical mode and the current list is
            # empty. Then TeX enters unrestricted horizontal mode, starting
            # the horizontal list with an empty hbox whose width is
            # \parindent. The \everypar tokens are inserted into TeX's
            # input. The page builder is exercised."
            if self.mode != Mode.internal_vertical:
                par_skip_glue = self.parameters.get(Parameters.par_skip)
                par_skip_glue_item = Glue(**par_skip_glue)
                self.append_to_list(par_skip_glue_item)
            self.push_mode(Mode.horizontal)
            # An empty box of width \parindent is appended to the current
            # list, and the space factor is set to 1000.
            append_parindent_box()
        elif self.mode in horizontal_modes:
            # An empty box of width \parindent is appended to the current list,
            # and the space factor is set to 1000.
            # (Space factor handling is done when adding any H Box.)
            append_parindent_box()
        else:
            raise NotImplementedError

    def get_register_box(self, i, copy):
        if copy:
            get_func = self.registers.get
        else:
            get_func = self.registers.pop
        return get_func(Instructions.set_box.value, i)

    def append_register_box(self, i, copy):
        box_item = self.get_register_box(i, copy)
        # If void box, do nothing.
        if box_item is not None:
            self.append_to_list(box_item)

    def get_unboxed_register_box(self, i, copy, horizontal):
        # See TeXbook page 120.
        # TODO: implement global voiding:
        # 'If you say `\global\setbox3=<box>`, register \box3 will become
        # "globally void" when it is subsequently used or unboxed.'
        # TODO: Unset glue:
        box_item = self.get_register_box(i, copy)
        if isinstance(box_item, HBox):
            if horizontal:
                unwrapped_box_contents = box_item.contents
            else:
                raise UserError('Asked to unbox horizontal box, '
                                'but found vertical box')
        elif isinstance(box_item, VBox):
            if horizontal:
                raise UserError('Asked to unbox vertical box, '
                                'but found horizontal box')
            else:
                unwrapped_box_contents = box_item.contents
        # Void box.
        elif box_item is None:
            unwrapped_box_contents = []
        else:
            raise ValueError(f'Box Register contains non-box: {box_item}')
        # An unboxing operation 'unsets' any glue that was set at the box's
        # outer level. For example, consider the sequence of commands:
        #
        # \setbox5=\hbox{A \hbox{B C}} \setbox6=\hbox to 1.05\wd5{\unhcopy5}
        #
        # This makes \box6 five percent wider than \box5; the glue between A
        # and \hbox{B C} stretches to make the difference, but the glue inside
        # the inner hbox does not change.
        for item in unwrapped_box_contents:
            if isinstance(item, Glue):
                item.unset()
        return unwrapped_box_contents

    @check_not_vertical
    def append_unboxed_register_h_box(self, i, copy):
        unwrapped_box_contents = self.get_unboxed_register_box(i, copy,
                                                               horizontal=True)
        self.extend_list(unwrapped_box_contents)

    @check_not_horizontal
    def append_unboxed_register_v_box(self, i, copy):
        unwrapped_box_contents = self.get_unboxed_register_box(i, copy,
                                                               horizontal=False)
        self.extend_list(unwrapped_box_contents)

    @check_not_horizontal
    def do_end(self):
        # TeXbook page 283.
        # "This command is not allowed in internal vertical mode. In
        # regular vertical mode it terminates TeX if the main vertical list
        # is empty and '\deadcycles = 0'. Otherwise TeX backs up the 'end'
        # command so that it can be read again; then it exercises the page
        # builder, after appending a box/glue/penalty combination that will
        # force the output routine to act. (See the end of Chapter 23.)"
        # TeXbook page 264 (the end of Chapter 23).
        # [When TeX gets into the above situation] it inserts the
        # equivalent of
        #
        #   \line{} \vfill \penalty -10000000000
        #   [
        #   translated from Plain TeX into primitive calls:
        #   \hbox to \hsize \vfill \penalty -10000000000
        #   ]
        #
        # into the main vertical list. This has the effect of invoking the
        # output routine repeatedly until everything has been shipped out.
        # In particular, the last column of two-column format will not be
        # lost.
        if self.mode != Mode.vertical:
            raise LogicError(f"Got 'end' command in mode {self.mode}")
        logger.info(f"Doing 'end' command")
        if not self.current_page:
            raise TidyEnd
        h_size = self.parameters.get(Parameters.h_size)
        self.append_to_list(HBox([], to=h_size))
        self.add_v_fill_glue()
        self.add_penalty(-10000000000)
        # Recurse.
        self.do_end()

    def start_local_group(self):
        self.push_group(Group.local)
        self.push_new_scope()

    def end_group(self, banisher):
        if self.group == Group.local:
            # TODO: Bit dodgy: TeXbook says 'after_group' tokens are inserted
            # "just *after* undoing local assignments". Emphasis mine.
            self.pop_group(banisher)
            self.pop_scope()
        # For groups where we started a sub-executor (for example, to get a
        # box), raise an exception to tell the surrounding executor to finish
        # up (such as tell the banisher to make the box).
        elif self.group in sub_executor_groups:
            # "Eventually, when the matching '}' appears, TeX restores
            # values that were changed by assignments in the group just
            # ended."
            self.pop_group(banisher)
            self.pop_scope()
            raise EndOfSubExecutor
        else:
            raise NotImplementedError

    def push_to_after_group_queue(self, token):
        self.after_group_queue.append(token)

    def set_after_assignment_token(self, token):
        self.after_assignment_token = token

    @after_assignment
    def do_macro_assigment(self, token_source,
                           name, parameter_text, replacement_text,
                           def_type, prefixes):
        logger.info(f"Defining macro '{name}'")
        self.router.set_macro(
                name, parameter_text=parameter_text,
                replacement_text=replacement_text,
                def_type=def_type, prefixes=prefixes,
        )

    @after_assignment
    def set_register(self, token_source, is_global, type_, i, value):
        logger.info(f"Setting '{type_}' register '{i}' to '{value}'")
        self.registers.set(is_global, type_, i, value)

    @after_assignment
    def modify_register(self, token_source, is_global, type_, i, by_operand,
                        operation):
        logger.info(f"Modifying '{type_}' register '{i}'")
        self.registers.modify_register_value(is_global, type_, i,
                                             by_operand, operation)

    @after_assignment
    def set_parameter(self, token_source, is_global, name, value):
        logger.info(f"Setting parameter '{name}' to '{value}'")
        self.parameters.set_parameter(is_global, name, value)

    @after_assignment
    def modify_parameter(self, token_source, is_global, parameter,
                         by_operand, operation):
        logger.info(f"Modifying parameter '{parameter}'")
        self.parameters.modify_parameter_value(is_global, parameter,
                                               by_operand, operation)

    @after_assignment
    def set_code(self, token_source, is_global, code_type,
                 char_size, code_size):
        logger.info(f"Setting '{code_type}' code '{code_size}' to '{char_size}'")
        self.codes.set_by_nrs(
            is_global=is_global,
            code_type=code_type,
            char_size=char_size,
            code_size=code_size,
        )

    @after_assignment
    def do_let_assignment(self, token_source, new_name, *args, **kwargs):
        logger.info(f"Doing let assignment to '{new_name}'")
        self.router.do_let_assignment(new_name=new_name, *args, **kwargs)

    @after_assignment
    def do_short_hand_definition(self, token_source, is_global, name,
                                 def_type, code):
        logger.info(f"Defining short macro '{name}' as {code}")
        self.router.do_short_hand_definition(
            is_global=is_global,
            name=name,
            def_type=def_type,
            code=code,
        )

    def _select_font(self, is_global, font_id):
        self.scoped_font_state.set_current_font(is_global, font_id)
        font_select_item = FontSelection(font_nr=font_id)
        # Commands like font commands aren't exactly boxes, but they go through
        # as DVI commands. Just put them in the box for now to deal with later.
        self.append_to_list(font_select_item)

    @after_assignment
    def select_font(self, token_source, is_global, font_id):
        logger.info(f"Selecting font '{font_id}'")
        self._select_font(is_global=is_global, font_id=font_id)

    @after_assignment
    def set_font_family(self, token_source, is_global, family_nr, font_range, font_id):
        logger.info(f"Setting font family '{family_nr}'")
        self.scoped_font_state.set_font_family(
            is_global=is_global,
            family_nr=family_nr,
            font_range=font_range,
            font_id=font_id
        )

    @after_assignment
    def set_box_register(self, token_source, i, item, is_global):
        logger.info(f"Setting box register")
        self.registers.set(type_=Instructions.set_box.value, i=i,
                           value=item, is_global=is_global)

    @after_assignment
    def define_new_font(self, token_source,
                        file_name, at_clause, cs_name, is_global):
        new_font_id = self.load_new_font(file_name, at_clause)
        logger.info(f"Defining new font '{new_font_id}' as '{cs_name}'")
        # Make a control sequence pointing to it.
        self.router.define_new_font_control_sequence(
            is_global, cs_name, new_font_id)

    @after_assignment
    def set_skew_char(self, token_source, *args, **kwargs):
        logger.info(f"Setting skew character")
        self.global_font_state.set_skew_char(*args, **kwargs)

    @after_assignment
    def set_hyphen_char(self, token_source, *args, **kwargs):
        logger.info(f"Setting hyphen character")
        self.global_font_state.set_hyphen_char(*args, **kwargs)

    # Driving with tokens.

    def _parse_box_token(self, v, horizontal):
        conts = v['contents']
        spec = v['specification']
        to = None
        spread = None
        if spec is not None:
            d = self.eval_number_token(spec.value)
            if spec.type == 'to':
                to = d
            elif spec.type == 'spread':
                spread = d
            else:
                raise ValueError(f'Unknown specification type {spec.type}')
        BoxCls = HBox if horizontal else VBox
        box_item = BoxCls(contents=conts, to=to, spread=spread)
        return box_item

    def eval_size_token(self, size_token) -> Union[int, BuiltToken]:
        """Evaluate the components of an unsigned quantity and return the
        result. Usually this will be an integer, but it may also be a token
        representing an infinite size of some order.
        """
        v = size_token.value
        # If the size is the contents of an integer or dimen parameter.
        if isinstance(v, InstructionToken) and v.type in (Instructions.integer_parameter.value,
                                                          Instructions.dimen_parameter.value):
            return self.parameters.get(v.value['parameter'])
        # If the size is the contents of a count or dimen register.
        elif isinstance(v, BuiltToken) and v.type in (Instructions.count.value,
                                                      Instructions.dimen.value):
            # The register number is a generic 'number' token, so evaluate
            # this.
            evaled_i = self.eval_number_token(v.value)
            return self.registers.get(v.type, i=evaled_i)
        elif isinstance(v, BuiltToken) and v.type in (Instructions.box_dimen_height.value,
                                                      Instructions.box_dimen_width.value,
                                                      Instructions.box_dimen_depth.value):
            # The box register number is a generic 'number' token, so evaluate
            # this.
            evaled_i = self.eval_number_token(v.value)
            return self.get_box_dimen(evaled_i, v.type)
        # If the size is the short-hand character token.
        # This is different to, for example, a count_def_token. A character
        # token has an integer that represents a character code, and is itself
        # the value. A count-def token has an integer that represents the
        # *location* of the actual value.
        elif isinstance(v, InstructionToken) and v.type in ('CHAR_DEF_TOKEN', 'MATH_CHAR_DEF_TOKEN'):
            return v.value
        # If the size is the code of the target of a backtick instruction.
        elif isinstance(v, BuiltToken) and v.type == 'backtick':
            return evaler.get_backtick_target_code(target=v.value)
        # If the size is the integer represented by an integer literal.
        elif isinstance(v, BuiltToken) and v.type == 'integer_constant':
            return evaler.get_integer_constant(v.value)
        # If the size is the real number represented by a decimal number
        # literal.
        elif isinstance(v, BuiltToken) and v.type == 'decimal_constant':
            return evaler.get_real_decimal_constant(v.value)
        # If the size is the value represented by a short-hand def token.
        elif isinstance(v, BuiltToken) and v.type == 'internal':
            return v.value
        # If the size is a specification of a dimension (this is different to a
        # call to retrieve the contents of a dimen register).
        elif isinstance(v, BuiltToken) and v.type == 'dimen':
            nr_units = self.eval_size_token(v.value['factor'])
            unit_attrs = v.value['unit']
            unit = unit_attrs['unit']
            if unit == Unit.fil:
                nr_fils = unit_attrs['number_of_fils']
                return self.get_infinite_dimen(nr_fils, nr_units)
            else:
                is_true_unit = unit_attrs.get('true', False)
                return self.get_finite_dimen(unit, nr_units, is_true_unit)
        else:
            raise ValueError

    def eval_number_token(self, number_token) -> Union[int, BuiltToken]:
        """Evaluate the components of a signed quantity and return the result.
        Usually this will be an integer, but it may also be a token
        representing an infinite number of some order and sign.
        """
        number_value = number_token.value
        # Occurs if the number is a register-def-token.
        if isinstance(number_value, BuiltToken) and number_value.type == 'internal_number':
            return number_value.value
        elif isinstance(number_value, dict):
            size_token = number_value['size']
            size = self.eval_size_token(size_token)
            sign = evaler.evaluate_signs(number_value['signs'])
            if isinstance(size, BuiltToken) and size.type == 'fil_dimension':
                size.value['factor'] *= sign
            else:
                size *= sign
            return size
        else:
            raise ValueError

    def eval_glue_token(self, glue_token) -> dict:
        v = glue_token.value
        if isinstance(v, BuiltToken) and v.type == 'explicit':
            # Should contain a dict specifying three dimens (in the general sense
            # of 'physical length'), a 'dimen' (in the narrow sense), 'shrink' and
            # 'stretch'.
            dimens = v.value
            evaluated_glue = {}
            for dimen_name, dimen_tok in dimens.items():
                if dimen_tok is None:
                    evaluated_dimen = None
                else:
                    evaluated_dimen = self.eval_number_token(dimen_tok)
                evaluated_glue[dimen_name] = evaluated_dimen
            return evaluated_glue
        # If the size is the contents of a glue or mu glue register.
        elif isinstance(v, BuiltToken) and v.type in (Instructions.skip.value,
                                                      Instructions.mu_skip.value):
            # The register number is a generic 'number' token, so evaluate this
            # first.
            evaled_i = self.eval_number_token(v.value)
            return self.registers.get(v.type, i=evaled_i)
        # If the size is the contents of a parameter.
        elif isinstance(v, InstructionToken) and v.type in (Instructions.glue_parameter.value,
                                                            Instructions.mu_glue_parameter.value):
            return self.parameters.get(v.value['parameter'])
        else:
            raise ValueError(f"Unknown glue token '{glue_token}'")

    def eval_token_list_token(self, token_list_token) -> list:
        token_list_value = token_list_token.value
        if token_list_value.type == 'general_text':
            evaluated_token_list = token_list_value.value
        # Also could be token_register, or token parameter.
        else:
            raise NotImplementedError
        return evaluated_token_list

    def execute_command_tokens(self, commands, banisher):
        while True:
            try:
                self.execute_command_token(next(commands), banisher)
            except EOFError:
                return
            except EndOfSubExecutor:
                return

    def execute_command_token(self, command, banisher):
        try:
            self._execute_command_token(command, banisher)
        except (EOFError, EndOfSubExecutor, TidyEnd):
            raise
        except Exception as e:
            raise ExecuteCommandError(
                command=command,
                position_str='',
            ) from e

    def _execute_command_token(self, command, banisher):
        # Reader needed to allow us to insert new input in response to
        # commands.
        # Banisher needed to allow us to put output back on the queue in
        # response to commands.
        type_ = command.type
        v = command.value
        # Note: It would be nice to do this in the banisher, so we don't have
        # to mess about unpacking the command. But one cannot know at banisher-
        # time how a terminal token in isolation will be used. For example, a
        # char-cat pair might end up as part of a filename or something.
        if (self.mode in vertical_modes and
                command_shifts_to_horizontal(command)):
            # "If any of these tokens occurs as a command in vertical mode or
            # internal vertical mode, TeX automatically performs an \indent
            # command as explained above. This leads into horizontal mode with
            # the \everypar tokens in the input, after which TeX will see the
            # horizontal command again."
            # Put the terminal tokens that led to this command back on the
            # input queue.
            logger.info(f'"{type_}" causing shift to horizontal mode')
            terminal_tokens = command._terminal_tokens
            # Get a primitive token for the indent command.
            indent_token = make_primitive_control_sequence_instruction(
                name='indent', instruction=Instructions.indent)
            # And add it before the tokens we just read.
            banisher.replace_tokens_on_input([indent_token] + terminal_tokens)
        elif (self.mode == Mode.horizontal and
              command_shifts_to_vertical(command)):
            # "The appearance of a <vertical command> in regular horizontal
            # mode causes TeX to insert the token 'par' into the input; after
            # reading and expanding this 'par' token, TeX will see the
            # <vertical command> token again. (The current meaning of the
            # control sequence \par will be used; 'par' might no longer stand
            # for TeX's \par primitive.)"
            # Put the terminal tokens that led to this command back on the
            # input queue.
            logger.info(f'"{type_}" causing shift to vertical mode')
            terminal_tokens = command._terminal_tokens
            par_cs_token = make_unexpanded_control_sequence_instruction('par')
            banisher.replace_tokens_on_input([par_cs_token] + terminal_tokens)
        elif (self.mode == Mode.restricted_horizontal and
              command_shifts_to_vertical(command)):
            # The appearance of a <vertical command> in restricted horizontal
            # mode is forbidden.
            raise UserError(f"Cannot do command {type_} in restricted "
                            f"horizontal mode")
        elif type_ == Instructions.space.value:
            logger.debug(f'Doing space')
            self.do_space()
        elif type_ == Instructions.par.value:
            logger.debug(f'Doing paragraph')
            self.do_paragraph()
        elif type_ == 'character':
            logger.debug(f"Adding character \"{v['char']}\"")
            self.add_character_char(v['char'])
        elif type_ == Instructions.accent.value:
            logger.info(f'Adding accented character')
            assignments = v['assignments'].value
            accent_code_eval = self.eval_number_token(v['accent_code'])
            char_tok = v['target_char']
            if char_tok is None:
                target_char_code = None
            elif char_tok.type == 'character':
                target_char_code = ord(char_tok.value['char'])
            else:
                raise NotImplementedError
            # TeXbook page 54: "Mode-independent commands like font changes may
            # appear between the accent number and the character to be
            # accented, but grouping operations must not intervene."
            for assignment in assignments:
                self.execute_command_token(assignment, banisher)
            self.do_accent(accent_code_eval, target_char_code)
        elif type_ == Instructions.v_rule.value:
            logger.info(f"Adding vertical rule")
            # Evaluate the number token representing each dimension.
            for k in v:
                if v[k] is not None:
                    v[k] = self.eval_number_token(v[k])
            self.add_v_rule(**v)
        elif type_ == Instructions.h_rule.value:
            logger.info(f"Adding horizontal rule")
            # Evaluate the number token representing each dimension.
            for k in v:
                if v[k] is not None:
                    v[k] = self.eval_number_token(v[k])
            self.add_h_rule(**v)
        # The box already has its contents in the correct way, built using this
        # very method. Recursion still amazes me sometimes.
        elif type_ in (Instructions.h_box.value,
                       Instructions.v_box.value, Instructions.v_top.value):
            horizontal = type_ == Instructions.h_box.value
            if horizontal:
                logger.info(f'Adding horizontal box')
            else:
                logger.info(f'Adding vertical box')
            box_item = self._parse_box_token(v, horizontal=horizontal)
            self.append_to_list(box_item)
        elif type_ in (Instructions.box.value, Instructions.copy.value):
            logger.info(f"Getting box from register with '{type_}' command")
            evaled_i = self.eval_number_token(v)
            # \box empties the register; \copy doesn't
            is_copy = type_ == Instructions.copy.value
            self.append_register_box(i=evaled_i, copy=is_copy)
        elif type_ == 'un_box':
            logger.info(f"Unpacking box from register with '{type_}' command")
            reg_nr = self.eval_number_token(v['nr'])
            cmd_type = v['cmd_type']
            if cmd_type in (Instructions.un_h_copy, Instructions.un_v_copy):
                is_copy = True
            elif cmd_type in (Instructions.un_h_box, Instructions.un_v_box):
                is_copy = False
            else:
                raise ValueError(f'Unknown unbox command type: {cmd_type}')
            if v['cmd_type'] in (Instructions.un_h_copy,
                                 Instructions.un_h_box):
                method = self.append_unboxed_register_h_box
            elif v['cmd_type'] in (Instructions.un_v_copy,
                                   Instructions.un_v_box):
                method = self.append_unboxed_register_v_box
            else:
                raise ValueError(f'Unknown unbox command type: {cmd_type}')
            method(i=reg_nr, copy=is_copy)
        elif type_ == Instructions.ship_out.value:
            raise NotImplementedError
        # I think technically only this should cause the program to end, not
        # EOFError anywhere. But for now, whatever.
        elif type_ == Instructions.end.value:
            self.do_end()
        elif type_ == 'message':
            logger.info(f"Doing 'message' command")
            conts = v['content'].value
            s = ''.join(t.value['char'] for t in conts)
            logger.warning(f'TODO: MESSAGE: {s}')
        elif type_ == 'write':
            logger.info(f"Doing 'write' command")
            conts = v['content'].value
            # s = ''.join(t.value['char'] for t in conts)
            logger.warning(f'TODO: LOG: <TODO>')
            # TODO: This should be read with expansion, but at the moment we
            # read it unexpanded, so what we get here is not printable.
            pass
        elif type_ == Instructions.relax.value:
            logger.info(f"Doing 'relax' command")
            pass
        elif type_ == Instructions.indent.value:
            logger.debug(f"Doing 'indent'")
            self.do_indent()
        elif type_ == Instructions.left_brace.value:
            logger.debug(f"Starting local group due to left brace")
            # A character token of category 1, or a control sequence like
            # \bgroup that has been \let equal to such a character token,
            # causes TeX to start a new level of grouping.
            self.start_local_group()
        elif type_ == Instructions.right_brace.value:
            logger.debug(f"Ending current group '{self.group}' due to right brace")
            # I think roughly same comments as for left brace above probably
            # apply.
            self.end_group(banisher)
        # Adding glue.
        elif type_ == Instructions.h_skip.value:
            glue = self.eval_glue_token(v)
            self.add_h_glue(**glue)
        elif type_ == Instructions.v_skip.value:
            glue = self.eval_glue_token(v)
            self.add_v_glue(**glue)
        elif type_ == Instructions.h_stretch_or_shrink.value:
            self.add_h_stretch_or_shrink_glue()
        elif type_ == Instructions.v_stretch_or_shrink.value:
            self.add_v_stretch_or_shrink_glue()
        elif type_ == Instructions.h_fil.value:
            self.add_h_fil_glue()
        elif type_ == Instructions.v_fil.value:
            self.add_v_fil_glue()
        elif type_ == Instructions.h_fill.value:
            self.add_h_fill_glue()
        elif type_ == Instructions.v_fill.value:
            self.add_v_fill_glue()
        elif type_ == Instructions.h_fil_neg.value:
            self.add_h_neg_fil_glue()
        elif type_ == Instructions.v_fil_neg.value:
            self.add_v_neg_fil_glue()
        elif type_ == Instructions.open_input.value:
            stream_nr = self.eval_number_token(v['stream_nr'])
            file_name = v['file_name'].value
            logger.warning(f"TODO: Open input file '{file_name}' as stream "
                           f"{stream_nr}")
            # raise NotImplementedError
        # After group.
        elif type_ == Instructions.after_group.value:
            self.push_to_after_group_queue(v)
        elif type_ == Instructions.after_assignment.value:
            self.set_after_assignment_token(v)
        # Start of assignments.
        elif type_ == 'macro_assignment':
            self.do_macro_assigment(
                token_source=banisher,
                name=v['name'],
                parameter_text=v['parameter_text'],
                replacement_text=v['replacement_text'],
                def_type=v['def_type'],
                prefixes=v['prefixes'],
            )
        elif type_ == 'variable_assignment':
            variable, value = v['variable'], v['value']
            # The value might be a variable reference or something, so we must
            # evaluate it to its contents first before assigning a variable to
            # it.
            value_evaluate_map = {
                'number': self.eval_number_token,
                'dimen': self.eval_number_token,
                'glue': self.eval_glue_token,
                'token_list': self.eval_token_list_token,
            }
            value_evaluate_func = value_evaluate_map[value.type]
            evaled_value = value_evaluate_func(value)
            if is_register_type(variable.type):
                evaled_i = self.eval_number_token(variable.value)
                self.set_register(
                    token_source=banisher,
                    type_=variable.type,
                    i=evaled_i,
                    value=evaled_value,
                    is_global=v['global'],
                )
            elif is_parameter_type(variable.type):
                parameter = variable.value['parameter']
                self.set_parameter(
                    token_source=banisher,
                    name=parameter,
                    value=evaled_value,
                    is_global=v['global'],
                )
            else:
                raise ValueError(f"Unknown variable type: '{variable.type}'")
        elif type_ == 'advance':
            variable, value = v['variable'], v['value']
            # See 'variable_assignment' case.
            evaled_value = self.eval_number_token(value)
            kwargs = {'is_global': v['global'],
                      'by_operand': evaled_value,
                      'operation': Operation.advance}
            if is_register_type(variable.type):
                evaled_i = self.eval_number_token(variable.value)
                self.modify_register(
                    token_source=banisher,
                    type_=variable.type,
                    i=evaled_i,
                    **kwargs
                )
            elif is_parameter_type(variable.type):
                parameter = variable.value['parameter']
                self.modify_parameter(
                    token_source=banisher,
                    name=parameter,
                    **kwargs
                )
            else:
                raise ValueError(f"Unknown variable type: '{variable.type}'")
        elif type_ == 'code_assignment':
            char_size = self.eval_number_token(v['char'])
            code_size = self.eval_number_token(v['code'])
            self.set_code(
                token_source=banisher,
                is_global=v['global'],
                code_type=v['code_type'],
                char_size=char_size,
                code_size=code_size,
            )
        elif type_ == 'let_assignment':
            self.do_let_assignment(
                token_source=banisher,
                is_global=v['global'],
                new_name=v['name'],
                target_token=v['target_token']
            )
        elif type_ == 'short_hand_definition':
            code_uneval = v['code']
            # TODO: Log symbolic argument too.
            code_eval = self.eval_number_token(code_uneval)
            cs_name = v['control_sequence_name']
            self.do_short_hand_definition(
                banisher, v['global'], cs_name, v['def_type'],
                code_eval,
            )
        elif type_ == 'font_selection':
            self.select_font(banisher, v['global'], v['font_id'])
        elif type_ == 'family_assignment':
            family_nr_eval = self.eval_number_token(v['family_nr'])
            self.set_font_family(banisher, v['global'], family_nr_eval,
                                 v['font_range'], v['font_id'])
        elif type_ == Instructions.set_box.value:
            evaled_i = self.eval_number_token(v['nr'])
            box_type = v['box'].type
            horizontal = box_type == Instructions.h_box.value
            box_item = self._parse_box_token(v['box'].value,
                                             horizontal=horizontal)
            self.set_box_register(banisher, evaled_i, box_item, v['global'])
        elif type_ == 'font_definition':
            self.define_new_font(banisher,
                                 v['file_name'].value, v['at_clause'],
                                 v['control_sequence_name'], v['global'])
        elif type_ == 'skew_char_assignment':
            code_eval = self.eval_number_token(v['code'])
            self.set_skew_char(banisher, v['font_id'], code_eval)
        elif type_ == 'hyphen_char_assignment':
            code_eval = self.eval_number_token(v['code'])
            self.set_hyphen_char(banisher, v['font_id'], code_eval)
        # TODO: implement this, and mark method with 'assignment' decorator.
        elif type_ == Instructions.hyphenation.value:
            raise NotImplementedError
        # TODO: implement this, and mark method with 'assignment' decorator.
        elif type_ == Instructions.patterns.value:
            raise NotImplementedError
        # TODO: handle these commands, and mark them with 'assignments'
        # decorator:
        # box_size_assignment
        # interaction_mode_assignment
        # intimate_assignment
        # End of assignments.
        else:
            raise ValueError(f"Command type '{type_}' not recognised.")

    # This method has a long name to emphasize that it will return the index of
    # the token block to pick, not the result of the condition.
    def evaluate_if_token_to_block(self, if_token) -> int:
        v = if_token.value
        t = if_token.type
        if t == Instructions.if_num.value:
            relation_str = v['relation'].value['char']
            left_nr = self.eval_number_token(v['left_number'])
            right_nr = self.eval_number_token(v['right_number'])
            outcome = self.evaluate_if_num(left_nr, right_nr, relation_str)
        elif t == Instructions.if_dimen.value:
            relation_str = v['relation'].value['char']
            left_dim = self.eval_number_token(v['left_dimen'])
            right_dim = self.eval_number_token(v['right_dimen'])
            outcome = self.evaluate_if_dim(left_dim, right_dim, relation_str)
        elif t == Instructions.if_odd.value:
            nr = self.eval_number_token(v['number'])
            outcome = self.evaluate_if_odd(nr)
        elif t == Instructions.if_v_mode.value:
            outcome = self.evaluate_if_v_mode()
        elif t == Instructions.if_h_mode.value:
            outcome = self.evaluate_if_h_mode()
        elif t == Instructions.if_m_mode.value:
            outcome = self.evaluate_if_m_mode()
        elif t == Instructions.if_inner_mode.value:
            outcome = self.evaluate_if_inner_mode()
        elif t == Instructions.if_char.value:
            outcome = self.evaluate_if_chars_equal(v['tok_1'], v['tok_2'])
        elif t == Instructions.if_cat.value:
            outcome = self.evaluate_if_cats_equal(v['tok_1'], v['tok_2'])
        elif t == Instructions.if_token.value:
            outcome = self.evaluate_if_tokens_equal(v['tok_1'], v['tok_2'])
        elif t == Instructions.if_void.value:
            nr = self.eval_number_token(v['number'])
            outcome = self.evaluate_if_box_register_void(reg_nr=nr)
        elif t == Instructions.if_h_box.value:
            nr = self.eval_number_token(v['number'])
            outcome = self.evaluate_if_box_register_h_box(reg_nr=nr)
        elif t == Instructions.if_v_box.value:
            nr = self.eval_number_token(v['number'])
            outcome = self.evaluate_if_box_register_v_box(reg_nr=nr)
        elif t == Instructions.if_end_of_file.value:
            nr = self.eval_number_token(v['number'])
            outcome = self.evaluate_if_end_of_file(input_stream_nr=nr)
        elif t == Instructions.if_true.value:
            outcome = True
        elif t == Instructions.if_false.value:
            outcome = False
        elif t == Instructions.if_case.value:
            number_eval = self.eval_number_token(v['number'])
            outcome = self.evaluate_if_case(number_eval)
        else:
            raise ValueError(f"Unknown 'if' token of type '{t}'")
        i_block_to_pick: int
        if t == Instructions.if_case:
            i_block_to_pick = outcome
        else:
            i_block_to_pick = 0 if outcome else 1
        return i_block_to_pick
