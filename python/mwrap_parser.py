"""
mwrap_parser.py — Recursive descent parser for mwrap .mw files.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Converted to Python by Zydrunas Gimbutas (2026),
with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
"""

import sys
from mwrap_ast import (
    Expr, TypeQual, Var, Func, VT,
    promote_int, id_string, add_inherits,
)
from mwrap_lexer import Lexer, Token, TokenType
from mwrap_typecheck import typecheck
from mwrap_mgen import print_matlab_call


class ParseError(Exception):
    pass


class Parser:
    """Recursive descent parser for mwrap '#' lines.

    Usage:
        parser = Parser(lexer, ctx, mexfunc=mexfunc)
        for tok in lexer.lex_file(filename):
            parser.feed(tok)
        # After all files:
        funcs = parser.funcs        # list[Func]
        err_flag = parser.err_flag
    """

    def __init__(self, lexer, ctx, mexfunc="mexfunction"):
        self.lexer = lexer
        self.ctx = ctx
        self.mexfunc = mexfunc

        # Function list
        self.funcs = []
        self.func_id = 0
        self.func_lookup = {}       # id_string -> first Func with that sig

        # Error tracking
        self.type_errs = 0
        self.err_flag = 0

        # Token buffer for current '#' line
        self._tokens = []
        self._pos = 0
        self._collecting = False    # True while inside a '#' line

    # ------------------------------------------------------------------
    # Token stream interface
    # ------------------------------------------------------------------

    def feed(self, tok):
        """Feed one token from the lexer."""
        if tok.type == TokenType.EOF:
            self._flush_pending(tok)
            return
        if tok.type == TokenType.NON_C_LINE:
            self._flush_pending(tok)
            return

        # Accumulate tokens from a '#' line
        self._tokens.append(tok)

        # A ';' terminates a statement — parse it
        if tok.type == TokenType.PUNCT and tok.value == ';':
            self._parse_line()
            self._tokens.clear()

    def _flush_pending(self, tok):
        """Report error if there are tokens pending without a ';'."""
        if self._tokens:
            tname = "NON_C_LINE" if tok.type == TokenType.NON_C_LINE else "$end"
            fname = self.lexer.current_ifname
            line = tok.line
            print(f"Parse error ({fname}:{line}): syntax error, unexpected {tname}, expecting ';'",
                  file=sys.stderr)
            self.err_flag += 1
            self._tokens.clear()

    def finish_file(self):
        """Call after all tokens from one input file have been fed."""
        # Flush any pending tokens (missing ';' at EOF)
        if self._tokens:
            fname = self.lexer.current_ifname
            line = self.lexer.linenum
            print(f"Parse error ({fname}:{line}): syntax error, unexpected $end, expecting ';'",
                  file=sys.stderr)
            self.err_flag += 1
            self._tokens.clear()
        if self.type_errs:
            print(f"{self.lexer.current_ifname}: {self.type_errs} type errors detected",
                  file=sys.stderr)
            self.err_flag += self.type_errs
        self.type_errs = 0

    # ------------------------------------------------------------------
    # Token access helpers
    # ------------------------------------------------------------------

    def _peek(self):
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(TokenType.EOF, "", 0)

    def _advance(self):
        tok = self._peek()
        self._pos += 1
        return tok

    def _expect(self, ttype, value=None):
        tok = self._advance()
        if tok.type != ttype or (value is not None and tok.value != value):
            exp = f"{ttype.name}"
            if value:
                exp += f" '{value}'"
            self._error(f"Expected {exp}, got {tok.type.name} '{tok.value}'")
        return tok

    def _expect_punct(self, ch):
        return self._expect(TokenType.PUNCT, ch)

    def _at(self, ttype, value=None):
        t = self._peek()
        if t.type != ttype:
            return False
        if value is not None and t.value != value:
            return False
        return True

    def _at_punct(self, ch):
        return self._at(TokenType.PUNCT, ch)

    def _line(self):
        """Current line number for error messages."""
        if self._tokens:
            return self._tokens[0].line
        return self.lexer.linenum

    def _error(self, msg):
        fname = self.lexer.current_ifname
        line = self._line()
        print(f"Parse error ({fname}:{line}): {msg}", file=sys.stderr)
        raise ParseError(msg)

    # ------------------------------------------------------------------
    # Top-level statement parse
    # ------------------------------------------------------------------

    def _parse_line(self):
        """Parse one complete '#' line (already accumulated in _tokens)."""
        self._pos = 0
        try:
            self._statement()
        except ParseError:
            self.err_flag += 1

    def _statement(self):
        """statement ::= tdef | classdef | basevar '=' funcall | funcall"""
        tok = self._peek()

        if tok.type == TokenType.TYPEDEF:
            self._tdef()
            return

        if tok.type == TokenType.CLASS:
            self._classdef()
            return

        # Distinguish:  basevar = funcall   vs   funcall
        # A funcall starts with: ID -> ... | ID ( | FORTRAN ID | NEW ID
        # A basevar starts with: ID ID  or  ID qual ID
        # The disambiguator: look for '=' before '(' or ';'
        if self._has_assignment():
            bv = self._basevar()
            self._expect_punct('=')
            fc = self._funcall()
            fc.ret = [bv]
            self._finish_func(fc)
        else:
            fc = self._funcall()
            self._finish_func(fc)

    def _has_assignment(self):
        """Lookahead: is there a '=' before '(' or ';'?"""
        depth = 0
        for i in range(len(self._tokens)):
            t = self._tokens[i]
            if t.type == TokenType.PUNCT:
                if t.value == '[':
                    depth += 1
                elif t.value == ']':
                    depth -= 1
                elif depth == 0 and t.value == '=':
                    return True
                elif depth == 0 and t.value == '(':
                    return False
                elif depth == 0 and t.value == ';':
                    return False
        return False

    # ------------------------------------------------------------------
    # typedef / classdef
    # ------------------------------------------------------------------

    def _tdef(self):
        """TYPEDEF ID ID ';'"""
        self._expect(TokenType.TYPEDEF)
        space = self._expect(TokenType.ID).value
        name = self._expect(TokenType.ID).value
        self._expect_punct(';')

        if space == "numeric":
            self.ctx.add_scalar_type(name)
        elif space == "dcomplex":
            self.ctx.add_zscalar_type(name)
        elif space == "fcomplex":
            self.ctx.add_cscalar_type(name)
        elif space == "mxArray":
            self.ctx.add_mxarray_type(name)
        else:
            print(f"Unrecognized typespace: {space}", file=sys.stderr)
            self.type_errs += 1

    def _classdef(self):
        """CLASS ID ':' inheritslist ';'"""
        self._expect(TokenType.CLASS)
        child = self._expect(TokenType.ID).value
        self._expect_punct(':')
        parents = self._inheritslist()
        self._expect_punct(';')
        add_inherits(self.ctx, child, parents)

    def _inheritslist(self):
        """ID (',' ID)* — returns list[str]"""
        result = [self._expect(TokenType.ID).value]
        while self._at_punct(','):
            self._advance()
            result.append(self._expect(TokenType.ID).value)
        return result

    # ------------------------------------------------------------------
    # funcall / func
    # ------------------------------------------------------------------

    def _funcall(self):
        """funcall ::= func '(' args ')' ';'"""
        f = self._func()
        self._expect_punct('(')
        f.args = self._args()
        self._expect_punct(')')
        self._expect_punct(';')
        return f

    def _func(self):
        """func ::= ID '->' ID '.' ID | ID | FORTRAN ID | NEW ID"""
        tok = self._peek()

        if tok.type == TokenType.FORTRAN:
            self._advance()
            name = self._expect(TokenType.ID).value
            f = Func(None, None, name,
                     self.lexer.current_ifname, self._line())
            f.fort = True
            return f

        if tok.type == TokenType.NEW:
            self._advance()
            classname = self._expect(TokenType.ID).value
            return Func(None, classname, "new",
                        self.lexer.current_ifname, self._line())

        # ID — could be plain func, or  thisvar -> classname . method
        name = self._expect(TokenType.ID).value

        if self._at_punct('-'):
            # thisvar -> classname . method
            self._advance()  # '-'
            self._expect_punct('>')
            classname = self._expect(TokenType.ID).value
            self._expect_punct('.')
            method = self._expect(TokenType.ID).value
            return Func(name, classname, method,
                        self.lexer.current_ifname, self._line())

        return Func(None, None, name,
                    self.lexer.current_ifname, self._line())

    # ------------------------------------------------------------------
    # args / var
    # ------------------------------------------------------------------

    def _args(self):
        """args ::= var (',' var)* | ε — returns list[Var]"""
        if self._at_punct(')'):
            return []
        result = [self._var()]
        while self._at_punct(','):
            self._advance()
            result.append(self._var())
        return result

    def _var(self):
        """var ::= [devicespec] [iospec] TYPE [qual] (NAME | NUMBER | STRING)
           OR:  [devicespec] [iospec] TYPE NAME [aqual]    (post-name array)
        """
        devicespec = self._devicespec()
        iospec = self._iospec()
        basetype = promote_int(self.ctx, self._expect(TokenType.ID).value)

        # Now we may see:
        #   quals then NAME/NUMBER/STRING
        #   NAME/NUMBER/STRING then optional aqual
        #   Just NAME/NUMBER/STRING (no qual)
        tok = self._peek()

        if tok.type == TokenType.PUNCT and tok.value in ('*', '&', '['):
            # quals before name
            qual = self._quals()
            name = self._name_or_literal()
            return Var(devicespec, iospec, basetype, qual, name)

        # NAME/NUMBER/STRING first, then optional aqual
        name = self._name_or_literal()

        # Check for post-name aqual:  name [ ... ] or name [ ... ] &
        if self._at_punct('['):
            qual = self._aqual()
            return Var(devicespec, iospec, basetype, qual, name)

        return Var(devicespec, iospec, basetype, None, name)

    def _name_or_literal(self):
        tok = self._peek()
        if tok.type in (TokenType.ID, TokenType.NUMBER, TokenType.STRING):
            self._advance()
            return tok.value
        self._error(f"Expected name, number or string, got {tok.type.name} '{tok.value}'")

    def _devicespec(self):
        tok = self._peek()
        if tok.type == TokenType.CPU:
            self._advance()
            return 'c'
        if tok.type == TokenType.GPU:
            self._advance()
            return 'g'
        return 'c'

    def _iospec(self):
        tok = self._peek()
        m = {
            TokenType.INPUT:   'i',
            TokenType.OUTPUT:  'o',
            TokenType.INOUT:   'b',
        }
        if tok.type in m:
            self._advance()
            return m[tok.type]
        return 'i'

    def _quals(self):
        """quals ::= '*' | '&' | aqual"""
        if self._at_punct('*'):
            self._advance()
            return TypeQual('*')
        if self._at_punct('&'):
            self._advance()
            return TypeQual('&')
        return self._aqual()

    def _aqual(self):
        """aqual ::= arrayspec ['&']"""
        exprs = self._arrayspec()
        if self._at_punct('&'):
            self._advance()
            return TypeQual('r', exprs)
        return TypeQual('a', exprs)

    def _arrayspec(self):
        """'[' exprs ']' — returns list[Expr]"""
        self._expect_punct('[')
        e = self._exprs()
        self._expect_punct(']')
        return e

    def _exprs(self):
        """exprs ::= expr (',' expr)* | ε — returns list[Expr]"""
        if self._at_punct(']'):
            return []
        result = [self._expr()]
        while self._at_punct(','):
            self._advance()
            result.append(self._expr())
        return result

    def _expr(self):
        """expr ::= ID | NUMBER"""
        tok = self._peek()
        if tok.type in (TokenType.ID, TokenType.NUMBER):
            self._advance()
            return Expr(tok.value)
        self._error(f"Expected expression, got {tok.type.name} '{tok.value}'")

    def _basevar(self):
        """basevar ::= ID [quals] ID  — always output, cpu"""
        basetype = promote_int(self.ctx, self._expect(TokenType.ID).value)

        # Peek: quals or name?
        tok = self._peek()
        if tok.type == TokenType.PUNCT and tok.value in ('*', '&', '['):
            qual = self._quals()
            name = self._expect(TokenType.ID).value
            return Var('c', 'o', basetype, qual, name)

        # NAME then optional aqual
        name = self._expect(TokenType.ID).value

        if self._at_punct('['):
            qual = self._aqual()
            return Var('c', 'o', basetype, qual, name)

        return Var('c', 'o', basetype, None, name)

    # ------------------------------------------------------------------
    # Post-parse: typecheck, MATLAB stub, add to func list
    # ------------------------------------------------------------------

    def _finish_func(self, func):
        """Typecheck, emit MATLAB stub, add to function list."""
        self.func_id += 1
        func.id = self.func_id

        self.type_errs += typecheck(self.ctx, func, self._line())

        if self.lexer.outfp:
            print_matlab_call(self.lexer.outfp, func, self.mexfunc)

        self._add_func(func)

    def _add_func(self, func):
        """Add func to list; deduplicate via id_string."""
        ids = id_string(self.ctx, func)

        first = self.func_lookup.get(ids)
        if first:
            # Same signature — add to first occurrence's same list
            first.same.append(func)
        else:
            # New unique signature — append to main list
            self.funcs.append(func)
            self.func_lookup[ids] = func
