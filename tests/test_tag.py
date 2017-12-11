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
                   "feat.Michael Vescera"),  # the source string here is broken beyond any hope of salvation
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
                   "To Kill a King"),
                  ("WEAPÖNIZER - Malefactor (from 'Lawless Age' LP 2017)",
                   "Weapönizer",
                   "Lawless Age",
                   "Malefactor"),
                  ("Sator Malus \"Endless Cycles Of Life & Death\" from \"Dark Matters\" Album",
                   "Sator Malus",
                   "Dark Matters",
                   "Endless Cycles of Life & Death"),
                  ("HERESIARCH - Storming upon Knaves (2017) Dark Descent Records",
                   "Heresiarch",
                   "Death Ordinance",
                   "Storming Upon Knaves"),
                  ("Stallion - Waiting For A Sign (Album: From The Dead 2017 - Track 4) Official",
                   "Stallion",
                   "From the Dead",
                   "Waiting for a Sign"),
                  ("Dystopia -Vanishing Point-",
                   "Boris",
                   "Dear",
                   "Dystopia -Vanishing Point-"),
                  ("DEADSONG",
                   "Boris",
                   "Dear",
                   "Deadsong"),
                  ("D.O.W.N -Domination of Waiting Noise-",
                   "Boris",
                   "Dear",
                   "D.O.W.N -Domination of Waiting Noise-"),
                  ("OBSCURITY - WAS UNS BLEIBT (OFFICIAL LYRIC VIDEO) | TROLLZORN",
                   "Obscurity",
                   "Streitmacht",
                   "Was Uns Bleibt"),
                  ("Kabbalah - Phantasmal Planetoid (Official Music Video) | 2017 Twin Earth Records",
                   "Kabbalah",
                   "Spectral Ascent",
                   "Phantasmal Planetoid"),
                  ("PATHOLOGY 'Pathology' promo (Lamentation)",
                   "Pathology",
                   "Pathology",
                   "Lamentation"),
                  ("Hexenklad - A Path to Ruin (Canadian Folk Influenced Black Metal)",
                   "Hexenklad",
                   "Spirit of the Stone",
                   "A Path to Ruin"),
                  ("Song Of Fire And Ice",
                   "Bloodnut",
                   "St. Ranga",
                   "Song of Fire and Ice"),
                  ("IIII: Here, At The Disposition Of Time (Inverting A Solar Giant)",
                   "Tchornobog",
                   "Tchornobog",
                   "IIII: Here, At the Disposition of Time (Inverting a Solar Giant)"),
                  ("II: Hallucinatory Black Breath Of Possession (Mountain-Eye Amalgamation)",
                   "Tchornobog",
                   "Tchornobog",
                   "II: Hallucinatory Black Breath of Possession (Mountain-Eye Amalgamation)"),
                  ("Temple of Void – \"Graven Desires\" (Lords of Death)",
                   "Temple of Void",
                   "Lords of Death",
                   "Graven Desires"),
                  ("THE NECROMANCERS - Salem Girl Pt.1 (AUDIO ONLY)",
                   "The Necromancers",
                   "Servants of the Salem Girl",
                   "Salem Girl Pt.1"),
                  ("VENOM INC - Dein Fleisch (OFFICIAL MUSIC VIDEO)",
                   "Venom Inc.",
                   "Avé",
                   "Dein Fleisch"),
                  ("Akercocke - Disappear (from Renaissance in Extremis)",
                   "Akercocke",
                   "Renaissance In Extremis",
                   "Disappear"),
                  ("SYN ZE SASE TRI - \"TĂRÎMU' DE LUMINĂ\"",
                   "Syn Ze Șase Tri",
                   "Zăul moș",
                   "Tarimu' de Lumina"),
                  ("GUTSLIT (India) - Brazen Bull (Brutal Death Metal/Grind)",
                   "Gutslit",
                   "Amputheatre",
                   "Brazen Bull"),
                  ("VAULTWRAITH \"The Vaultwraith\"",
                   "Vaultwraith",
                   "Death Is Proof of Satan’s Power",
                   "The Vaultwraith"),
                  ("FORGOTTEN TOMB - We Owe You Nothing (UNCENSORED)",
                   "Forgotten Tomb",
                   "We Owe You Nothing",
                   "We Owe You Nothing"),
                  ("Thy Serpent's Cult/ Track 02 Diabolic Force  from New Album 'Supremacy of Chaos' LP 2016",
                   "Thy Serpent’s Cult",
                   "Supremacy of Chaos",
                   "Diabolic Force"),
                  ("BLAZE OF PERDITION - Ashes Remain (Official Track Excerpt)",
                   "Blaze of Perdition",
                   "Conscious Darkness",
                   "Ashes Remain"),
                  ("THREAT SIGNAL - Elimination Process (Official 360 VR Video)",
                   "Threat Signal",
                   "Disconnect",
                   "Elimination Process"),
                  ("Death Toll 80k - Cause / Avoid (2017 - Grindcore)",
                   "Death Toll 80k",
                   "Step Down",
                   "Cause / Avoid"),
                  ("Loch Vostok - Summer (Official lyric)",
                   "Loch Vostok",
                   "Strife",
                   "Summer"),
                  ("SEA GOAT - Friends (Song Stream) // [Record Label: Swan Lake Records]",
                   "Sea Goat",
                   "Tata",
                   "Friends"),
                  ("MARGINAL (Belgium) - Delirium Tremens (Grindcore/Crust) Transcending Obscurity Records",
                   "Marginal",
                   "Total Destruction",
                   "Delirium Tremens"))

    for before, artist, album, after in references:
      self.assertEqual(amg.tag.normalize_title_tag(before, artist, album), after)

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
    self.assertIn("covr", tags)
    self.assertEqual(len(tags["covr"]), 1)
    self.assertEqual(bytes(tags["covr"][0]), cover_data)
    self.assertTrue(amg.tag.has_embedded_album_art(self.m4a_filepath))
