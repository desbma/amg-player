import abc
import base64
import calendar
import datetime
import functools
import itertools
import logging
import operator
import string

import mutagen
import mutagen.easyid3
import mutagen.easymp4
try:
  import re2 as re
except ImportError:
  import re
import unidecode

from amg import sanitize


class TitleNormalizer:

  """ Class to chain all title tag transformations. """

  def __init__(self, artist, album):
    self.cleaners = []

    # TODO separate cleaner from params and copy/reuse cleaners in TitleNormalizer.cleanup

    # remove consecutive spaces
    self.registerCleaner(FunctionCleaner(lambda x: " ".join(x.split()), execute_once=True))

    # detect and remove 'taken from album xxx, out (on) yyy' suffix
    self.registerCleaner(RegexSuffixCleaner("taken from .*, out ", execute_once=True))

    # detect and remove 'album: xxx track yy'
    self.registerCleaner(RegexCleaner("(album: .* )?track [0-9]+", execute_once=True))

    # detect and remove 'from xxx LP' suffix
    self.registerCleaner(RegexSuffixCleaner("from .* LP", execute_once=True))

    # detect and remove 'from xxx album' suffix
    self.registerCleaner(RegexSuffixCleaner("from .*album", execute_once=True))

    # detect and remove 'xxx out: yy.zz.aa' suffix
    self.registerCleaner(RegexSuffixCleaner(" [^ ]* out: [0-9]+.[0-9]+.[0-9]+", execute_once=True))

    # detect and remove 'out yy.zz' suffix
    self.registerCleaner(RegexSuffixCleaner(" out [0-9]+/[0-9]+", execute_once=True))

    # detect and remove 'out month xxth' suffix
    self.registerCleaner(RegexSuffixCleaner(" out [a-z]+ [0-9]+th", execute_once=True))

    # detect and remove '[xxx music]' suffix
    self.registerCleaner(RegexSuffixCleaner("[\[\( ][a-z]* music$", execute_once=True))

    # detect and remove 'xxx entertainment' suffix
    self.registerCleaner(RegexSuffixCleaner("[\[\( ][a-z]+ entertainment$", execute_once=True))

    # detect and remove 'record label xxx' suffix
    self.registerCleaner(RegexSuffixCleaner("record label:? [a-z0-9 ]*$", execute_once=True))

    # detect and remove 'record label xxx' suffix
    self.registerCleaner(RegexSuffixCleaner("next concert: .*$", execute_once=True))

    # detect and remove 'feat.xxx' suffix
    self.registerCleaner(RegexSuffixCleaner("feat\..*$", execute_once=True))

    # detect and remove '- xxx metal' suffix
    for genre in ("metal", "crust", "grindcore", "grind"):
      self.registerCleaner(RegexSuffixCleaner("[\-|\(\[/\]]+[ ]*(?:[0-9a-z/-]+[ ]*)+" + genre + "( song)?$",
                                              suffixes=(genre, " ".join((genre, "song"))),
                                              execute_once=True))

    # detect and remove 'xxx metal' prefix
    for genre in ("death",):
      self.registerCleaner(RegexPrefixCleaner("^" + genre + "[a-z- ]* metal ",
                                              execute_once=True))

    # detect and remove 'xxx productions' suffix
    self.registerCleaner(RegexSuffixCleaner("[\[\( ][a-z ]+ productions$"))

    # detect and remove track number prefix
    self.registerCleaner(RegexPrefixCleaner("^[0-9]+ - "))

    # detect and remove 'xxx records' suffix
    self.registerCleaner(RecordsSuffixCleaner("recordings"))
    self.registerCleaner(RecordsSuffixCleaner("records"))

    # build list of common useless expressions
    expressions = []
    words1 = ("", "official", "new", "full", "the new", "stop motion", "explicit")
    words2 = ("", "video", "music", "track", "lyric", "lyrics", "album", "album/tour", "promo", "stream", "single",
              "visual", "360", "studio", "audio", "song")
    words3 = ("video", "track", "premiere", "premier", "version", "clip", "audio", "stream", "single", "teaser", "presentation",
              "song", "in 4k", "4k", "visualizer", "album", "promo", "only", "excerpt", "vr", "lyric", "trailer")
    for w1 in words1:
      for w2 in words2:
        for w3 in words3:
          if w3 != w2:
            if w1 or w2:
              for rsep in (" ", "-", ""):
                rpart = rsep.join((w2, w3)).strip()
                expressions.append(" ".join((w1, rpart)).strip())
            else:
              expressions.append(w3)
    expressions.extend(("pre-orders available", "preorders available", "hd",
                        "official", "pre-listening", "prelistening", "trollzorn",
                        "uncensored", "s/t", "sw exclusive",
                        "transcending obscurity india", "transcending obscurity",
                        "trailer for the upcoming album"))
    year = datetime.datetime.today().year
    for y in range(year - 5, year + 1):
      expressions.append(str(y))
      for month_name, month_abbr in zip(MONTH_NAMES, MONTH_NAMES_ABBR):
        expressions.append("%s %u" % (month_name, y))
        expressions.append("%s %u" % (month_abbr, y))
    expressions.sort(key=len, reverse=True)
    expressions.remove("song")
    suffix_cleaner = SimpleSuffixCleaner()
    for expression in expressions:
      self.registerCleaner(suffix_cleaner, (expression,))
    prefix_cleaner = SimplePrefixCleaner()
    for expression in expressions:
      self.registerCleaner(prefix_cleaner, (expression,))

    # detect and remove artist prefix ot suffix
    self.registerCleaner(ArtistCleaner(), (artist,))

    # detect and remove starting parenthesis expression
    self.registerCleaner(StartParenthesesCleaner(execute_once=True))

    # detect and remove album prefix or suffix
    self.registerCleaner(AlbumCleaner(execute_once=True), (album,))

    # fix paired chars
    self.registerCleaner(PairedCharCleaner(execute_once=True))

    # remove some punctuation
    self.registerCleaner(FunctionCleaner(lambda x: x.strip("-"), execute_once=True))

    # normalize case
    self.registerCleaner(FunctionCleaner(sanitize.normalize_tag_case, execute_once=True))

    # post normalize case fix
    self.registerCleaner(FunctionCleaner(lambda x: x.replace("PT.", "pt."), execute_once=True))

  def registerCleaner(self, cleaner, args=()):
    assert(isinstance(cleaner, TitleCleanerBase))
    self.cleaners.append((cleaner, args))

  def cleanup(self, title):
    cur_title = title

    start_index = 0
    while self.cleaners:
      to_del_idx = None

      for i, (cleaner, args) in enumerate(self.cleaners):
        if i < start_index:
          continue

        if cleaner.doSkip(cur_title, *args):
          continue

        remove_cur_cleaner = False
        restart_loop = False

        new_title = cleaner.cleanup(cur_title, *args)
        if new_title and (new_title != cur_title):
          logging.getLogger().debug("%s changed title tag: %s -> %s" % (cleaner.__class__.__name__,
                                                                        repr(cur_title),
                                                                        repr(new_title)))
          # update string and remove this cleaner to avoid calling it several times
          cur_title = new_title
          remove_cur_cleaner = not cleaner.doKeep()
          restart_loop = True

        elif cleaner.execute_once:
          remove_cur_cleaner = True
          # this cleaner did not match and we will remove it, continue from same index
          start_index = i

        if remove_cur_cleaner:
          to_del_idx = i
        if restart_loop:
          start_index = 0
        if remove_cur_cleaner or restart_loop:
          break

      else:
        # all cleaners have been called and string did not change
        break

      if to_del_idx is not None:
        del self.cleaners[to_del_idx]

    if cur_title != title:
      logging.getLogger().info("Fixed title tag: %s -> %s" % (repr(title), repr(cur_title)))
    return cur_title


