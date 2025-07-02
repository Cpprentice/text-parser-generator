import collections
import io
import os
import re
import sys
from dataclasses import dataclass
from functools import cache
from typing import Callable, Self, Any

from line_profiler.explicit_profiler import profile

import gfp.cast
from gfp.stream import Stream, SlicedStream


def re_search(exp, buffer):
    re_search.history[exp].append(len(buffer))
    return re.search(exp, buffer)

re_search.history = collections.defaultdict(list)


def is_in_slice(a_slice: slice, idx: int):
    # This function is not intended to work with negative slice start/stop and index values
    step = a_slice.step if a_slice.step else 1
    if a_slice.start is None and a_slice.stop is None:
        return (idx % step) == 0
    elif a_slice.start is None:
        if idx >= a_slice.stop:
            return False
        return (idx % step) == 0
    elif a_slice.stop is None:
        if idx < a_slice.start:
            return False
        return (idx - a_slice.start) % step == 0
    else:
        if idx < a_slice.start or idx >= a_slice.stop:
            return False

        return (idx - a_slice.start) % step == 0


# Created with the help of ChatGPT
class ByteQueue:
    def __init__(
            self,
            source: io.BufferedReader,
            buffer_size: int = 4096,
            read_chunk_size: int = 4096,
            source_slice: slice = None
    ):
        self._buffer = bytearray(buffer_size)
        self._start = 0
        self._end = 0
        self._source = source
        if source_slice is not None:
            if source_slice.start is None:
                # For later calculations we need the slice start to be an int
                self._source_slice = slice(0, source_slice.stop, source_slice.step)
            else:
                self._source_slice = source_slice
        else:
            self._source_slice = slice(0, None)
        self._source_pos = self._source_slice.start
        self._read_chunk_size = read_chunk_size

    def __repr__(self):
        slice_string = ''
        if self._source_slice not in {slice(0, None), slice(0, None, 1)}:
            slice_string = f'[{self._source_slice.start}:{self._source_slice.stop}]'
        return f'ByteQueue({len(self)}, {len(self._buffer)}){slice_string}'

    def __len__(self) -> int:
        return self._end - self._start

    def _compact(self):
        """Move remaining data to the front of the buffer."""
        if self._start > 0:
            self._buffer[:self._end - self._start] = self._buffer[self._start:self._end]
            self._end -= self._start
            self._start = 0

    @property
    def _buffer_mv(self) -> memoryview:
        return memoryview(self._buffer)[self._start:self._end]

    @property
    def _buffer_text(self) -> str:
        return bytes(self._buffer_mv).decode('cp1252')

    def _ensure_capacity(self, additional_space: int):
        """Ensure there's enough space for `additional_space` more bytes."""
        available = len(self._buffer) - self._end
        if available >= additional_space:
            return
        self._compact()
        available = len(self._buffer) - self._end
        if available < additional_space:
            new_size = max(len(self._buffer) * 2, self._end + additional_space)
            new_buffer = bytearray(new_size)
            new_buffer[:self._end - self._start] = self._buffer[self._start:self._end]
            self._buffer = new_buffer
            self._end -= self._start
            self._start = 0

    def _fill_from_stream(self) -> int:
        """Read a fixed chunk of data from the stream into the buffer."""

        # Make sure we are at the right location of the source stream
        self._source.seek(self._source_pos, io.SEEK_SET)

        # Check if the size of our stream is sliced
        remaining_stream_size = self._source_slice.stop - self._source_pos \
            if self._source_slice.stop is not None \
            else None
        local_read_chunk_size = self._read_chunk_size \
            if remaining_stream_size is None \
            else min(remaining_stream_size, self._read_chunk_size)

        self._ensure_capacity(local_read_chunk_size)

        mv = memoryview(self._buffer)
        n = self._source.readinto(mv[self._end:self._end + local_read_chunk_size])
        self._end += n
        self._source_pos += n
        return n  # n will be 0 at EOF

    def read(self, size: int) -> bytes:
        if size > len(self):
            self._fill_from_stream()
        if size > len(self):
            # reached EOF
            raise EOFError('End of base stream reached before requested bytes could be read')
        size = min(size, len(self))
        data = self._buffer[self._start:self._start + size]
        self._start += size
        return bytes(data)

    def _read_until_raw(self, delimiter: re.Pattern, consume: bool, delimiter_repeating: bool) -> re.Match:
        """

        :param delimiter:
        :param consume:
        :param delimiter_repeating:
        :return:
        """
        while True:
            match = re_search(delimiter, self._buffer_mv)
            if match:
                if delimiter_repeating:
                    # check from new position if delimiter continues
                    # we need to load some more to catch all remaining bytes of
                    #  the delimiter if the delimiter continues till the end
                    if match.end(0) != len(self):
                        break
                else:
                    break
            bytes_filled = self._fill_from_stream()
            if bytes_filled == 0 and not delimiter_repeating:
                raise EOFError("Can't find delimiter until end of stream")
            if bytes_filled == 0 and delimiter_repeating:
                if not match:
                    raise EOFError("Can't find delimiter until end of stream")
                break
        return match

    def _finalize_raw_read(self, match: re.Match, consume: bool) -> bytes:
        data = self._buffer[self._start:self._start + match.start(0)]
        old_start = self._start
        self._start = old_start + match.start(0)  # advance till start of delimiter
        if consume:
            self._start = old_start + match.end(0)

        return bytes(data)

    def read_until(self, delimiter: re.Pattern, consume: bool, delimiter_repeating: bool) -> bytes:
        match = self._read_until_raw(delimiter, consume, delimiter_repeating)
        return self._finalize_raw_read(match, consume)

    def create_sub_queue(
            self,
            delimiter: re.Pattern,
            consume: bool,
            delimiter_repeating: bool,
            repeat_mode: str
    ) -> Self:
        match = None
        try:
            match = self._read_until_raw(delimiter, consume, delimiter_repeating)
            end = match.start(0)
            if consume:
                end = match.end(0)
            new_start = self._source_pos - len(self)
        except EOFError as ex:
            if repeat_mode == 'eos':
                if len(self) == 0:
                    raise ex
                new_start = self._source_pos - len(self)
                self._start = self._end  # advance till the end of the stream so the next iteration returns len 0
                end = None
            else:
                raise ex

        if end is None:
            new_end = None
        else:
            new_end = new_start + end
        new_byte_queue = ByteQueue(
            self._source,
            source_slice=slice(new_start, new_end)
        )
        if match is not None:
            self._finalize_raw_read(match, consume)
        return new_byte_queue

    # def peek(self, size: int) -> bytes:
    #     size = min(size, len(self))
    #     return bytes(self._buffer[self._start:self._start + size])
    #
    # def clear(self) -> None:
    #     self._start = 0
    #     self._end = 0
    #
    # def extend(self, data: bytes):
    #     self._ensure_capacity(len(data))
    #     self._buffer[self._end:self._end + len(data)] = data
    #     self._end += len(data)


