import base64
import os
import random
import shutil
import tempfile
import unittest
import urllib.parse

import mutagen

import amg


def download(url, filepath):
  cache_dir = os.getenv("TEST_DL_CACHE_DIR")
  if cache_dir is not None:
    os.makedirs(cache_dir, exist_ok=True)
    cache_filepath = os.path.join(cache_dir,
                                  os.path.basename(urllib.parse.urlsplit(url).path))
    if os.path.isfile(cache_filepath):
      shutil.copyfile(cache_filepath, filepath)
      return
  amg.fetch_ressource(url, filepath)
  if cache_dir is not None:
    shutil.copyfile(filepath, cache_filepath)


class TestTag(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.ref_temp_dir = tempfile.TemporaryDirectory()
    vorbis_filepath = os.path.join(cls.ref_temp_dir.name, "f.ogg")
    download("https://upload.wikimedia.org/wikipedia/en/0/09/Opeth_-_Deliverance.ogg",
             vorbis_filepath)
    opus_filepath = os.path.join(cls.ref_temp_dir.name, "f.opus")
    download("https://people.xiph.org/~giles/2012/opus/ehren-paper_lights-64.opus",
             opus_filepath)
    mp3_filepath = os.path.join(cls.ref_temp_dir.name, "f.mp3")
    download("http://www.stephaniequinn.com/Music/Vivaldi%20-%20Spring%20from%20Four%20Seasons.mp3",
             mp3_filepath)
    m4a_filepath = os.path.join(cls.ref_temp_dir.name, "f.m4a")
    download("https://auphonic.com/media/audio-examples/01.auphonic-demo-unprocessed.m4a",
             m4a_filepath)

  @classmethod
  def tearDownClass(cls):
    cls.ref_temp_dir.cleanup()

  def setUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    for src_filename in os.listdir(__class__.ref_temp_dir.name):
      shutil.copy(os.path.join(__class__.ref_temp_dir.name, src_filename), self.temp_dir.name)
    self.vorbis_filepath = os.path.join(self.temp_dir.name, "f.ogg")
    self.opus_filepath = os.path.join(self.temp_dir.name, "f.opus")
    self.mp3_filepath = os.path.join(self.temp_dir.name, "f.mp3")
    self.m4a_filepath = os.path.join(self.temp_dir.name, "f.m4a")

  def tearDown(self):
    self.temp_dir.cleanup()

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

  def test_get_r128_loudness(self):
    refs = ((self.vorbis_filepath, -7.7, 2.6),
            (self.opus_filepath, -14.7, 1.1),
            (self.mp3_filepath, -19, -4.2),
            (self.m4a_filepath, -20.6, 0.1))
    for filepath, level_ref, peak_ref in refs:
      level, peak = amg.tag.get_r128_loudness(filepath)
      self.assertAlmostEqual(level, level_ref, msg=filepath)
      self.assertAlmostEqual(peak, peak_ref, msg=filepath)

  def test_tag(self):
    artist = "Artist"
    album = "Album"
    cover_data = os.urandom(random.randint(10000, 500000))
    review = amg.ReviewMetadata(None, artist, album, None, None, None, None)

    amg.tag.tag(self.vorbis_filepath, review, cover_data)
    tags = mutagen.File(self.vorbis_filepath)
    ref_tags = {"artist": [artist],
                "album": [album],
                "REPLAYGAIN_TRACK_GAIN": ["-6.30 dB"],
                "REPLAYGAIN_TRACK_PEAK": ["1.34896288"]}
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k], v)
    self.assertIn("metadata_block_picture", tags)
    self.assertEqual(len(tags["metadata_block_picture"]), 1)
    self.assertIn(base64.b64encode(cover_data).decode(),
                  tags["metadata_block_picture"][0])

    amg.tag.tag(self.opus_filepath, review, cover_data)
    tags = mutagen.File(self.opus_filepath)
    ref_tags = {"artist": [artist],
                "album": [album],
                "R128_TRACK_GAIN": ["-2125"]}
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k], v)
    self.assertIn("metadata_block_picture", tags)
    self.assertEqual(len(tags["metadata_block_picture"]), 1)
    self.assertIn(base64.b64encode(cover_data).decode(),
                  tags["metadata_block_picture"][0])

    amg.tag.tag(self.mp3_filepath, review, cover_data)
    tags = mutagen.File(self.mp3_filepath)
    ref_tags = {"TPE1": [artist],
                "TALB": [album]}
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k].text, v)
    self.assertIn("APIC:", tags)
    self.assertIn(cover_data,
                  tags["APIC:"].data)

    amg.tag.tag(self.m4a_filepath, review, cover_data)
    tags = mutagen.File(self.m4a_filepath)
    ref_tags = {"\xa9ART": [artist],
                "\xa9alb": [album]}
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k], v)
    self.assertIn("covr", tags)
    self.assertEqual(len(tags["covr"]), 1)
    self.assertEqual(bytes(tags["covr"][0]), cover_data)