class TitleCleanerBase:

  """ Base class for all title cleaner subclasses. """

  RCLEAN_CHARS = list(string.punctuation)
  LCLEAN_CHARS = RCLEAN_CHARS.copy()
  for c in "!?)-":
    RCLEAN_CHARS.remove(c)
  for c in "(":
    LCLEAN_CHARS.remove(c)
  RCLEAN_CHARS = str(RCLEAN_CHARS) + string.whitespace
  LCLEAN_CHARS = str(LCLEAN_CHARS) + string.whitespace

  def __init__(self, *, execute_once=False):
    self.execute_once = execute_once

  def doSkip(self, title, *args):
    """ Return True if this cleaner can be skipped for this title string. """
    return False

  def doKeep(self):
    """ Return True if this cleaner should not be removed even if it matched. """
    return False

  @abc.abstractmethod
  def cleanup(self, title, *args):
    """ Cleanup a title string, and return the updated string. """
    pass

  def rclean(self, s):
    """ Remove garbage at right of string. """
    r = s.rstrip(__class__.RCLEAN_CHARS)
    if r.endswith(" -"):
      r = r[:-2].rstrip(__class__.RCLEAN_CHARS)
    return r

  def lclean(self, s):
    """ Remove garbage at left of string. """
    r = s.lstrip(__class__.LCLEAN_CHARS)
    c = unidecode.unidecode_expect_ascii(r).lstrip(__class__.LCLEAN_CHARS)
    if c != r:
      r = c
    return r

  @functools.lru_cache(maxsize=32768)
  def rnorm(self, s):
    return unidecode.unidecode_expect_ascii(s).rstrip(string.punctuation).lower()

  @functools.lru_cache(maxsize=32768)
  def lnorm(self, s):
    return unidecode.unidecode_expect_ascii(s).lstrip(string.punctuation).lower()

  def startslike(self, s, l):
    """ Return True if start of string s is similar to l. """
    return self.lnorm(s).startswith(self.rnorm(l))

  def endslike(self, s, l):
    """ Return True if end of string s is similar to l. """
    norm_s = self.rnorm(s)
    norm_l = self.rnorm(l)
    trunc = norm_s[:-len(norm_l)]
    return (norm_s.endswith(norm_l) and ((not trunc) or (not norm_s[:-len(norm_l)][-1].isalnum())))

  def rmsuffix(self, s, e):
    """ Remove string suffix. """
    return s.rstrip(string.punctuation)[:-len(unidecode.unidecode_expect_ascii(e))]

  def rmprefix(self, s, e):
    """ Remove string prefix. """
    return s.lstrip(string.punctuation)[len(unidecode.unidecode_expect_ascii(e)):]


