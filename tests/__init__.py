#!/usr/bin/env python3

import datetime
import inspect
import logging
import random
import unittest

import amg


class TestAmg(unittest.TestCase):

  def test_get_reviews(self):
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
      self.assertIsInstance(review.date_published, datetime.date)
      self.assertIsInstance(review.tags, tuple)
      self.assertTrue(review.tags)
      for tag in review.tags:
        self.assertIsInstance(tag, str)
    self.assertEqual(i, count - 1)

  def test_get_embedded_track(self):
    http_cache = amg.web_cache.WebCache(":memory:",
                                        "reviews",
                                        caching_strategy=amg.web_cache.CachingStrategy.FIFO)
    urls = {"https://www.angrymetalguy.com/vredehammer-violator-review/":
            (("https://www.youtube.com/watch?v=9Z34GAEO8hU",),
             False),
            "https://www.angrymetalguy.com/cadaveric-fumes-dimensions-obscure-review/":
            (("https://bloodharvestrecords.bandcamp.com/track/crepuscular-journey",
              "https://bloodharvestrecords.bandcamp.com/track/extatic-extirpation",
              "https://bloodharvestrecords.bandcamp.com/track/where-darkness-reigns-pristine",
              "https://bloodharvestrecords.bandcamp.com/track/swallowed-into-eternity"),
             True),
            "https://www.angrymetalguy.com/sinnery-feast-fools-review/":
            (("https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/257383834",),
             True),
            "https://www.angrymetalguy.com/hornss-telepath-review/":
            (("https://hornss.bandcamp.com/track/atrophic",),
             True)}
    for review_url, (expected_track_url, expected_audio_only) in urls.items():
      review_page = amg.fetch_page(review_url)
      track_url, audio_only = amg.get_embedded_track(review_page, http_cache)
      self.assertEqual(track_url, expected_track_url)
      self.assertEqual(audio_only, expected_audio_only)

  def test_normalize_tag_case(self):
    references = {"ALL CAPS IS SO STUPID": "All Caps Is So Stupid",
                  "i ZZ the a Bzz bhh": "I Zz the a Bzz Bhh",
                  "I.C.Y.C.S.D": "I.C.Y.C.S.D"}
    for before, after in references.items():
      self.assertEqual(amg.normalize_tag_case(before), after)

  def test_normalize_title_tag(self):
    references = {("CREST OF DARKNESS - Welcome The Dead (Official Video)", "Crest of Darkness"): "Welcome the Dead",
                  ("REVEL IN FLESH - Emissary Of All Plagues (Official Lyric Video)", "Revel in Flesh"): "Emissary of All Plagues",
                  ("BORNHOLM - March Of Saturn Lyricvideo", "Bornholm"): "March of Saturn"}
    for (before, artist), after in references.items():
      self.assertEqual(amg.normalize_title_tag(before, artist), after)


if __name__ == "__main__":
  # disable logging
  logging.basicConfig(level=logging.CRITICAL + 1)
  #logging.basicConfig(level=logging.DEBUG)

  # run tests
  unittest.main()
