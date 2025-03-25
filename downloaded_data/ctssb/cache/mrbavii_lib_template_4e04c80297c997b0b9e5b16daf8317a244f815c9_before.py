""" A parser for the template engine. """

__author__      = "Brian Allen Vanderburg II"
__copyright__   = "Copyright 2016"
__license__     = "Apache License 2.0"


import re

from .errors import *
from .nodes import *
from .expr import *


class TemplateParser(object):
    """ A base tokenizer. """

    def __init__(self, template, text):
        """ Initialize the parser. """

        self._template = template
        self._text = text
        
        # Stack and line number
        self._ops_stack = []
        self._nodes = []
        self._stack = [self._nodes]
        self._line = 1

        # Buffer for plain text segments
        self._buffer = []
        self._pre_strip = False
        self._auto_strip = False

    def parse(self):
        """ Parse the template and return the node list. """
        
        self._parse_body()
        self._flush_buffer()

        if self._ops_stack:
            raise SyntaxError(
                "Unmatched action tag", 
                self._ops_stack[-1][0],
                self._ops_stack[-1][1]
            )

        return self._nodes

    def _parse_body(self):
        """ Parse the entire body. """

        last = 0
        while True:

            pos = self._text.find("{", last)
            if pos == -1:
                # No more tags
                self._buffer.append(self._text[last:])
                return
            else:
                # Found the start of a tag
                text = self._text[last:pos]
                self._line += text.count("\n")
                self._buffer.append(text)

                last = self._parse_tag(pos)

    def _parse_tag(self, pos):
        """ Parse a tag found at pos """
        tag = self._text[pos:pos + 2]
        if not tag in ("{#", "{%", "{{"):
            raise SyntaxError(
                "Unknown tag {0}".format(tag),
                self._template._filename,
                self._line
            )

        start = pos + 2
        if self._text[start:start + 1] == "-":
            post_strip = True
            start += 1
        else:
            post_strip = False

        self._flush_buffer(post_strip)
        if tag == "{#":
            return self._parse_tag_comment(start)
        elif tag == "{%":
            return self._parse_tag_action(start)
        elif tag == "{{":
            return self._parse_tag_emitter(start)

    def _parse_tag_ending(self, start, ending, bare=True):
        """ Parse an expected tag ending. """

        # Find our ending
        pos = self._text.find(ending, start)
        if pos == -1:
            raise SyntaxError(
                "Expecting end tag: {0}".format(ending),
                self._template._filename,
                self._line
            )
            
        if (pos  > start) and (self._text[pos - 1:pos] == "-"):
            self._pre_strip = True
            ending = "-" + ending
        else:
            self._pre_strip = False

        # Make sure only whitespace was before it
        guts = self._text[start:pos + 2]
        if bare and (guts.strip() != ending):
            raise SyntaxError(
                "Expecting end tag: {0}".format(ending),
                self._template._filename,
                self._line
            )

        self._line += guts.count("\n")
        return pos + 2

    def _parse_tag_comment(self, start):
        """ Parse a comment tag: """

        return self._parse_tag_ending(start, "#}", False)

    def _parse_tag_action(self, start):
        """ Parse some action tag. """
        
        # Determine the action
        pos = self._skip_space(start, "Incomplete tag")
        end = self._find_space(pos, "Incomplete tag")
        action = self._text[pos:end]
        
        if action == "if":
            pos = self._parse_action_if(end)
        elif action == "elif":
            pos = self._parse_action_elif(end)
        elif action == "else":
            pos =  self._parse_action_else(end)
        elif action == "for":
            pos = self._parse_action_for(end)
        elif action == "set":
            pos = self._parse_action_set(end)
        elif action == "with":
            pos = self._parse_action_with(end)
        elif action == "include":
            pos = self._parse_action_include(end)
        elif action == "section":
            pos = self._parse_action_section(end)
        elif action == "use":
            pos = self._parse_action_use(end)
        elif action == "def":
            pos = self._parse_action_def(end)
        elif action == "call":
            pos = self._parse_action_call(end)
        elif action.startswith("end"):
            pos = self._parse_action_end(end, action)
        elif action == "autostrip":
            self._auto_strip = True
            pos = end
        elif action == "no_autostrip":
            self._auto_strip = False
            pos = end
        else:
            raise SyntaxError(
                "Unknown action tag: {0}".format(action),
                self._template._filename,
                self._line
            )

        return self._parse_tag_ending(pos, "%}")

    def _parse_action_if(self, start):
        """ Parse an if action. """
        line = self._line
        pos = self._skip_space(start, "Expected expression")
        (expr, pos) = self._parse_expr(pos)
        
        node = IfNode(self._template, line, expr)
        
        self._ops_stack.append(("if", line))
        self._stack[-1].append(node)
        self._stack.append(node._nodes)
        return pos

    def _parse_action_elif(self, start):
        """ Parse an elif action. """
        line = self._line
        pos = self._skip_space(start, "Expected expression")
        (expr, pos) = self._parse_expr(pos)

        if not self._ops_stack:
            raise SyntaxError(
                "Mismatched elif",
                self._template._filename,
                line
            )

        what = self._ops_stack[-1]
        if what[0] != "if":
            raise SyntaxError(
                "Mismatched elif",
                self._template._filename,
                line
            )

        self._stack.pop()
        node = self._stack[-1][-1]
        node.add_elif(expr)
        self._stack.append(node._nodes)

        return pos

    def _parse_action_else(self, start):
        """ Parse an else. """
        line = self._line

        if not self._ops_stack:
            raise SyntaxError(
                "Mismatched else",
                self._template._filename,
                line
            )

        what = self._ops_stack[-1]
        if what[0] != "if":
            raise SyntaxError(
                "Mismatched else",
                self._template._filename,
                line
            )

        self._stack.pop()
        node = self._stack[-1][-1]
        node.add_else()
        self._stack.append(node._nodes)

        return start

    def _parse_action_for(self, start):
        """ Parse a for statement. """
        line = self._line

        pos = self._skip_space(start, "Expected variable")
        (var, pos) = self._parse_var(pos, False)

        pos = self._skip_word(pos, "in", "Expected 'in'")

        (expr, pos) = self._parse_expr(pos)

        node = ForNode(self._template, line, var, expr)
        self._ops_stack.append(("for", line))
        self._stack[-1].append(node)
        self._stack.append(node._nodes)

        return pos
    
    def _parse_action_set(self, start):
        """ Parse a set statement. """
        line = self._line

        (assigns, pos) = self._parse_multi_assign(start)

        node = AssignNode(self._template, line, assigns)
        self._stack[-1].append(node)

        return pos

    def _parse_action_with(self, start):
        """ Parse a with statement. """
        line = self._line

        self._ops_stack.append(("with", line))

        (assigns, pos) = self._parse_multi_assign(start)

        node = WithNode(self._template, line, assigns)
        self._stack[-1].append(node)
        self._stack.append(node._nodes)

        return pos


    def _parse_action_include(self, start):
        """ Parse an include node. """
        line = self._line

        pos = self._skip_space(start, "Expecting expression")
        (expr, pos) = self._parse_expr(pos)

        node = IncludeNode(self._template, line, expr)
        self._stack[-1].append(node)

        return pos

    def _parse_action_section(self, start):
        """ Parse a section node. """
        line = self._line

        pos = self._skip_space(start, "Expecting expression")
        (expr, pos) = self._parse_expr(pos)

        self._ops_stack.append(("section", line))
        node = SectionNode(self._template, line, expr)
        self._stack[-1].append(node)
        self._stack.append(node._nodes)

        return pos

    def _parse_action_use(self, start):
        """ Parse a use section node. """
        line = self._line

        pos = self._skip_space(start, "Expecting expression")
        (expr, pos) = self._parse_expr(pos)

        node = UseSectionNode(self._template, line, expr)
        self._stack[-1].append(node)

        return pos

    def _parse_action_def(self, start):
        """ Parse a local or global def. """
        line = self._line

        pos = self._skip_space(start, "Expecting string")
        (name, pos) = self._parse_string(pos)

        self._ops_stack.append(("def", line))

        nodes = self._defines.setdefault(name, [])
        self._stack.append(nodes)

        return pos

    def _parse_action_call(self, start):
        """ Parse a call to a local or global def. """
        line = self._line

        pos = self._skip_space(start, "Expecting string")
        (name, pos) = self._parse_string(pos)


        nodes = self._template._defines.get(name, None)
        if nodes is None:
            raise UnknownDefineError(
                name,
                self._template._filename,
                self._line
            )

        self._stack[-1].extend(nodes)

        return pos


    def _parse_action_end(self, start, action):
        """ Parse an end tag """
        line = self._line

        if not self._ops_stack:
            raise SyntaxError(
                "To many ends: {0}".format(action),
                self._template._filename,
                line
            )

        what = self._ops_stack[-1]
        if what[0] != action[3:]:
            raise SyntaxError(
                "Mismatched end tag: {0}".format(action),
                self._template._filename,
                line
            )

        self._ops_stack.pop()
        self._stack.pop()

        return start

    def _parse_tag_emitter(self, start):
        """ Parse an emitter tag. """
        line = self._line

        pos = self._skip_space(start, "Expected expression")
        (expr, pos) = self._parse_expr(pos)
        pos = self._parse_tag_ending(pos, "}}")

        if isinstance(expr, ValueExpr):
            node = TextNode(self._template, line, str(expr.eval()))
        else:
            node = VarNode(self._template, line, expr)
        self._stack[-1].append(node)
        return pos
        
    def _skip_space(self, start, errmsg=None):
        """ Return the first non-whitespace position. """
        for pos in range(start, len(self._text)):
            ch = self._text[pos]
            if ch == "\n":
                self._line += 1
                continue
            elif ch in (" ", "\t"):
                continue

            return pos

        if errmsg:
            raise SyntaxError(
                errmsg,
                self._template._filename,
                self._line
            )

        return -1

    def _find_space(self, start, errmsg=None):
        """ Find the next space, do not increase line number. """
        for pos in range(start, len(self._text)):
            if self._text[pos] in ("\n", " ", "\t"):
                return pos
        
        if errmsg:
            raise SyntaxError(
                errmsg,
                self._template._filename,
                self._line
            )

        return -1

    def _skip_word(self, start, word, errmsg=None, space=True):
        """ Skip a word. """
        pos = self._skip_space(start, errmsg)
        if pos == -1:
            return -1

        if space:
            end = self._find_space(pos, errmsg)
            if pos == -1:
                return -1
        else:
            end = pos + len(word)

        if self._text[pos:end] == word:
            return end

        if errmsg:
            raise SyntaxError(
                errmsg,
                self._template._filename,
                self._line
            )

        return -1

    def _parse_expr(self, start):
        """ Parse an expression and return (node, pos) """
        pos = self._skip_space(start, "Expecting expression")

        ch = self._text[pos:pos + 1]

        if ch == "\"":
            (value, pos) = self._parse_string(pos)
            node = ValueExpr(self._template, self._line, str(value))
            return (node, pos)

        if ch == "[":
            return self._parse_expr_list(pos + 1)

        if ch in "0123456789.":
            return self._parse_expr_number(pos)

        (var, pos) = self._parse_var(pos)
        if self._text[pos:pos + 1] == "(":
            (nodes, pos) = self._parse_expr_items(pos + 1, ")")
            node = FuncExpr(self._template, self._line, var, nodes)
        elif self._text[pos:pos + 1] == "[":
            (nodes, pos) = self._parse_expr_items(pos + 1, "]")
            node = IndexExpr(self._template, self._line, var, nodes)
        else:
            node = VarExpr(self._template, self._line, var)
          
        return (node, pos)

    def _parse_expr_list(self, start):
        """ Pare an expression that's a list. """
        (nodes, pos) = self._parse_expr_items(start, "]")

        if nodes and all(isinstance(node, ValueExpr) for node in nodes):
            node = ValueExpr(self._template, nodes[0]._line, [node.eval() for node in nodes])
        else:
            node = ListExpr(self._template, self._line, nodes)
        return (node, pos)

    def _parse_expr_number(self, start):
        """ Parse a number """
        result = []
        for pos in range(start, len(self._text)):
            ch = self._text[pos]
            if not ch in "0123456789.":
                break
            result.append(ch)

        if not result:
            raise SyntaxError(
                "Expecting number",
                self._template._filename,
                self._line
            )

        result = "".join(result)

        if not "." in result:
            node = ValueExpr(self._template, self._line, int(result))
        elif result.count("." == 1):
            node = ValueExpr(self._template, self._line, float(result))
        else:
            raise SyntaxError(
                "Expecting number",
                self._template._filename,
                self._line
            )

        return (node, pos)

    def _parse_expr_items(self, start, ending):
        """ Parse a list of items """
        items = []

        pos = start
        first = True
        while True:
            pos = self._skip_space(pos, "Expecting expression")
            if self._text[pos] == ending:
                return (items, pos + 1)

            if not first:
                if self._text[pos] != ",":
                    raise SyntaxError(
                        "Expecting comma",
                        self._template._filename,
                        self._line
                    )
                pos = self._skip_space(pos + 1, "Expecting expression")
            first = False

            (node, pos) = self._parse_expr(pos)
            items.append(node)

    def _parse_assign(self, start):
        """ Parse a var = expr assignment, return (var, expr, pos) """
        line = self._line

        pos = self._skip_space(start, "Expected variable")
        (var, pos) = self._parse_var(pos, False)

        pos = self._skip_word(pos, "=", "Expected '='", False)
        (expr, pos) = self._parse_expr(pos)

        return (var, expr, pos)

    def _parse_multi_assign(self, start):
        """ Parse multiple var = expr statemetns, return ( [(var, expr)], pos) """
        assigns = []

        pos = start
        first = True
        while True:
            pos = self._skip_space(pos)
            if self._text[pos] in "-%": # Ending of the tag
                break

            if not first:
                if self._text[pos] != ",":
                    raise SyntaxError(
                        "Expecting comma",
                        self._template._filename,
                        line
                    )
                pos = self._skip_space(pos + 1, "Expecting variable")
            first = False

            (var, expr, pos) = self._parse_assign(pos)
            assigns.append((var, expr))

        return (assigns, pos)

    def _parse_string(self, start):
        """ Parse a string and return (str, pos) """

        if self._text[start:start + 1] != "\"":
            raise SyntaxError(
                "Expected string",
                self._template._filename,
                self._line
            )

        escaped = False
        result = []
        for pos in range(start + 1,len(self._text)):
            ch = self._text[pos]
            
            if escaped:
                escaped = False
                if ch == "n":
                    result.append("\n")
                elif ch == "t":
                    result.append("\t")
                elif ch == "\\":
                    result.append("\\")
                elif ch == "\"":
                    result.append("\"")
                continue

            if ch == "\"":
                return ("".join(result), pos + 1)

            if ch == "\\":
                escaped = True
                continue

            result.append(ch)

        raise SyntaxError(
            "Expected end of string",
            self._template._filename,
            self._line
        )

    def _parse_var(self, start, allow_dots=True):
        """ Parse a variable and return (var, pos) """

        first = True
        result = []
        current = []
        for pos in range(start, len(self._text)):
            ch = self._text[pos]

            if ch == ".":
                if not allow_dots:
                    raise SyntaxError(
                        "Dotted variable not allowed",
                        self._template._filename,
                        self._line
                    )

                if not current:
                    raise SyntaxError(
                        "Expected variable segment",
                        self._template._filename,
                        self._line
                    )

                result.append("".join(current))
                current = []
                first = True
                continue

            if ch in ("abcdefghijklmnopqrstuvwxyz"
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "0123456789_"):

                if first and ch in "0123456789":
                    raise SyntaxError(
                        "Expected variable",
                        self._template._filename,
                        self._line
                    )

                current.append(ch)
                first = False
            else:
                break

        if first == True:
            raise SyntaxError(
                "Epected variable",
                self._template._filename,
                self._line
            )

        if allow_dots:
            result.append("".join(current))
            return (result, pos)
        else:
            return ("".join(current), pos)
                


    def _flush_buffer(self, post=False):
        """ Flush the buffer to output. """
        if self._buffer:
            text = "".join(self._buffer)

            if self._auto_strip:
                text = text.strip()
            else:
                if self._pre_strip:
                    # If the previous tag had a white-space control {{ ... -}}
                    # trim the start of this buffer up to/including a new line
                    first_nl = text.find("\n")
                    if first_nl == -1:
                        text = text.lstrip()
                    else:
                        text = text[:first_nl + 1].lstrip() + text[first_nl + 1:]

                if post:
                    # If the current tag has a white-space contro {{- ... }}
                    # trim the end of the buffer up to/including a new line
                    last_nl = text.find("\n")
                    if last_nl == -1:
                        text = text.rstrip()
                    else:
                        text = text[:last_nl] + text[last_nl:].rstrip()
            
            if text:
                node = TextNode(self._template, self._line, text)
                self._stack[-1].append(node)

        self._buffer = []