class FunctionCleaner(TitleCleanerBase):

  """ Cleaner to apply a function to the title string. """

  def __init__(self, func, **kwargs):
    super().__init__(**kwargs)
    assert(callable(func))
    self.func = func

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    return self.func(title)


class SimplePrefixCleaner(TitleCleanerBase):

  """ Cleaner to remove a static string prefix. """

  def cleanup(self, title, prefix):
    """ See TitleCleanerBase.cleanup. """
    if self.startslike(title, prefix):
      title = self.lclean(self.rmprefix(title, prefix))
    return title


class SimpleSuffixCleaner(TitleCleanerBase):

  """ Cleaner to remove a static string suffix. """

  def cleanup(self, title, suffix):
    """ See TitleCleanerBase.cleanup. """
    if self.endslike(title, suffix):
      new_title = self.rclean(self.rmsuffix(title, suffix))
      if new_title.lower() != "the":
        title = new_title
    return title


class ArtistCleaner(SimplePrefixCleaner, SimpleSuffixCleaner):

  """ Cleaner to remove artist prefix/suffix. """

  def __init__(self, *args, **kwargs):
    self.prefix_removed = False
    self.suffix_removed = False
    super().__init__(*args, **kwargs)

  def doKeep(self):
    """ See TitleCleanerBase.doKeep. """
    return not self.suffix_removed

  def cleanup(self, title, artist):
    """ See TitleCleanerBase.cleanup. """
    for s, suffix_only in itertools.zip_longest(("by " + artist,
                                                 artist,
                                                 artist.replace(" ", ""),
                                                 artist.replace("and", "&"),
                                                 artist.replace("’", "")),
                                                (True,),
                                                fillvalue=False):
      # detect and remove artist prefix
      if (not suffix_only) and (not self.prefix_removed) and self.startslike(title, s):
        r = SimplePrefixCleaner.cleanup(self, title, s)
        self.prefix_removed = True
        return r
      # detect and remove artist suffix
      elif (not self.suffix_removed) and self.endslike(title, s):
        r = SimpleSuffixCleaner.cleanup(self, title, s)
        self.suffix_removed = True
        return r
    return title


