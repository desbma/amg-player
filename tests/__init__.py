#!/usr/bin/env python3

import datetime
import inspect
import logging
import os
import random
import shutil
import tempfile
import unittest

import amg


class TestAmg(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.ref_temp_dir = tempfile.TemporaryDirectory()
    ogg_filepath = os.path.join(cls.ref_temp_dir.name, "f.ogg")
    amg.fetch_ressource("https://upload.wikimedia.org/wikipedia/en/0/09/Opeth_-_Deliverance.ogg",
                        ogg_filepath)
    mp3_filepath = os.path.join(cls.ref_temp_dir.name, "f.mp3")
    amg.fetch_ressource("http://www.stephaniequinn.com/Music/Vivaldi%20-%20Spring%20from%20Four%20Seasons.mp3",
                        mp3_filepath)
    m4a_filepath = os.path.join(cls.ref_temp_dir.name, "f.m4a")
    amg.fetch_ressource("https://auphonic.com/media/audio-examples/01.auphonic-demo-unprocessed.m4a",
                        m4a_filepath)

  @classmethod
  def tearDownClass(cls):
    cls.ref_temp_dir.cleanup()

  def setUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    for src_filename in os.listdir(__class__.ref_temp_dir.name):
      shutil.copy(os.path.join(__class__.ref_temp_dir.name, src_filename), self.temp_dir.name)
    self.ogg_filepath = os.path.join(self.temp_dir.name, "f.ogg")
    self.mp3_filepath = os.path.join(self.temp_dir.name, "f.mp3")
    self.m4a_filepath = os.path.join(self.temp_dir.name, "f.m4a")

  def tearDown(self):
    self.temp_dir.cleanup()

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

  def test_normalize_title_tag(self):
    references = (("CREST OF DARKNESS - Welcome The Dead (Official Video)",
                   "Crest of Darkness",
                   None,
                   "Welcome the Dead"),
                  ("REVEL IN FLESH - Emissary Of All Plagues (Official Lyric Video)",
                   "Revel in Flesh",
                   None,
                   "Emissary of All Plagues"),
                  ("BORNHOLM - March Of Saturn Lyricvideo",
                   "Bornholm",
                   None,
                   "March of Saturn"),
                  ("BLACK ANVIL - \"As Was\" (Official Track)",
                   "Black Anvil",
                   None,
                   "As Was"),
                  ("Emptiness - Your Skin Won't Hide You (Official Premiere)",
                   "Emptiness",
                   None,
                   "Your Skin Won't Hide You"),
                  ("The Light at the End (Effect)",
                   "Uniform",
                   None,
                   "The Light at the End (Effect)"),
                  ("INFERNAL ANGELS - Belial: The Deceiver (OFFICIAL VIDEO)",
                   "Infernal Angels",
                   None,
                   "Belial: The Deceiver"),
                  ("BEHEADED - Beast Incarnate (official video) PRE-ORDERS AVAILABLE",
                   "Beheaded",
                   None,
                   "Beast Incarnate"),
                  ("Undrask - Longhammer (OFFICIAL MUSIC VIDEO)",
                   "Undrask",
                   None,
                   "Longhammer"),
                  ("Nuit Noire De L'Ame",
                   "Wolvennest",
                   None,
                   "Nuit Noire de l'Ame"),
                  ("L'Etoile Du Matin",
                   "Au Champ Des Morts",
                   None,
                   "L'Etoile du Matin"),
                  ("Drude",
                   "Drude",
                   None,
                   "Drude"),
                  ("Drude - Drude",
                   "Drude",
                   None,
                   "Drude"),
                  ("Drude (official video)",
                   "Drude",
                   None,
                   "Drude"),
                  ("Drude Drude (official video)",
                   "Drude",
                   None,
                   "Drude"),
                  ("WITHERFALL - End Of Time (ALBUM VERSION - OFFICIAL TRACK)",
                   "Witherfall",
                   None,
                   "End of Time"),
                  ("CRYSTAL VIPER - The Witch Is Back (2017) // official clip // AFM Records",
                   "Crystal Viper",
                   None,
                   "The Witch Is Back"),
                  ("CRYSTAL VIPER // AFM Records",
                   "Crystal Viper",
                   None,
                   "Crystal Viper"),
                  ("AFM Records",
                   "Crystal Viper",
                   None,
                   "Afm Records"),
                  ("Records",
                   "Crystal Viper",
                   None,
                   "Records"),
                  ("Dool - She Goat [taken from \"Here Now, There Then\", out on February 17th 2017]",
                   "Dool",
                   None,
                   "She Goat"),
                  ("Cnoc an Tursa - Wha Wadna Fecht for Charlie (New Track - 2017)",
                   "Cnoc an Tursa",
                   None,
                   "Wha Wadna Fecht for Charlie"),
                  ("Black Sites - Burning Away The Day (In Monochrome) 2016",
                   "Black Sites",
                   None,
                   "Burning Away the Day (In Monochrome)"),
                  ("In Thousand Lakes - Death Train [HD]",
                   "In Thousand Lakes",
                   None,
                   "Death Train"),
                  ("EX DEO - The Rise Of Hannibal (Official Audio) | Napalm Records",
                   "Ex Deo",
                   None,
                   "The Rise of Hannibal"),
                  ("Power Trip - \"Executioner's Tax (Swing of the Axe)\"",
                   "Power Trip",
                   None,
                   "Executioner's Tax (Swing of the Axe)"),
                  ("Antropomorphia \"Crown ov the Dead\" (OFFICIAL)",
                   "Antropomorphia",
                   None,
                   "Crown Ov the Dead"),
                  ("ARDUINI/BALICH - \"THE FALLEN\"",
                   "Arduini / Balich",
                   None,
                   "The Fallen"),
                  ("VENDETTA - Religion Is A Killer Pre-Listening",
                   "Vendetta",
                   None,
                   "Religion Is a Killer"),
                  ("DESECRATE THE FAITH 'Unholy Infestation' promo clip (Shrine of Enmity)",
                   "Desecrate the Faith",
                   "Unholy Infestation",
                   "Shrine of Enmity"),
                  ("\"This Mortal Road\" Official Stream",
                   "Rozamov",
                   "This Mortal Road",
                   "This Mortal Road"))

    for before, artist, album, after in references:
      self.assertEqual(amg.tag.normalize_title_tag(before, artist, album), after)

  def test_get_r128_volume(self):
    refs = ((self.ogg_filepath, -7.7),
            (self.mp3_filepath, -19),
            (self.m4a_filepath, -20.6))
    for filepath, volume in refs:
      self.assertAlmostEqual(amg.tag.get_r128_volume(filepath), volume, msg=filepath)


if __name__ == "__main__":
  # disable logging
  logging.basicConfig(level=logging.CRITICAL + 1)
  #logging.basicConfig(level=logging.DEBUG)

  # run tests
  unittest.main()
