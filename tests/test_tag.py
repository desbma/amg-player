"""Tag related unit tests."""

import base64
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse

import mutagen

import amg


def download(url, filepath):
    """Download a file."""
    cache_dir = os.getenv("TEST_DL_CACHE_DIR")
    if cache_dir is not None:
        os.makedirs(cache_dir, exist_ok=True)
        cache_filepath = os.path.join(cache_dir, os.path.basename(urllib.parse.urlsplit(url).path))
        if os.path.isfile(cache_filepath):
            shutil.copyfile(cache_filepath, filepath)
            return
    data = amg.fetch_ressource(url)
    with open(filepath, "wb") as f:
        f.write(data)
    if cache_dir is not None:
        shutil.copyfile(filepath, cache_filepath)


class TestTag(unittest.TestCase):
    """Tag related test suite."""

    @classmethod
    def setUpClass(cls):
        """Set up test suite stuff."""
        cls.ref_temp_dir = tempfile.TemporaryDirectory()
        vorbis_filepath = os.path.join(cls.ref_temp_dir.name, "f.ogg")
        download("https://upload.wikimedia.org/wikipedia/en/0/09/Opeth_-_Deliverance.ogg", vorbis_filepath)
        opus_filepath = os.path.join(cls.ref_temp_dir.name, "f.opus")
        download("https://www.dropbox.com/s/xlp1goezxovlgl4/ehren-paper_lights-64.opus?dl=1", opus_filepath)
        mp3_filepath = os.path.join(cls.ref_temp_dir.name, "f.mp3")
        download("https://www.dropbox.com/s/mtac0y8azs5hqxo/Shuffle%2520for%2520K.M.mp3?dl=1", mp3_filepath)
        m4a_filepath = os.path.join(cls.ref_temp_dir.name, "f.m4a")
        download("https://auphonic.com/media/audio-examples/01.auphonic-demo-unprocessed.m4a", m4a_filepath)

    @classmethod
    def tearDownClass(cls):
        """Clean up test suite stuff."""
        cls.ref_temp_dir.cleanup()

    def setUp(self):
        """Set up test case stuff."""
        self.temp_dir = tempfile.TemporaryDirectory()
        for src_filename in os.listdir(__class__.ref_temp_dir.name):
            shutil.copy(os.path.join(__class__.ref_temp_dir.name, src_filename), self.temp_dir.name)
        self.vorbis_filepath = os.path.join(self.temp_dir.name, "f.ogg")
        self.opus_filepath = os.path.join(self.temp_dir.name, "f.opus")
        self.mp3_filepath = os.path.join(self.temp_dir.name, "f.mp3")
        mf = mutagen.File(self.mp3_filepath)
        mf.tags.delall("APIC")
        mf.save()
        self.m4a_filepath = os.path.join(self.temp_dir.name, "f.m4a")
        mf = mutagen.File(self.m4a_filepath)
        del mf["covr"]
        mf.save()

    def tearDown(self):
        """Clean up test case stuff."""
        self.temp_dir.cleanup()

    def test_normalize_title_tag(self):
        """Test title tag normalization."""
        json_filepath = os.path.join(os.path.dirname(__file__), "normalize_title_tag.json")
        with open(json_filepath, "rt") as json_file:
            for test_data in json.load(json_file):
                source = test_data["source"]
                artist = test_data["artist"]
                album = test_data["album"]
                record_label = test_data.get("record_label")
                expected_result = test_data["result"]
                with self.subTest(source=source, expected_result=expected_result, artist=artist, album=album):
                    self.assertEqual(amg.tag.normalize_title_tag(source, artist, album, record_label), expected_result)

    def test_tag(self):
        """Test tagging for various formats."""
        artist = "Artist"
        album = "Album"
        # https://github.com/mathiasbynens/small/blob/master/jpeg.jpg
        cover_data = b"\xff\xd8\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc9\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xcc\x00\x06\x00\x10\x10\x05\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9"
        review = amg.ReviewMetadata(None, artist, album, None, None, None)

        # vorbis
        self.assertFalse(amg.tag.has_embedded_album_art(self.vorbis_filepath))
        amg.tag.tag(self.vorbis_filepath, review, {}, cover_data)
        tags = mutagen.File(self.vorbis_filepath)
        ref_tags = {"artist": [artist], "album": [album]}
        for k, v in ref_tags.items():
            self.assertIn(k, tags)
            self.assertEqual(tags[k], v)
        self.assertIn("metadata_block_picture", tags)
        self.assertEqual(len(tags["metadata_block_picture"]), 1)
        self.assertIn(cover_data, base64.b64decode(tags["metadata_block_picture"][0]))
        self.assertTrue(amg.tag.has_embedded_album_art(self.vorbis_filepath))

        # opus
        self.assertFalse(amg.tag.has_embedded_album_art(self.opus_filepath))
        amg.tag.tag(self.opus_filepath, review, {}, cover_data)
        tags = mutagen.File(self.opus_filepath)
        ref_tags = {"artist": [artist], "album": [album]}
        for k, v in ref_tags.items():
            self.assertIn(k, tags)
            self.assertEqual(tags[k], v)
        self.assertIn("metadata_block_picture", tags)
        self.assertEqual(len(tags["metadata_block_picture"]), 1)
        self.assertIn(cover_data, base64.b64decode(tags["metadata_block_picture"][0]))
        self.assertTrue(amg.tag.has_embedded_album_art(self.opus_filepath))

        # mp3
        self.assertFalse(amg.tag.has_embedded_album_art(self.mp3_filepath))
        amg.tag.tag(self.mp3_filepath, review, {}, cover_data)
        tags = mutagen.File(self.mp3_filepath)
        ref_tags = {"TPE1": [artist], "TALB": [album]}
        for k, v in ref_tags.items():
            self.assertIn(k, tags)
            self.assertEqual(tags[k].text, v)
        self.assertIn("APIC:", tags)
        self.assertIn(cover_data, tags["APIC:"].data)
        self.assertTrue(amg.tag.has_embedded_album_art(self.mp3_filepath))

        # mp4
        self.assertFalse(amg.tag.has_embedded_album_art(self.m4a_filepath))
        amg.tag.tag(self.m4a_filepath, review, {}, cover_data)
        tags = mutagen.File(self.m4a_filepath)
        ref_tags = {"\xa9ART": [artist], "\xa9alb": [album]}
        for k, v in ref_tags.items():
            self.assertIn(k, tags)
            self.assertEqual(tags[k], v)
        self.assertIn("covr", tags)
        self.assertEqual(len(tags["covr"]), 1)
        self.assertEqual(bytes(tags["covr"][0]), cover_data)
        self.assertTrue(amg.tag.has_embedded_album_art(self.m4a_filepath))
