"""
mwrap_lexer.py — Line-oriented lexer for .mw files.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Converted to Python by Zydrunas Gimbutas (2026),
with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
"""

import re
import sys
import os
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, TextIO, List


class TokenType(Enum):
    ID        = auto()
    NUMBER    = auto()
    STRING    = auto()
    NEW       = auto()
    FORTRAN   = auto()
    INPUT     = auto()
    OUTPUT    = auto()
    INOUT     = auto()
    CLASS     = auto()
    TYPEDEF   = auto()
    CPU       = auto()
    GPU       = auto()
    PUNCT     = auto()      # single characters: ( ) , ; * & [ ] . - > = :
    NON_C_LINE = auto()
    EOF       = auto()


KEYWORDS = {
    "new":      TokenType.NEW,
    "FORTRAN":  TokenType.FORTRAN,
    "input":    TokenType.INPUT,
    "output":   TokenType.OUTPUT,
    "inout":    TokenType.INOUT,
    "class":    TokenType.CLASS,
    "typedef":  TokenType.TYPEDEF,
    "cpu":      TokenType.CPU,
    "gpu":      TokenType.GPU,
}

# Regex for tokenising a '#' line body
_TOKEN_RE = re.compile(
    r"(//[^\n]*)"               # comment (rest of line) — skip
    r"|('[^'\n]*'?)"            # string literal (single-quoted)
    r"|((?:::)?[_a-zA-Z][_a-zA-Z0-9]*(?:::(?:[_a-zA-Z][_a-zA-Z0-9]*))*)"  # ID (may have ::)
    r"|([0-9]+)"                # number
    r"|([->()\[\],;*&=:.])"     # punctuation
    r"|[ \t\r]+"                # whitespace — skip
)


@dataclass
class Token:
    type: TokenType
    value: str
    line: int


def _is_name_char(c):
    return c.isalnum() or c == '_'


def _fname_scan_line(text):
    """Extract function name from '@function ...' tail, return name.m."""
    paren = text.find('(')
    if paren < 0:
        paren = len(text)
    # Walk back from paren to find last alnum
    end = paren
    while end > 0 and not _is_name_char(text[end - 1]):
        end -= 1
    start = end
    while start > 0 and _is_name_char(text[start - 1]):
        start -= 1
    name = text[start:end]
    return name + ".m"


