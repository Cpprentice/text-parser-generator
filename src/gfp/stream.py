import io


class Stream:
    def __init__(self, text_stream: io.TextIOBase):
        self._base = text_stream

    def __getattr__(self, item):
        return getattr(self._base, item)

    # def seek(self, offset, whence=io.SEEK_SET):
    #     return self._base.seek(offset, whence)
    #
    # def tell(self):
    #     return self._base.tell()
    #
    def read(self, size=-1):
        text = self._base.read(size)
        if text == b'':
            raise EOFError('Reached end of stream')
        return text


def slice_intersect(s1: slice, s2: slice) -> slice:
    # Note this does not work for step != 1
    if s1.start is None and s1.stop is None:
        return s2
    elif s2.start is None and s2.stop is None:
        return s1

    elif s1.start is None and s2.start is None:
        return slice(None, min(s1.stop, s2.stop))
    elif s1.start is None and s2.stop is None:
        if s1.stop > s2.start:
            return slice(s2.start, s1.stop)
        return slice(0, 0)
    elif s1.start is None:
        if s1.stop > s2.start:
            return slice(s2.start, min(s1.stop, s2.stop))
        return slice(0, 0)

    elif s1.stop is None and s2.start is None:
        if s1.start < s2.stop:
            return slice(s1.start, s2.stop)
        return slice(0, 0)
    elif s1.stop is None and s2.stop is None:
        return slice(max(s1.start, s2.start), None)
    elif s1.stop is None:
        if s1.start < s2.stop:
            return slice(max(s1.start, s2.start), s2.stop)
        return slice(0, 0)

    elif s2.start is None:
        if s1.start < s2.stop:
            return slice(s1.start, min(s1.stop, s2.stop))
        return slice(0, 0)
    elif s2.stop is None:
        if s2.start < s1.stop:
            return slice(max(s1.start, s2.start), s1.stop)
        return slice(0, 0)

    elif s2.start < s1.stop and s2.stop > s1.start:
        return slice(max(s1.start, s2.start), min(s1.stop, s2.stop))
    return slice(0, 0)


class SlicedStream:
    def __init__(self, base_stream: io.IOBase, stream_slice: slice):
        self._base = base_stream
        self._stream_slice = stream_slice
        self._rel_pos = 0

    # def __getattr__(self, item):
    #     return getattr(self._base, item)

    def _absolute_pos(self, rel_pos: int) -> int | None:
        if rel_pos is None:
            return None
        return rel_pos + self._stream_slice.start

    def _relative_pos(self, abs_pos: int) -> int:
        return abs_pos - self._stream_slice.start

    @property
    def size(self) -> int | None:
        if self._stream_slice.stop is None:
            return None
        return self._stream_slice.stop - self._stream_slice.start

    def _out_of_stream(self, abs_pos: int) -> bool:
        return abs_pos not in self._stream_slice

    def seek(self, rel_pos: int, whence: int = 0):
        self._rel_pos = rel_pos
        return self._base.seek(self._absolute_pos(rel_pos), whence)
        # TODO this likely does not work for anything else than offset from the stream start

    def tell(self) -> int:
        return self._rel_pos

    def read(self, size=-1):
        rel_target_pos = None if size is None or size < 0 else self._rel_pos + size
        slice_to_be_read = slice(
            self._absolute_pos(self._rel_pos),
            self._absolute_pos(rel_target_pos)
        )
        valid_slice_to_be_read = slice_intersect(self._stream_slice, slice_to_be_read)

        if valid_slice_to_be_read.stop is None:
            new_size = -1
        else:
            new_size = valid_slice_to_be_read.stop - valid_slice_to_be_read.start
        if new_size != 0:
            self._base.seek(self._absolute_pos(self._rel_pos), io.SEEK_SET)
        text = self._base.read(new_size)
        if text == b'':
            raise EOFError('Reached end of stream')
        self._rel_pos += len(text)
        return text
