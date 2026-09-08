"""AMG main tests."""

import dbm
import dbm.dumb
import dbm.sqlite3
import inspect
import itertools
import random
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import platformdirs

import amg


class TestAmg(unittest.TestCase):
    """AMG main test suite."""

    def setUp(self) -> None:
        """Set up test case stuff."""
        self.maxDiff = None

    def test_get_reviews(self) -> None:
        """Test review fetching."""
        count = random.randint(10, 50)
        gen = amg.get_reviews()
        self.assertTrue(inspect.isgenerator(gen))
        reviews = list(itertools.islice(gen, count))
        self.assertEqual(len(reviews), count)
        for review in reviews:
            self.assertIsInstance(review, amg.ReviewMetadata)
            self.assertTrue(review.url.startswith(amg.ROOT_URL))
            self.assertIsInstance(review.artist, str)
            self.assertTrue(review.artist)
            self.assertIsInstance(review.album, str)
            self.assertTrue(review.album)
            self.assertTrue(review.cover_thumbnail_url.startswith("http"))
            self.assertTrue((review.cover_url is None) or review.cover_url.startswith("http"))
            self.assertIsInstance(review.tags, tuple)
            self.assertTrue(review.tags)
            for tag in review.tags:
                self.assertIsInstance(tag, str)

    def test_known_reviews_backend(self) -> None:
        """Test played review storage uses SQLite whatever the interpreter's default dbm backend."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                unittest.mock.patch.object(platformdirs, "user_data_dir", return_value=tmp_dir),
                unittest.mock.patch.object(dbm, "_defaultmod", dbm.dumb),
            ):
                known_reviews = amg.KnownReviews()
            known_reviews.data.close()
            self.assertEqual(dbm.whichdb(Path(tmp_dir) / "played.dat"), dbm.sqlite3.__name__)

    def test_get_embedded_track(self) -> None:
        """Test embedded track URL extraction."""
        http_cache = amg.web_cache.WebCache(":memory:", "reviews", caching_strategy=amg.web_cache.CachingStrategy.FIFO)
        urls = {
            "https://www.angrymetalguy.com/vredehammer-violator-review/": (
                ("https://www.youtube.com/watch?v=9Z34GAEO8hU",),
                False,
            ),
            "https://www.angrymetalguy.com/cadaveric-fumes-dimensions-obscure-review/": (
                (
                    "https://bloodharvestrecords.bandcamp.com/track/crepuscular-journey",
                    "https://bloodharvestrecords.bandcamp.com/track/extatic-extirpation",
                    "https://bloodharvestrecords.bandcamp.com/track/where-darkness-reigns-pristine",
                    "https://bloodharvestrecords.bandcamp.com/track/swallowed-into-eternity",
                ),
                True,
            ),
            "https://www.angrymetalguy.com/sinnery-feast-fools-review/": (
                ("https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/257383834",),
                True,
            ),
            "https://www.angrymetalguy.com/hornss-telepath-review/": (
                (
                    "https://hornss.bandcamp.com/track/st-geneive",
                    "https://hornss.bandcamp.com/track/atrophic",
                    "https://hornss.bandcamp.com/track/manzanita",
                    "https://hornss.bandcamp.com/track/in-fields-of-lyme",
                    "https://hornss.bandcamp.com/track/sargasso-heart",
                    "https://hornss.bandcamp.com/track/prince-of-a-thousand-enemies",
                    "https://hornss.bandcamp.com/track/the-black-albatross",
                    "https://hornss.bandcamp.com/track/leaving-thermal",
                    "https://hornss.bandcamp.com/track/the-airtight-garage",
                    "https://hornss.bandcamp.com/track/old-ghosts",
                    "https://hornss.bandcamp.com/track/galatic-derelict",
                ),
                True,
            ),
            # "https://www.angrymetalguy.com/auditory-armory-dark-matter-review/":
            # (("https://www.reverbnation.com/open_graph/song/28202104?pwc%5Bbranded%5D=1",),
            #  True),
            "https://www.angrymetalguy.com/gorod-aethra-review/": (
                ("https://www.youtube.com/watch?v=WBU1H-9yvmQ",),
                False,
            ),
        }
        for review_url, (expected_track_url, expected_audio_only) in urls.items():
            review_page = amg.fetch_page(review_url)
            track_url, audio_only = amg.get_embedded_track(review_page, http_cache)
            self.assertEqual(track_url, expected_track_url)
            self.assertEqual(audio_only, expected_audio_only)
