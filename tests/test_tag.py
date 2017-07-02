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
    download("https://allthingsaudio.wikispaces.com/file/view/Shuffle%20for%20K.M.mp3/139190697/Shuffle%20for%20K.M.mp3",
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
    mf = mutagen.File(self.mp3_filepath)
    mf.tags.delall("APIC")
    mf.save()
    self.m4a_filepath = os.path.join(self.temp_dir.name, "f.m4a")
    mf = mutagen.File(self.m4a_filepath)
    del mf["covr"]
    mf.save()

  def tearDown(self):
    self.temp_dir.cleanup()

  def test_normalize_title_tag(self):
    references = (("CREST OF DARKNESS - Welcome The Dead (Official Video)",
                   "Crest of Darkness",
                   "Welcome the Dead",
                   "Welcome the Dead"),
                  ("REVEL IN FLESH - Emissary Of All Plagues (Official Lyric Video)",
                   "Revel in Flesh",
                   "Emissary of All Plagues",
                   "Emissary of All Plagues"),
                  ("BORNHOLM - March Of Saturn Lyricvideo",
                   "Bornholm",
                   "Primaeval Pantheons",
                   "March of Saturn"),
                  ("BLACK ANVIL - \"As Was\" (Official Track)",
                   "Black Anvil",
                   "As Was",
                   "As Was"),
                  ("Emptiness - Your Skin Won't Hide You (Official Premiere)",
                   "Emptiness",
                   "Not for Music",
                   "Your Skin Won't Hide You"),
                  ("The Light at the End (Effect)",
                   "Uniform",
                   "Wake in Fright",
                   "The Light at the End (Effect)"),
                  ("INFERNAL ANGELS - Belial: The Deceiver (OFFICIAL VIDEO)",
                   "Infernal Angels",
                   "Ars Goetia",
                   "Belial: The Deceiver"),
                  ("BEHEADED - Beast Incarnate (official video) PRE-ORDERS AVAILABLE",
                   "Beheaded",
                   "Beast Incarnate",
                   "Beast Incarnate"),
                  ("Undrask - Longhammer (OFFICIAL MUSIC VIDEO)",
                   "Undrask",
                   "Battle Through Time",
                   "Longhammer"),
                  ("Nuit Noire De L'Ame",
                   "Wolvennest",
                   "Wolvennest",
                   "Nuit Noire de l'Ame"),
                  ("L'Etoile Du Matin",
                   "Au Champ Des Morts",
                   "Dans La Joie",
                   "L'Etoile du Matin"),
                  ("Drude",
                   "Drude",
                   "Drude",
                   "Drude"),
                  ("Drude - Drude",
                   "Drude",
                   "Drude",
                   "Drude"),
                  ("Drude (official video)",
                   "Drude",
                   "Drude",
                   "Drude"),
                  ("Drude Drude (official video)",
                   "Drude",
                   "Drude",
                   "Drude"),
                  ("WITHERFALL - End Of Time (ALBUM VERSION - OFFICIAL TRACK)",
                   "Witherfall",
                   "Nocturnes and Requiems",
                   "End of Time"),
                  ("CRYSTAL VIPER - The Witch Is Back (2017) // official clip // AFM Records",
                   "Crystal Viper",
                   "Queen of the Witches",
                   "The Witch Is Back"),
                  ("CRYSTAL VIPER // AFM Records",
                   "Crystal Viper",
                   "Queen of the Witches",
                   "Crystal Viper"),
                  ("AFM Records",
                   "Crystal Viper",
                   "Queen of the Witches",
                   "Afm Records"),
                  ("Records",
                   "Crystal Viper",
                   "Queen of the Witches",
                   "Records"),
                  ("Dool - She Goat [taken from \"Here Now, There Then\", out on February 17th 2017]",
                   "Dool",
                   "Here Now, There Then",
                   "She Goat"),
                  ("Cnoc an Tursa - Wha Wadna Fecht for Charlie (New Track - 2017)",
                   "Cnoc an Tursa",
                   "The Forty Five",
                   "Wha Wadna Fecht for Charlie"),
                  ("Black Sites - Burning Away The Day (In Monochrome) 2016",
                   "Black Sites",
                   "In Monochrome",
                   "Burning Away the Day"),
                  ("In Thousand Lakes - Death Train [HD]",
                   "In Thousand Lakes",
                   "Age of Decay",
                   "Death Train"),
                  ("EX DEO - The Rise Of Hannibal (Official Audio) | Napalm Records",
                   "Ex Deo",
                   "The Immortal Wars",
                   "The Rise of Hannibal"),
                  ("Power Trip - \"Executioner's Tax (Swing of the Axe)\"",
                   "Power Trip",
                   "Nightmare Logic",
                   "Executioner's Tax (Swing of the Axe)"),
                  ("Antropomorphia \"Crown ov the Dead\" (OFFICIAL)",
                   "Antropomorphia",
                   "Sermon ov Wrath",
                   "Crown Ov the Dead"),
                  ("ARDUINI/BALICH - \"THE FALLEN\"",
                   "Arduini / Balich",
                   "Dawn of Ages",
                   "The Fallen"),
                  ("VENDETTA - Religion Is A Killer Pre-Listening",
                   "Vendetta",
                   "The 5th",
                   "Religion Is a Killer"),
                  ("DESECRATE THE FAITH 'Unholy Infestation' promo clip (Shrine of Enmity)",
                   "Desecrate the Faith",
                   "Unholy Infestation",
                   "Shrine of Enmity"),
                  ("\"This Mortal Road\" Official Stream",
                   "Rozamov",
                   "This Mortal Road",
                   "This Mortal Road"),
                  ("ANTROPOFAGUS - SPAWN OF CHAOS (OFFICIAL TRACK PREMIERE 2017) [COMATOSE MUSIC]",
                   "Antropofagus",
                   "Methods of Resurrection through Evisceration",
                   "Spawn of Chaos"),
                  ("Demonic Resurrection - Matsya - The Fish (Official Lyric Video)",
                   "Demonic Resurrection",
                   "Dashavatar",
                   "Matsya - The Fish"),
                  ("King of Asgard - Death And A New Sun [taken from \":taudr:\", out March 17th 2017]",
                   "King of Asgard",
                   ":taudr:",
                   "Death and a New Sun"),
                  ("DIĜIR GIDIM - Conversing with The Ethereal",
                   "Digir Gidim",
                   "I Thought There Was The Sun Awaiting My Awakening",
                   "Conversing with the Ethereal"),
                  ("EMERALD - Reckoning Day (PURE STEEL RECORDS)",
                   "Emerald",
                   "Reckoning Day",
                   "Reckoning Day"),
                  ("FALLS OF RAUROS - White Granite (Official single 2017)",
                   "Falls of Rauros",
                   "Vigilance Perennial",
                   "White Granite"),
                  ("VESCERA feat.Michael Vescera  - Beyond The Fight - album/tour  teaser 2017",
                   "Vescera",
                   "Beyond the Fight",
                   "feat.Michael"),  # the source string here is broken beyond any hope of salvation
                  ("Horte:  9  (Official Visual Presentation)",
                   "Horte",
                   "Horte",
                   "9"),
                  ("Trial (swe) \"Juxtaposed\" (OFFICIAL)",
                   "Trial",
                   "Motherless",
                   "Juxtaposed"),
                  ("TEHOM - Voices From The Darkside (Full song)",
                   "Tehom",
                   "The Merciless Light",
                   "Voices from the Darkside"),
                  ("DISTILLATOR - Summoning the Malicious (OFFICIAL VIDEO) | THRASH METAL [2017]",
                   "Distillator",
                   "Summoning the Malicious",
                   "Summoning the Malicious"),
                  ("Doublestone - Solen Sover (Studio Session) | May 2017 | Ripple Music",
                   "Doublestone",
                   "Devil’s Own",
                   "Solen Sover (Studio Session)"),
                  ("Slaegt - I Smell Blood",
                   "Slægt",
                   "Domus Mysterium",
                   "I Smell Blood"),
                  ("God Dethroned \"The World Ablaze\" (OFFICIAL VIDEO in 4k)",
                   "God Dethroned",
                   "The World Ablaze",
                   "The World Ablaze"),
                  ("ASSAULT (Singapore) - The Fallen Reich OFFICIAL VIDEO (Death Metal/Thrash Metal)",
                   "Assault",
                   "The Fallen Reich",
                   "The Fallen Reich"),
                  ("My Leviathan - Morass Of Molasses",
                   "Morass of Molasses",
                   "These Paths We Tread",
                   "My Leviathan"),
                  ("Rapheumets Well - Ghost Walkers Exodus (360 Video)",
                   "Rapheumets Well",
                   "Enders Door",
                   "Ghost Walkers Exodus"),
                  ("SUFFOCATION - Your Last Breaths (360 VISUALIZER OFFICIAL VIDEO)",
                   "Suffocation",
                   "…of the Dark Light",
                   "Your Last Breaths"),
                  ("Völur - Breaker of Skulls [taken from \"Ancestors\"]",
                   "Völur",
                   "Ancestors",
                   "Breaker of Skulls"),
                  ("Horrid - The Black March (From the Album Beyond The Dark Border)'",
                   "Horrid",
                   "Beyond The Dark Border",
                   "The Black March"),
                  ("APOSENTO - Partially Deceased Syndrome (Official Video-clip) [2017]",
                   "Aposento",
                   "Bleed to Death",
                   "Partially Deceased Syndrome"),
                  ("Conveyer - Disgrace (Audio)",
                   "Conveyer",
                   "No Future",
                   "Disgrace"),
                  ("DESULTORY \"Our Departure\" Lyrics Video",
                   "Desultory",
                   "Through Aching Aeons",
                   "Our Departure"),
                  ("Chant VI - La Vieillesse",
                   "Les Chants du Hasard",
                   "Les Chants du Hasard",
                   "Chant VI - La Vieillesse"),
                  ("Manilla Road - To Kill A King (The New Studio Album) MiniMix OUT: 30.06.17",
                   "Manilla Road",
                   "To Kill a King",
                   "To Kill a King"))

    for before, artist, album, after in references:
      self.assertEqual(amg.tag.normalize_title_tag(before, artist, album), after)

  @unittest.skipUnless(amg.HAS_FFMPEG, "FFmpeg is not installed")
  def test_get_r128_loudness(self):
    refs = ((self.vorbis_filepath, -7.7, 2.6),
            (self.opus_filepath, -14.7, 1.1),
            (self.mp3_filepath, -15.3, -0.1),
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

    # vorbis
    self.assertFalse(amg.tag.has_embedded_album_art(self.vorbis_filepath))
    amg.tag.tag(self.vorbis_filepath, review, cover_data)
    tags = mutagen.File(self.vorbis_filepath)
    ref_tags = {"artist": [artist],
                "album": [album]}
    if amg.HAS_FFMPEG:
      ref_tags.update({"REPLAYGAIN_TRACK_GAIN": ["-6.30 dB"],
                       "REPLAYGAIN_TRACK_PEAK": ["1.34896288"]})
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k], v)
    self.assertIn("metadata_block_picture", tags)
    self.assertEqual(len(tags["metadata_block_picture"]), 1)
    self.assertIn(base64.b64encode(cover_data).decode(),
                  tags["metadata_block_picture"][0])
    self.assertTrue(amg.tag.has_embedded_album_art(self.vorbis_filepath))

    # opus
    self.assertFalse(amg.tag.has_embedded_album_art(self.opus_filepath))
    amg.tag.tag(self.opus_filepath, review, cover_data)
    tags = mutagen.File(self.opus_filepath)
    ref_tags = {"artist": [artist],
                "album": [album]}
    if amg.HAS_FFMPEG:
      ref_tags["R128_TRACK_GAIN"] = ["179"]
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k], v)
    self.assertIn("metadata_block_picture", tags)
    self.assertEqual(len(tags["metadata_block_picture"]), 1)
    self.assertIn(base64.b64encode(cover_data).decode(),
                  tags["metadata_block_picture"][0])
    self.assertTrue(amg.tag.has_embedded_album_art(self.opus_filepath))

    # mp3
    self.assertFalse(amg.tag.has_embedded_album_art(self.mp3_filepath))
    amg.tag.tag(self.mp3_filepath, review, cover_data)
    tags = mutagen.File(self.mp3_filepath)
    ref_tags = {"TPE1": [artist],
                "TALB": [album]}
    if amg.HAS_FFMPEG:
      ref_tags.update({"TXXX:REPLAYGAIN_TRACK_GAIN": ["1.30 dB"],
                       "TXXX:REPLAYGAIN_TRACK_PEAK": ["0.988553"]})
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k].text, v)
    self.assertIn("APIC:", tags)
    self.assertIn(cover_data,
                  tags["APIC:"].data)
    self.assertTrue(amg.tag.has_embedded_album_art(self.mp3_filepath))

    # mp4
    self.assertFalse(amg.tag.has_embedded_album_art(self.m4a_filepath))
    amg.tag.tag(self.m4a_filepath, review, cover_data)
    tags = mutagen.File(self.m4a_filepath)
    ref_tags = {"\xa9ART": [artist],
                "\xa9alb": [album]}
    for k, v in ref_tags.items():
      self.assertIn(k, tags)
      self.assertEqual(tags[k], v)
    if amg.HAS_FFMPEG:
      self.assertIn("----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_GAIN", tags)
      self.assertEqual(len(tags["----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_GAIN"]), 1)
      self.assertEqual(bytes(tags["----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_GAIN"][0]), b"6.60 dB")
      self.assertIn("----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_PEAK", tags)
      self.assertEqual(len(tags["----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_PEAK"]), 1)
      self.assertEqual(bytes(tags["----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_PEAK"][0]), b"1.011579")
    self.assertIn("covr", tags)
    self.assertEqual(len(tags["covr"]), 1)
    self.assertEqual(bytes(tags["covr"][0]), cover_data)
    self.assertTrue(amg.tag.has_embedded_album_art(self.m4a_filepath))