class AlbumCleaner(SimplePrefixCleaner, SimpleSuffixCleaner):

  """ Cleaner to remove album prefix/suffix. """

  def cleanup(self, title, album):
    """ See TitleCleanerBase.cleanup. """
    # detect and remove album prefix
    if self.startslike(title, album):
      return SimplePrefixCleaner.cleanup(self, title, album)
    # detect and remove album suffix
    elif self.endslike(title, album):
      title = SimpleSuffixCleaner.cleanup(self, title, album)
      # detect and remove album suffix's prefix
      for suffix in ("taken from", "from the album", "from"):
        if self.endslike(title, suffix):
          new_title = SimpleSuffixCleaner.cleanup(self, title, suffix)
          if new_title:
            title = new_title
            break
    return title


class RegexCleaner(TitleCleanerBase):

  """ Cleaner to remove a regex match. """

  def __init__(self, regex, *, flags=re.IGNORECASE, **kwargs):
    super().__init__(**kwargs)
    self.regex = re.compile(regex, flags)

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    match = self.regex.search(title.rstrip(string.punctuation))
    if match:
      title = self.rclean(title[:match.start(0)]) + " " + self.lclean(title[match.end(0):])
    return title


class RegexSuffixCleaner(RegexCleaner):

  """ Cleaner to remove a regex suffix match. """

  def __init__(self, regex, *, suffixes=(), **kwargs):
    super().__init__(regex, **kwargs)
    self.suffixes = suffixes

  def doSkip(self, title, *args):
    """ See TitleCleanerBase.doSkip. """
    if self.suffixes:
      return not any(self.endslike(title, suffix) for suffix in self.suffixes)
    return super().doSkip(title, *args)

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    match = self.regex.search(title.rstrip(string.punctuation))
    if match:
      title = self.rclean(title[:match.start(0)])
    return title


class RegexPrefixCleaner(RegexCleaner):

  """ Cleaner to remove a regex prefix match. """

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    match = self.regex.search(title)
    if match:
      title = self.lclean(title[match.end(0):])
    return title


class RecordsSuffixCleaner(RegexSuffixCleaner, SimpleSuffixCleaner):

  """ Cleaner to remove record suffix. """

  def __init__(self, record_word, **kwargs):
    self.record_word = record_word
    super().__init__("[|\)\(\[][0-9a-z,/ ]+" + record_word + "$",
                     suffixes=(record_word,),
                     **kwargs)

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    # detect and remove 'xxx records' suffix
    match = self.regex.search(title.rstrip(string.punctuation))
    if match:
      # '(xxx yyy records)' suffix
      title = self.rclean(title[:match.start(0)])
    else:
      title = SimpleSuffixCleaner.cleanup(self, title, self.record_word)
      title = self.rclean(" ".join(title.split()[:-1]))
    return title


class StartParenthesesCleaner(TitleCleanerBase):

  """ Cleaner to remove parentheses string prefix. """

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    # detect and remove starting parenthesis expression
    if title.startswith("(") and (title.find(")") != (len(title) - 1)):
      return self.lclean(title[title.find(")") + 1:])
    return title


