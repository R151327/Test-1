"""
Classes representing uploaded files.
"""

import errno
import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import File
from django.core.files import temp as tempfile
from django.utils.encoding import force_str

__all__ = ('UploadedFile', 'TemporaryUploadedFile', 'InMemoryUploadedFile',
           'SimpleUploadedFile')


class UploadedFile(File):
    """
    A abstract uploaded file (``TemporaryUploadedFile`` and
    ``InMemoryUploadedFile`` are the built-in concrete subclasses).

    An ``UploadedFile`` object behaves somewhat like a file object and
    represents some file data that the user submitted with a form.
    """
    DEFAULT_CHUNK_SIZE = 64 * 2 ** 10

    def __init__(self, file=None, name=None, content_type=None, size=None, charset=None, content_type_extra=None):
        super(UploadedFile, self).__init__(file, name)
        self.size = size
        self.content_type = content_type
        self.charset = charset
        self.content_type_extra = content_type_extra

    def __repr__(self):
        return force_str("<%s: %s (%s)>" % (
            self.__class__.__name__, self.name, self.content_type))

    def _get_name(self):
        return self._name

    def _set_name(self, name):
        # Sanitize the file name so that it can't be dangerous.
        if name is not None:
            # Just use the basename of the file -- anything else is dangerous.
            name = os.path.basename(name)

            # File names longer than 255 characters can cause problems on older OSes.
            if len(name) > 255:
                name, ext = os.path.splitext(name)
                ext = ext[:255]
                name = name[:255 - len(ext)] + ext

        self._name = name

    name = property(_get_name, _set_name)


class TemporaryUploadedFile(UploadedFile):
    """
    A file uploaded to a temporary location (i.e. stream-to-disk).
    """
    def __init__(self, name, content_type, size, charset, content_type_extra):
        if settings.FILE_UPLOAD_TEMP_DIR:
            file = tempfile.NamedTemporaryFile(suffix='.upload',
                dir=settings.FILE_UPLOAD_TEMP_DIR)
        else:
            file = tempfile.NamedTemporaryFile(suffix='.upload')
        super(TemporaryUploadedFile, self).__init__(file, name, content_type, size, charset, content_type_extra)

    def temporary_file_path(self):
        """
        Returns the full path of this file.
        """
        return self.file.name

    def close(self):
        try:
            return self.file.close()
        except OSError as e:
            if e.errno != errno.ENOENT:
                # Means the file was moved or deleted before the tempfile
                # could unlink it.  Still sets self.file.close_called and
                # calls self.file.file.close() before the exception
                raise


class InMemoryUploadedFile(UploadedFile):
    """
    A file uploaded into memory (i.e. stream-to-memory).
    """
    def __init__(self, file, field_name, name, content_type, size, charset, content_type_extra):
        super(InMemoryUploadedFile, self).__init__(file, name, content_type, size, charset, content_type_extra)
        self.field_name = field_name

    def open(self, mode=None):
        self.file.seek(0)

    def close(self):
        pass

    def chunks(self, chunk_size=None):
        self.file.seek(0)
        yield self.read()

    def multiple_chunks(self, chunk_size=None):
        # Since it's in memory, we'll never have multiple chunks.
        return False


class SimpleUploadedFile(InMemoryUploadedFile):
    """
    A simple representation of a file, which just has content, size, and a name.
    """
    def __init__(self, name, content, content_type='text/plain'):
        content = content or b''
        super(SimpleUploadedFile, self).__init__(BytesIO(content), None, name,
                                                 content_type, len(content), None, None)

    @classmethod
    def from_dict(cls, file_dict):
        """
        Creates a SimpleUploadedFile object from
        a dictionary object with the following keys:
           - filename
           - content-type
           - content
        """
        return cls(file_dict['filename'],
                   file_dict['content'],
                   file_dict.get('content-type', 'text/plain'))
