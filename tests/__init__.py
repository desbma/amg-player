#!/usr/bin/env python3

""" AMG main tests. """

import inspect
import logging
import random
import unittest

import amg


class TestAmg(unittest.TestCase):

    """AMG main test suite."""

    def setUp(self):
        """Set up test case stuff."""
        self.maxDiff = None

    def test_get_reviews(self):
        """Test review fetching."""
        count = random.randint(10, 50)
        gen = amg.get_reviews()
        self.assertTrue(inspect.isgenerator(gen))
        for i, review in zip(range(count), gen):
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
        self.assertEqual(i, count - 1)

    def test_get_embedded_track(self):
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


if __name__ == "__main__":
    # disable logging
    logging.basicConfig(level=logging.CRITICAL + 1)
    # logging.basicConfig(level=logging.DEBUG)

    # run tests
    unittest.main()
