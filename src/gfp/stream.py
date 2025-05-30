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