class PairedCharCleaner(TitleCleanerBase):

  """ Cleaner to fix chars that go by pair. """

  def cleanup(self, title):
    """ See TitleCleanerBase.cleanup. """
    # detect and remove unpaired chars
    char_pairs = (("()", False),
                  ("\"" * 2, False),
                  ("'" * 2, True))
    for (c1, c2), only_at_edges in char_pairs:
      if only_at_edges:
        if title.endswith(c2) and (c1 not in title[:-1]):
          title = title[:-1]
        elif title.startswith(c1) and (c2 not in title[1:]):
          title = title[1:]
      else:
        if c1 != c2:
          if (title.count(c1) + title.count(c2)) == 1:
            title = title.translate(str.maketrans("", "", c1 + c2))
        else:
          if title.count(c1) == 1:
            title = title.translate(str.maketrans("", "", c1))

    # detect and remove parenthesis at start and end
    if title.startswith("(") and title.endswith(")"):
      title = title[1:-1]

    return title


def normalize_title_tag(title, artist, album):
  """ Remove useless prefix and suffix from title tag string. """
  normalizer = TitleNormalizer(artist, album)
  return normalizer.cleanup(title)


def tag(track_filepath, review, cover_data):
  """ Tag an audio file, return tag dict excluding RG/R128 info and album art. """
  logging.getLogger().info("Tagging file '%s'" % (track_filepath))
  mf = mutagen.File(track_filepath)
  if isinstance(mf, mutagen.mp3.MP3):
    mf = mutagen.easyid3.EasyID3(track_filepath)
  elif isinstance(mf, mutagen.mp4.MP4):
    mf = mutagen.easymp4.EasyMP4(track_filepath)

  # override/fix source tags added by youtube-dl, because they often contain crap
  mf["artist"] = sanitize.normalize_tag_case(review.artist)
  mf["album"] = sanitize.normalize_tag_case(review.album)
  try:
    mf["title"] = normalize_title_tag(mf["title"][0], review.artist, review.album)
  except KeyError:
    pass
  tags = dict(mf)

  if cover_data is not None:
    if isinstance(mf, mutagen.easyid3.EasyID3) or isinstance(mf, mutagen.easymp4.EasyMP4):
      # EasyXXX helpers do not allow embedding album art, reopen as normal mutagen file
      mf.save()
      mf = mutagen.File(track_filepath)

    # embed album art
    embed_album_art(mf, cover_data)

  mf.save()

  return tags


def has_embedded_album_art(filepath):
  """ Return True if file already has an embedded album art, False instead. """
  mf = mutagen.File(filepath)
  if isinstance(mf, mutagen.ogg.OggFileType):
    return "metadata_block_picture" in mf
  elif isinstance(mf, mutagen.mp3.MP3):
    return any(map(operator.methodcaller("startswith", "APIC:"), mf.keys()))
  elif isinstance(mf, mutagen.mp4.MP4):
    return "covr" in mf


def embed_album_art(mf, cover_data):
  """ Embed album art into audio file. """
  if isinstance(mf, mutagen.ogg.OggFileType):
    picture = mutagen.flac.Picture()
    picture.data = cover_data
    picture.type = mutagen.id3.PictureType.COVER_FRONT
    picture.mime = "image/jpeg"
    encoded_data = base64.b64encode(picture.write())
    mf["metadata_block_picture"] = encoded_data.decode("ascii")
  elif isinstance(mf, mutagen.mp3.MP3):
    mf.tags.add(mutagen.id3.APIC(mime="image/jpeg",
                                 type=mutagen.id3.PictureType.COVER_FRONT,
                                 data=cover_data))
    mf.save()
  elif isinstance(mf, mutagen.mp4.MP4):
    mf["covr"] = [mutagen.mp4.MP4Cover(cover_data,
                                       imageformat=mutagen.mp4.AtomDataType.JPEG)]


# copy month names before changing locale
MONTH_NAMES = calendar.month_name[1:]
MONTH_NAMES_ABBR = calendar.month_abbr[1:]
