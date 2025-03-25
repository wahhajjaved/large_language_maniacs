"""An ASCII pretty printer of dependency trees."""
import re
import sys

import colorama
from termcolor import colored
from udapi.core.basewriter import BaseWriter

COLOR_OF = {
    'form': 'yellow',
    'lemma': 'cyan',
    'upos': 'red',
    'deprel': 'blue',
    'ord': 'green',
}

# Too many instance variables, arguments, branches...
# I don't see how to fix this while not making the code less readable or more difficult to use.
# pylint: disable=R0902,R0912,R0913,R0914
class TextModeTrees(BaseWriter):
    """An ASCII pretty printer of dependency trees.

    SYNOPSIS
    # from command line (visualize CoNLL-U files)
    udapy write.TextModeTrees color=1 < file.conllu | less -R

    # is scenario (examples of other parameters)
    write.TextModeTrees indent=1 print_sent_id=1 print_sentence=1
    write.TextModeTrees zones=en,cs attributes=form,lemma,upos minimize_cross=0

    DESCRIPTION
    This block prints dependency trees in plain-text format.
    For example the following CoNLL-U file (with tabs instead of spaces)

    1  I     I     PRON  PRP Number=Sing|Person=1 2  nsubj     _ _
    2  saw   see   VERB  VBD Tense=Past           0  root      _ _
    3  a     a     DET   DT  Definite=Ind         4  det       _ _
    4  dog   dog   NOUN  NN  Number=Sing          2  dobj      _ _
    5  today today NOUN  NN  Number=Sing          2  nmod:tmod _ SpaceAfter=No
    6  ,     ,     PUNCT ,   _                    2  punct     _ _
    7  which which DET   WDT PronType=Rel         10 nsubj     _ _
    8  was   be    VERB  VBD Person=3|Tense=Past  10 cop       _ _
    9  a     a     DET   DT  Definite=Ind         10 det       _ _
    10 boxer boxer NOUN  NN  Number=Sing          4  acl:relcl _ SpaceAfter=No
    11 .     .     PUNCT .   _                    2  punct     _ _

    will be printed (with the default parameters) as
    ─┮
     │ ╭─╼ I PRON nsubj
     ╰─┾ saw VERB root
       │                        ╭─╼ a DET det
       ├────────────────────────┾ dog NOUN dobj
       ├─╼ today NOUN nmod:tmod │
       ├─╼ , PUNCT punct        │
       │                        │ ╭─╼ which DET nsubj
       │                        │ ├─╼ was VERB cop
       │                        │ ├─╼ a DET det
       │                        ╰─┶ boxer NOUN acl:relcl
       ╰─╼ . PUNCT punct

    Some non-projective trees cannot be printed witout crossing edges.
    TextModeTrees uses a special "bridge" symbol ─╪─ to mark this:
    ─┮
     │ ╭─╼ 1
     ├─╪───┮ 2
     ╰─┶ 3 │
           ╰─╼ 4

    By default parameter `color=auto`, so if the output is printed to the console
    (not file or pipe), each node attribute is printed in different color.
    If a given node's MISC contains any of `ToDo`, `Bug` or `Mark` attributes
    (or any other specified in the parameter `mark`), the node will be highlighted
    (by reveresing the background and foreground colors).

    This block's method `process_tree` can be called on any node (not only root),
    which is useful for printing subtrees using `node.print_subtree()`,
    which is internally implemented using this block.

    SEE ALSO
    `write.TextModeTreesHtml`
    """

    def __init__(self, print_sent_id=True, print_text=True, add_empty_line=True, indent=1,
                 minimize_cross=True, color='auto', attributes='form,upos,deprel',
                 print_undef_as='', print_doc_meta=True, print_comments=False,
                 mark='ToDo|Bug|Mark', marked_only=False, **kwargs):
        """Create new TextModeTrees block object.

        Args:
        print_sent_id: Print ID of the tree (its root, aka "sent_id") above each tree?
        print_sentence: Print plain-text detokenized sentence on a line above each tree?
        add_empty_line: Print an empty line after each tree?
        indent: Number of characters to indent node depth in the tree for better readability.
        minimize_cross: Minimize crossings of edges in non-projective trees?
                        Trees without crossings are subjectively more readable, but usually
                        in practice also "deeper", that is with higher maximal line length.
        color: Print the node attribute with ANSI terminal colors?
               Default = 'auto' which means that color output only if the output filehandle
               is interactive (console). Each attribute is assigned a color (the mapping is
               tested on black background terminals and can be changed only in source code).
               If you plan to pipe the output (e.g. to "less -R") and you want the colors,
               you need to set explicitly color=1, see the example in Synopsis.
        attributes: A comma-separated list of node attributes which should be printed. Possible
                    values are ord, form, lemma, upos, xpos, feats, deprel, deps, misc.
        print_undef_as: What should be printed instead of undefined attribute values (if any)?
        print_doc_meta: Print `document.meta` metadata before each document?
        print_comments: Print comments (other than sent_id and text)?
        mark: a regex. If `re.search(mark, str(node.misc))` the node is highlighted.
            If `print_comments and re.search(mark, root.comment)` the comment is highlighted.
            Empty string means no highlighting. Default = 'ToDo|Bug|Mark'.
        marked_only: print only trees containing one or more marked nodes/comments. Default=False.
        """
        super().__init__(**kwargs)
        self.print_sent_id = print_sent_id
        self.print_text = print_text
        self.add_empty_line = add_empty_line
        self.indent = indent
        self.minimize_cross = minimize_cross
        self.color = color
        self.print_undef_as = print_undef_as
        self.print_doc_meta = print_doc_meta
        self.print_comments = print_comments
        self.mark = mark
        self.marked_only = marked_only

        # _draw[is_bottommost][is_topmost]
        line = '─' * indent
        self._horiz = line + '╼'
        self._draw = [[line + '┾', line + '┮'], [line + '┶', self._horiz]]

        # _space[is_bottommost][is_topmost]
        # _vert[is_crossing]
        space = ' ' * indent
        self._space = [[space + '├', space + '╭'], [space + '╰']]
        self._vert = [space + '│', line + '╪']

        self.attrs = attributes.split(',')
        self.mark_re = re.compile(mark, re.S) if (mark is not None and mark != '') else None
        self._index_of = []
        self._gaps = []
        self.lines = []
        self.lengths = []

    # We want to be able to call process_tree not only on root node,
    # so this block can be called from node.print_subtree(**kwargs)
    # on any node and print its subtree. Thus, we cannot assume that
    # allnodes[idx].ord == idx. Instead of node.ord, we'll use index_of[node.ord],
    # which is its index within the printed subtree.
    # gaps[node.ord] = number of nodes within node's span, which are not its descendants.
    def _compute_gaps(self, node):
        lmost, rmost, descs = self._index_of[node.ord], self._index_of[node.ord], 0
        for child in node.children:
            _lm, _rm, _de = self._compute_gaps(child)
            lmost = min(_lm, lmost)
            rmost = max(_rm, rmost)
            descs += _de
        self._gaps[node.ord] = rmost - lmost - descs
        return lmost, rmost, descs + 1

    def should_print_tree(self, root):
        """Should this tree be printed?"""
        if not self.marked_only:
            return True
        if any(self.is_marked(n) for n in root.descendants(add_self=1)):
            return True
        if not self.print_comments or root.comment is None or self.mark_re is None:
            return False
        return self.mark_re.search(root.comment)

    def process_tree(self, root):
        """Print the tree to (possibly redirected) sys.stdout."""
        allnodes = root.descendants(add_self=1)
        if not self.should_print_tree(root):
            return
        self._index_of = {allnodes[i].ord: i for i in range(len(allnodes))}
        self.lines = [''] * len(allnodes)
        self.lengths = [0] * len(allnodes)

        # Precompute the number of non-projective gaps for each subtree
        if self.minimize_cross:
            self._gaps = [0,] * (1 + len(root.root.descendants))
            self._compute_gaps(root)

        # Precompute lines for printing
        stack = [root,]
        while stack:
            node = stack.pop()
            children = node.children(add_self=1)
            min_idx, max_idx = self._index_of[children[0].ord], self._index_of[children[-1].ord]
            max_length = max([self.lengths[i] for i in range(min_idx, max_idx+1)])
            for idx in range(min_idx, max_idx+1):
                idx_node = allnodes[idx]
                filler = '─' if self._ends(idx, '─╭╰├╪') else ' '
                self._add(idx, filler * (max_length - self.lengths[idx]))

                topmost = idx == min_idx
                botmost = idx == max_idx
                if idx_node is node:
                    self._add(idx, self._draw[botmost][topmost])
                    self.add_node(idx, node)
                else:
                    if idx_node.parent is not node:
                        self._add(idx, self._vert[self._ends(idx, '─╭╰├╪')])
                    else:
                        self._add(idx, self._space[botmost][topmost])
                        if idx_node.is_leaf():
                            self._add(idx, self._horiz)
                            self.add_node(idx, idx_node)
                        else:
                            stack.append(idx_node)

            # sorting the stack to minimize crossings of edges
            if self.minimize_cross:
                stack = sorted(stack, key=lambda x: -self._gaps[x.ord])

        # Print headers (if required) and the tree itself
        if self.print_sent_id:
            print('# sent_id = ' + root.address())
        if self.print_text:
            print("# text = " + (root.get_sentence() if root.is_root() else root.compute_text()))
        if self.print_comments and root.comment:
            print('#' + self.colorize_comment(root.comment.rstrip().replace('\n', '\n#')))
        for line in self.lines:
            print(line)

        if self.add_empty_line:
            print('')

    def _ends(self, idx, chars):
        return bool(self.lines[idx] and self.lines[idx][-1] in chars)

    def before_process_document(self, document):
        """Initialize ANSI colors if color is True or 'auto'.

        If color=='auto', detect if sys.stdout is interactive
        (terminal, not redirected to a file).
        """
        super().before_process_document(document)
        if self.color == 'auto':
            self.color = sys.stdout.isatty()
            if self.color:
                colorama.init()
        if self.print_doc_meta:
            for key, value in sorted(document.meta.items()):
                print('%s = %s' % (key, value))

    def _add(self, idx, text):
        self.lines[idx] += text
        self.lengths[idx] += len(text)

    def add_node(self, idx, node):
        """Render a node with its attributes."""
        if not node.is_root():
            values = node.get_attrs(self.attrs, undefs=self.print_undef_as)
            self.lengths[idx] += 1 + len(' '.join(values))
            if self.color:
                marked = self.is_marked(node)
                for i, attr in enumerate(self.attrs):
                    values[i] = self.colorize_attr(attr, values[i], marked)
            self.lines[idx] += ' ' + ' '.join(values)

    def is_marked(self, node):
        """Should a given node be highlighted?"""
        return self.mark_re.search(str(node.misc)) if self.mark_re is not None else False

    def colorize_comment(self, comment):
        """Return a string with color markup for a given comment."""
        if self.mark_re is None:
            return comment
        return self.mark_re.sub(colored(r'\g<0>', None, None, ['reverse', 'bold']), comment)

    @staticmethod
    def colorize_attr(attr, value, marked):
        """Return a string with color markup for a given attr and its value."""
        color = COLOR_OF.get(attr, None)
        return colored(value, color, None, ['reverse', 'bold'] if marked else None)
