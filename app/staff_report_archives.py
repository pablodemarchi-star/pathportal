"""Expand report ZIP uploads into bounded, streamed individual files."""
import mimetypes
import shutil
import tempfile
import zipfile
import zlib
from pathlib import PurePosixPath
from werkzeug.datastructures import FileStorage

MAX_FILES = 1000
MAX_BYTES = 10 * 1024**3
MAX_DEPTH = 3


class MediaArchiveError(ValueError):
    pass


class SeekableStream:
    """Python 3.9's SpooledTemporaryFile omits seekable(), required by ZipFile."""
    def __init__(self, stream):
        self.stream = stream

    def seekable(self):
        return True

    def __getattr__(self, name):
        return getattr(self.stream, name)


def individual_media_files(upload, budget=None, depth=0):
    budget = budget if budget is not None else {'files': 0, 'bytes': 0}
    stream = upload.stream
    try:
        is_zip = zipfile.is_zipfile(stream)
        stream.seek(0)
        if not is_zip and not (upload.filename or '').lower().endswith('.zip'):
            header = stream.read(1024)
            stream.seek(0)
            if (upload.mimetype == 'application/pdf'
                    or (upload.filename or '').lower().endswith('.pdf')
                    or b'%PDF-' in header):
                raise MediaArchiveError('A PDF cannot be used as session photos or videos. Select the original photos and videos using the file picker. If needed, download them to your device first.')
            budget['files'] += 1
            if budget['files'] > MAX_FILES:
                raise MediaArchiveError('This ZIP contains too many files. Upload smaller groups of files.')
            yield upload
            return
        if depth >= MAX_DEPTH:
            raise MediaArchiveError('This ZIP contains too many nested archives. Upload the photos and videos directly.')
        count = budget['files']
        with zipfile.ZipFile(SeekableStream(stream)) as archive:
            for entry in archive.infolist():
                path = PurePosixPath(entry.filename.replace('\\', '/'))
                if entry.is_dir() or any(part.startswith('.') or part == '__MACOSX' for part in path.parts):
                    continue
                if entry.flag_bits & 1:
                    raise MediaArchiveError('Password-protected ZIP files are not supported. Upload the photos and videos directly.')
                if entry.file_size == 0:
                    continue
                budget['bytes'] += entry.file_size
                if budget['bytes'] > MAX_BYTES:
                    raise MediaArchiveError('This ZIP expands to too much data. Upload smaller groups of files.')
                if budget['files'] >= MAX_FILES:
                    raise MediaArchiveError('This ZIP contains too many files. Upload smaller groups of files.')
                with archive.open(entry) as source, tempfile.SpooledTemporaryFile(max_size=8*1024**2) as extracted:
                    shutil.copyfileobj(source, extracted, length=1024**2)
                    extracted.seek(0)
                    file = FileStorage(stream=extracted, filename=path.name,
                                       content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                    yield from individual_media_files(file, budget, depth+1)
        if budget['files'] == count:
            raise MediaArchiveError('This ZIP contains no files to upload. Select your photos and videos.')
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error) as error:
        raise MediaArchiveError('The ZIP could not be opened. Upload the photos and videos directly or select a valid ZIP.') from error