class LookupMixin:
    @staticmethod
    def _create_cast_lookup(items) -> dict[str, Any]:
        if 'default' in items:
            lookup = collections.defaultdict(lambda: getattr(gfp.cast, f"_{items['default']}"))
        else:
            lookup = {}
        for key, value in items.items():
            if key != 'default':
                lookup[key] = getattr(gfp.cast, f'{value}_')
        return lookup

    def _create_type_lookup(self, items) -> dict[str, Any]:
        if 'default' in items:
            default_type = items['default']
            lookup = collections.defaultdict(lambda: getattr(self.__class__, default_type))
        else:
            lookup = {}
        for key, value in items.items():
            if key != 'default':
                lookup[key] = getattr(self.__class__, value)
        return lookup


class RegularExpressionCacheMixin:
    @cache
    def _compiled_expression(self, pattern: bytes) -> re.Pattern[bytes]:
        return re.compile(pattern)


class AsDictMixin:
    def as_dict(self):
        ignored_keys = {'parent', 'encoding'}
        def _as_dict(x):
            if isinstance(x, AsDictMixin):
                return x.as_dict()
            if isinstance(x, list):
                return [_as_dict(y) for y in x]
            return x
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_') and key not in ignored_keys:
                result[key] = _as_dict(value)
        return result


