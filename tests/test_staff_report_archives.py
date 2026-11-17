import io
import unittest
import zipfile
from unittest.mock import patch
from werkzeug.datastructures import FileStorage
from app.staff_report_archives import individual_media_files, MediaArchiveError


def archive(entries):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as zipped:
        for name,content in entries: zipped.writestr(name,content)
    data.seek(0)
    return data


class ReportArchiveTest(unittest.TestCase):
    def unpack(self,upload):
        return [(file.filename,file.mimetype,file.read()) for file in individual_media_files(upload)]

    def test_zip_contents_are_individual_files_without_platform_metadata(self):
        source=archive([('Fotos/Fotografía 1.jpg',b'original photo'),('Videos/Video 1.mp4',b'original video'),
            ('__MACOSX/Fotos/._photo.jpg',b'finder metadata'),('.DS_Store',b'metadata')])
        result=self.unpack(FileStorage(stream=source,filename='session.zip'))
        self.assertEqual(result,[('Fotografía 1.jpg','image/jpeg',b'original photo'),('Video 1.mp4','video/mp4',b'original video')])

    def test_raw_files_remain_unchanged_and_disguised_zips_are_unpacked(self):
        file=FileStorage(stream=io.BytesIO(b'photo'),filename='Foto 1.jpg',content_type='image/jpeg')
        self.assertEqual(self.unpack(file),[('Foto 1.jpg','image/jpeg',b'photo')])
        file=FileStorage(stream=archive([('photo.jpg',b'image')]),filename='export.dat')
        self.assertEqual(self.unpack(file)[0][0],'photo.jpg')

    def test_nested_zips_are_flattened_and_never_uploaded_as_archives(self):
        inner=archive([('photo.jpg',b'image')]).getvalue()
        result=self.unpack(FileStorage(stream=archive([('nested.zip',inner)]),filename='outer.zip'))
        self.assertEqual(result,[('photo.jpg','image/jpeg',b'image')])

    def test_invalid_empty_and_oversized_archives_are_rejected(self):
        for source in [io.BytesIO(b'not a zip'),archive([]),archive([('.DS_Store',b'metadata')])]:
            with self.assertRaises(MediaArchiveError):self.unpack(FileStorage(stream=source,filename='upload.zip'))
        with patch('app.staff_report_archives.MAX_BYTES',2):
            with self.assertRaises(MediaArchiveError):self.unpack(FileStorage(stream=archive([('photo.jpg',b'image')]),filename='upload.zip'))
        with patch('app.staff_report_archives.MAX_FILES',1):
            with self.assertRaises(MediaArchiveError):self.unpack(FileStorage(stream=archive([('one.jpg',b'1'),('two.jpg',b'2')]),filename='upload.zip'))
