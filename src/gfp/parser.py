import io
import os
import re
import sys
from dataclasses import dataclass
from functools import cache
from typing import Callable, Self

from line_profiler.explicit_profiler import profile

from gfp.stream import Stream


# @dataclass(init=False, eq=False)
class GeneratedTextFileParser:
    def __init__(self, text_stream: io.TextIOBase, parent: Self = None, encoding: str = None):
        # super().__init__()
        self._io = Stream(text_stream)
        self.parent: Self = parent
        if encoding is not None:
            self.encoding = encoding
        elif parent is not None:
            self.encoding = parent.encoding
        else:
            self.encoding = 'utf-8'
        # self._expression_cache = {}

    @cache
    def _compiled_expression(self, txt: bytes):
    # def _compiled_expression(self, txt: str):
        # txt = f'(?<!{txt}){txt}'  # this was an attempt to fix a bug - but we often have non fixed length delimiters so this does not work
        if not txt.endswith(br'\Z'):
            txt += br'\Z'
        return re.compile(txt)

    def read_till_any_delimiter(self, delimiters: list[str]) -> tuple[str, str]:
        pass

    def _parse_fixed_contents(self, fixed_contents: str) -> str:
        fixed_contents = fixed_contents.encode(self.encoding)
        parsed_contents = self._io.read(len(fixed_contents))
        assert parsed_contents == fixed_contents
        return parsed_contents

    @profile
    def _parse_delimited_string(self, delimiter: str, delimiter_repeating: bool, consume: bool) -> str:
        delimiter = delimiter.encode(self.encoding)
        exp = self._compiled_expression(delimiter)
        delimiter_found = False
        delimiter_ended = False
        result = buffer = b''
        last = last_non_delimiter = pos = self._io.tell()
        delimiter_start_pos = sys.maxsize
        while (not delimiter_found) or (not delimiter_ended):
            last = pos
            try:
                char = self._io.read(1)
                pos += 1
                buffer = buffer + char
                # TODO the current creation of the regex still returns a match for double delimiters
                #  e.g. \n\n is still a match even if \n is a delimiter
                match = re.search(exp, buffer)
                if match:

                    delimiter_length = len(match.group(0))
                    delimiter_start_pos = min(delimiter_start_pos, pos - delimiter_length)
                    if delimiter_length > 1 and not delimiter_found:
                        # this applies only to the first hit of the delimiter
                        result = result[:1 - delimiter_length]
                    delimiter_found = True
                    # last_non_delimiter = pos - len(match.group(0))
                    if not delimiter_repeating:
                        last = pos
                        break
                if delimiter_found and not match:
                    delimiter_ended = True
                elif not delimiter_found:
                    result = buffer
                    # last_non_delimiter = last
            except EOFError as e:
                if not delimiter_found:
                    raise e
                delimiter_ended = True
        # self._io.seek(-1, os.SEEK_CUR)
        if not consume:
            # last = last_non_delimiter
            last = delimiter_start_pos
        self._io.seek(last)
        return result.decode(self.encoding)

    def as_dict(self):
        ignored_keys = {'parent', 'encoding'}
        def _as_dict(x):
            if isinstance(x, GeneratedTextFileParser):
                return x.as_dict()
            if isinstance(x, list):
                return [_as_dict(y) for y in x]
            return x
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_') and key not in ignored_keys:
                result[key] = _as_dict(value)
        return result

    # def _parse_till_eos(self, single_step: Callable):
    #     reached_eos = False
    #     result = []
    #     while not reached_eos:
    #         char = self._io.read(1)
    #         if char == '':
    #             reached_eos = True
    #         else:
    #             result.append(single_step())
    #     return result