class UpdatedGeneratedTextFileParser(LookupMixin, RegularExpressionCacheMixin, AsDictMixin):
    def __init__(self, base_stream: io.BufferedReader | ByteQueue, parent: Self = None, encoding: str = None):
        if isinstance(base_stream, ByteQueue):
            self._io = base_stream
        else:
            self._io = ByteQueue(base_stream)
        self._parent = parent
        if encoding is not None:
            self._encoding = encoding
        elif parent is not None:
            self._encoding = parent._encoding
        else:
            self._encoding = 'utf-8'
        self._last_delimiter: str | None = None

    def _parse_delimited_string(
            self,
            delimiter: str,
            delimiter_repeating: bool,
            consume: bool
    ):
        delimiter = delimiter.encode(self._encoding)
        exp = self._compiled_expression(delimiter)
        data_bytes = self._io.read_until(exp, consume, delimiter_repeating)
        return data_bytes.decode(self._encoding)

    def _parse_fixed_contents(self, fixed_contents: str) -> str:
        fixed_contents = fixed_contents.encode(self._encoding)
        parsed_contents = self._io.read(len(fixed_contents))
        assert parsed_contents == fixed_contents
        return parsed_contents.decode(self._encoding)

    def _create_substream(self, delimiter: str, delimiter_repeating: bool, consume: bool, repeat_mode: str) -> ByteQueue:
        delimiter = delimiter.encode(self._encoding)
        exp = self._compiled_expression(delimiter)
        return self._io.create_sub_queue(exp, consume, delimiter_repeating, repeat_mode)
        # start = self._io._source.tell()
        # try:
        #     _ = self._parse_delimited_string(delimiter, delimiter_repeating, consume)
        # except EOFError as ex:
        #     if repeat_mode == 'eos':
        #         pos = self._io._source.tell()
        #         if pos == start:
        #             raise ex
        #         return SlicedStream(self._io._source, slice(start, None))
        #     else:
        #         raise ex
        # end = self._io._source.tell()
        # return SlicedStream(self._io._source, slice(start, end))