class Lexer:
    """Line-oriented lexer for .mw files.

    Usage:
        lex = Lexer(outfp, outcfp, mbatching_flag, listing_flag)
        for tok in lex.lex_file(filename):
            ...   # only tokens from '#' lines; NON_C_LINE for other lines
    """

    def __init__(self, outfp=None, outcfp=None,
                 mbatching_flag=False, listing_flag=False):
        self.outfp: Optional[TextIO] = outfp
        self.outcfp: Optional[TextIO] = outcfp
        self.mbatching_flag: bool = mbatching_flag
        self.listing_flag: bool = listing_flag
        self.linenum: int = 0
        self.current_ifname: str = ""

        # File include stack
        self._file_stack: List = []          # [(fp, linenum, ifname), ...]
        self._current_fp: Optional[TextIO] = None

    # ------------------------------------------------------------------
    # public interface
    # ------------------------------------------------------------------

    def lex_file(self, filename):
        """Yield Token objects from *filename*."""
        fp = open(filename, "r")
        self._current_fp = fp
        self.current_ifname = filename
        self.linenum = 1
        yield from self._lex_stream()

    # ------------------------------------------------------------------
    # directive handlers
    # ------------------------------------------------------------------

    def _handle_block_c(self, line):
        """Process a line in block C mode. Returns False when block ends."""
        stripped = line.rstrip('\r\n')
        if re.match(r'^\$\][ \t\r]*$', stripped):
            self.linenum += 1
            return False
        if self.outcfp:
            self.outcfp.write(line)
        self.linenum += 1
        return True

    def _handle_comment(self):
        """Handle // comment line."""
        self.linenum += 1
        yield Token(TokenType.NON_C_LINE, "", self.linenum - 1)

    def _handle_function(self, stripped):
        """Handle @function directive."""
        tail = stripped[len("@function"):]
        tail = tail.rstrip('\r\n')
        fname = _fname_scan_line(tail)
        if self.mbatching_flag:
            if self.outfp:
                self.outfp.close()
            try:
                self.outfp = open(fname, "w")
            except OSError:
                print(f"Error: Could not write {fname}",
                      file=sys.stderr)
                sys.exit(1)
        if self.listing_flag:
            print(fname)
        if self.outfp:
            self.outfp.write(f"function{tail}\n")
        self.linenum += 1
        yield Token(TokenType.NON_C_LINE, "", self.linenum - 1)

    def _handle_include(self, stripped):
        """Handle @include directive. Pushes current file onto stack."""
        rest = stripped[len("@include"):].strip().rstrip('\r\n')
        if len(self._file_stack) >= 10:
            print("Error: Includes nested too deeply",
                  file=sys.stderr)
            sys.exit(1)
        self._file_stack.append(
            (self._current_fp, self.linenum, self.current_ifname))
        try:
            new_fp = open(rest, "r")
        except OSError:
            print(f"Error: Could not read '{rest}'",
                  file=sys.stderr)
            sys.exit(1)
        self.current_ifname = rest
        self.linenum = 1
        self._current_fp = new_fp

    def _handle_redirect(self, stripped):
        """Handle @ redirect directive."""
        rest = stripped[1:].strip().rstrip('\r\n')
        if self.mbatching_flag:
            if self.outfp:
                self.outfp.close()
                self.outfp = None
            if rest:
                try:
                    self.outfp = open(rest, "w")
                except OSError:
                    print(f"Error: Could not write {rest}",
                          file=sys.stderr)
                    sys.exit(1)
        if self.listing_flag and rest:
            print(rest)
        self.linenum += 1
        yield Token(TokenType.NON_C_LINE, "", self.linenum - 1)

    def _handle_dollar_line(self, stripped):
        """Handle $ single-line C pass-through."""
        rest = stripped[1:]
        if self.outcfp:
            self.outcfp.write(rest)
        self.linenum += 1
        yield Token(TokenType.NON_C_LINE, "", self.linenum - 1)

    def _handle_hash_line(self, stripped):
        """Handle # C declaration line — tokenise."""
        body = stripped[1:].rstrip('\r\n')
        yield from self._tokenize_c_line(body, self.linenum)
        self.linenum += 1

    # ------------------------------------------------------------------
    # internal line-by-line driver
    # ------------------------------------------------------------------

    def _lex_stream(self):
        """Process all lines from self._current_fp, yielding tokens."""
        in_block_c = False

        while True:
            raw_line = self._current_fp.readline()
            if raw_line == "":
                # End of current file
                if self._file_stack:
                    self._current_fp.close()
                    self._current_fp, self.linenum, self.current_ifname = self._file_stack.pop()
                    continue
                else:
                    return       # real EOF

            # Strip the trailing newline for processing but track it
            line = raw_line

            # --- block C mode ($[ ... $]) ---
            if in_block_c:
                in_block_c = self._handle_block_c(line)
                continue

            # Determine line prefix — compute leading whitespace
            stripped = line.lstrip(' \t')
            leading_ws = line[:len(line) - len(stripped)]

            # In the original Flex lexer, leading [ \t] in INITIAL state is
            # always written to outfp regardless of what prefix follows.
            # We replicate this for all prefix types except pure text lines
            # (which include their own leading whitespace in the full line).
            if leading_ws and self.outfp and (
                    stripped.startswith("$") or
                    stripped.startswith("#") or
                    stripped.startswith("@") or
                    stripped.startswith("//")):
                self.outfp.write(leading_ws)

            # $[ block start
            if re.match(r'^\$\[[ \t\r]*\n?$', stripped):
                in_block_c = True
                self.linenum += 1
                continue

            if stripped.startswith("//"):
                yield from self._handle_comment()
                continue

            if stripped.startswith("@function"):
                yield from self._handle_function(stripped)
                continue

            if stripped.startswith("@include"):
                self._handle_include(stripped)
                continue

            if stripped.startswith("@"):
                yield from self._handle_redirect(stripped)
                continue

            if stripped.startswith("$") and not stripped.startswith("$["):
                yield from self._handle_dollar_line(stripped)
                continue

            if stripped.startswith("#"):
                yield from self._handle_hash_line(stripped)
                continue

            # Text line — copy to MATLAB output
            if self.outfp:
                self.outfp.write(line)
            self.linenum += 1
            yield Token(TokenType.NON_C_LINE, "", self.linenum - 1)

    # ------------------------------------------------------------------
    # tokenise a single '#' line body
    # ------------------------------------------------------------------

    def _tokenize_c_line(self, body, line):
        """Yield tokens for the body of a '#' line."""
        for m in _TOKEN_RE.finditer(body):
            comment, string, ident, number, punct = m.groups()
            if comment:
                break        # rest of line is a comment
            if string:
                yield Token(TokenType.STRING, string, line)
            elif ident:
                tt = KEYWORDS.get(ident, TokenType.ID)
                yield Token(tt, ident, line)
            elif number:
                yield Token(TokenType.NUMBER, number, line)
            elif punct:
                yield Token(TokenType.PUNCT, punct, line)