# @dataclass(init=False, eq=False)
class GeneratedTextFileParser(LookupMixin, RegularExpressionCacheMixin, AsDictMixin):
    def __init__(self, text_stream: io.TextIOBase, parent: Self = None, encoding: str = None):
        # super().__init__()
        if not isinstance(text_stream, (Stream, SlicedStream)):
            self._io = Stream(text_stream)
        else:
            self._io = text_stream
        self.parent: Self = parent
        if encoding is not None:
            self.encoding = encoding
        elif parent is not None:
            self.encoding = parent.encoding
        else:
            self.encoding = 'utf-8'
        self.last_delimiter: str | None = None
        # self._expression_cache = {}

    # @cache
    # def _compiled_expression(self, txt: bytes):
    # # def _compiled_expression(self, txt: str):
    #     # txt = f'(?<!{txt}){txt}'  # this was an attempt to fix a bug - but we often have non fixed length delimiters so this does not work
    #     if not txt.endswith(br'\Z'):
    #         txt += br'\Z'
    #     return re.compile(txt)

    # def read_till_any_delimiter(self, delimiters: list[str]) -> tuple[str, str]:
    #     pass

    # @staticmethod
    # def _create_cast_lookup(items) -> dict[str, Any]:
    #     if 'default' in items:
    #         lookup = collections.defaultdict(lambda: getattr(gfp.cast, f"_{items['default']}"))
    #     else:
    #         lookup = {}
    #     for key, value in items.items():
    #         if key != 'default':
    #             lookup[key] = getattr(gfp.cast, f'{value}_')
    #     return lookup
    #
    # def _create_type_lookup(self, items) -> dict[str, Any]:
    #     if 'default' in items:
    #         default_type = items['default']
    #         lookup = collections.defaultdict(lambda: getattr(self.__class__, default_type))
    #     else:
    #         lookup = {}
    #     for key, value in items.items():
    #         if key != 'default':
    #             lookup[key] = getattr(self.__class__, value)
    #     return lookup

    def _parse_fixed_contents(self, fixed_contents: str) -> str:
        fixed_contents = fixed_contents.encode(self.encoding)
        parsed_contents = self._io.read(len(fixed_contents))
        assert parsed_contents == fixed_contents
        return parsed_contents

    def _create_substream(self, delimiter: str, delimiter_repeating: bool, consume: bool, repeat_mode: str) -> SlicedStream:
        start = self._io._base.tell()
        try:
            _ = self._parse_delimited_string(delimiter, delimiter_repeating, consume)
        except EOFError as ex:
            if repeat_mode == 'eos':
                pos = self._io._base.tell()
                if pos == start:
                    raise ex
                return SlicedStream(self._io._base, slice(start, None))
            else:
                raise ex
        end = self._io._base.tell()
        return SlicedStream(self._io._base, slice(start, end))

    def _parse_delimited_string_buffered(
            self,
            delimiter: str,
            delimiter_repeating: bool,
            consume: bool
    ):
        delimiter = delimiter.encode(self.encoding)
        exp = self._compiled_expression(delimiter)
        delimiter_found = False
        delimiter_ended = False
        result = buffer = b''
        last = pos = self._io.tell()
        delimiter_start_pos = sys.maxsize
        while (not delimiter_found) or (not delimiter_ended):
            last = pos
            try:
                chars = self._io.read(1024)  # TODO split the methods to have "read" and "read_raises" to distinguish if the end of stream is raised or the stream is truncated.
                # TODO the parsing buffer of e.g. 1024 bytes should be shared between multiple calls to this function - so as long as we still call it on the same object it should
                #  not require parsing the same bytes again - making it mandatory to keep track of position in the base stream and the buffer.
                #  Maybe an additional class for the stream buffer might help?
            except Exception:
                pass


    @profile
    def _parse_delimited_string(
            self,
            delimiter: str,
            delimiter_repeating: bool,
            consume: bool,
            # optional_delimiter: str | None = None
    ) -> str:
        delimiter = delimiter.encode(self.encoding)
        exp = self._compiled_expression(delimiter)
        # if optional_delimiter is not None:
        #     optional_delimiter = optional_delimiter.encode(self.encoding)
        delimiter_found = False
        delimiter_ended = False
        result = buffer = b''
        last = start = pos = self._io.tell()
        delimiter_start_pos = sys.maxsize
        while (not delimiter_found) or (not delimiter_ended):
            last = pos
            try:
                char = self._io.read(1)
                pos += 1
                buffer = buffer + char
                # TODO the current creation of the regex still returns a match for double delimiters
                #  e.g. \n\n is still a match even if \n is a delimiter
                match = re_search(exp, buffer)
                if match:
                    # if optional_delimiter is not None and match.group(0) == optional_delimiter:
                    #     self._io.seek(start)
                    #     return ''
                    self.last_delimiter = match.group(0).decode(self.encoding)

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

    # def as_dict(self):
    #     ignored_keys = {'parent', 'encoding'}
    #     def _as_dict(x):
    #         if isinstance(x, GeneratedTextFileParser):
    #             return x.as_dict()
    #         if isinstance(x, list):
    #             return [_as_dict(y) for y in x]
    #         return x
    #     result = {}
    #     for key, value in self.__dict__.items():
    #         if not key.startswith('_') and key not in ignored_keys:
    #             result[key] = _as_dict(value)
    #     return result

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