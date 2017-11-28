import base64
import calendar
import datetime
import logging
import operator
import re
import string

import mutagen
import mutagen.easyid3
import mutagen.easymp4
import unidecode

from amg import sanitize


def normalize_title_tag(title, artist, album):
  """ Remove useless prefix and suffix from title tag string. """
  original_title = title

  # basic string funcs
  rclean_chars = list(string.punctuation)
  lclean_chars = rclean_chars.copy()
  for c in "!?)-":
    rclean_chars.remove(c)
  for c in "(":
    lclean_chars.remove(c)
  rclean_chars = str(rclean_chars) + string.whitespace
  lclean_chars = str(lclean_chars) + string.whitespace
  def rclean(s):
    r = s.rstrip(rclean_chars)
    if r.endswith(" -"):
      r = r[:-2].rstrip(rclean_chars)
    return r
  def lclean(s):
    r = s.lstrip(lclean_chars)
    c = unidecode.unidecode_expect_ascii(r).lstrip(lclean_chars)
    if c != r:
      r = c
    return r

  def startslike(s, l):
    return unidecode.unidecode_expect_ascii(s).lstrip(string.punctuation).lower().startswith(unidecode.unidecode_expect_ascii(l).rstrip(string.punctuation).lower())
  def endslike(s, l):
    norm_s = unidecode.unidecode_expect_ascii(s).rstrip(string.punctuation).lower()
    norm_l = unidecode.unidecode_expect_ascii(l).lower()
    trunc = norm_s[:-len(norm_l)]
    return (norm_s.endswith(norm_l) and ((not trunc) or (not norm_s[:-len(norm_l)][-1].isalnum())))
  def rmsuffix(s, e):
    return s.rstrip(string.punctuation)[:-len(unidecode.unidecode_expect_ascii(e))]
  def rmprefix(s, e):
    return s.lstrip(string.punctuation)[len(unidecode.unidecode_expect_ascii(e)):]

  # build list of common useless expressions
  expressions = []
  words1 = ("", "official", "new", "full", "the new")
  words2 = ("", "video", "music", "track", "lyric", "lyrics", "album", "album/tour", "promo", "stream", "single",
            "visual", "360", "studio", "audio")
  words3 = ("video", "track", "premiere", "version", "clip", "audio", "stream", "single", "teaser", "presentation",
            "song", "in 4k", "visualizer", "album", "promo", "only", "excerpt", "vr")
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
                      "uncensored"))
  year = datetime.datetime.today().year
  for y in range(year - 5, year + 1):
    expressions.append(str(y))
    for month_name, month_abbr in zip(MONTH_NAMES, MONTH_NAMES_ABBR):
      expressions.append("%s %u" % (month_name, y))
      expressions.append("%s %u" % (month_abbr, y))
  expressions.sort(key=len, reverse=True)
  expressions_suffix = expressions
  expressions_prefix = expressions.copy()
  expressions_prefix.remove("song")

  # remove consecutive spaces
  title = " ".join(title.split())

  # detect and remove  'taken from album xxx, out (on) yyy' suffix
  match = re.search("taken from .*, out ", title, re.IGNORECASE)
  if match:
    new_title = rclean(title[:match.start(0)])
    if new_title:
      title = new_title

  # detect and remove  'from xxx LP' suffix
  match = re.search("from .* LP", title, re.IGNORECASE)
  if match:
    new_title = rclean(title[:match.start(0)])
    if new_title:
      title = new_title

  # detect and remove  'from xxx album' suffix
  match = re.search("from .* album", title, re.IGNORECASE)
  if match:
    new_title = rclean(title[:match.start(0)])
    if new_title:
      title = new_title

  # detect and remove  'xxx out: yy.zz.aa' suffix
  match = re.search(" [^ ]* out: [0-9]*.[0-9]*.[0-9]*", title, re.IGNORECASE)
  if match:
    new_title = rclean(title[:match.start(0)])
    if new_title:
      title = new_title

  # detect and remove  '[xxx music]' suffix
  match = re.search("[\[\( ][a-z]* music$", title.rstrip(string.punctuation), re.IGNORECASE)
  if match:
    new_title = rclean(title[:match.start(0)])
    if new_title:
      title = new_title

  title = rclean(title.strip(string.whitespace))

  artist_removed = False
  loop = True
  while loop:
    loop = False

    # detect and remove 'xxx records' suffix
    expression = "records"
    if endslike(title, expression):
      match = re.search("[|\)\(\[][0-9a-z ]*%s$" % (expression), title.rstrip(string.punctuation), re.IGNORECASE)
      if match:
        # '(xxx yyy records)' suffix
        new_title = rclean(title[:match.start(0)])
      else:
        new_title = rclean(rmsuffix(title, expression))
        new_title = rclean(" ".join(new_title.split()[:-1]))
      if new_title:
        title = new_title
        loop = True

    # detect and remove '- xxx metal' suffix
    for genre in ("metal", "grindcore", "grind"):
      if endslike(title, genre):  # performance optimization
        match = re.search("[\-|\(\[/]+[ ]*(?:[0-9a-z/-]+[ ]*)+" + genre + "$",
                          title.rstrip(string.punctuation),
                          re.IGNORECASE)
        if match:
          new_title = rclean(title[:match.start(0)])
          if new_title:
            title = new_title
            loop = True

    # detect and remove  'album: xxx track yy'
    match = re.search("(album: .* )?track [0-9]+", title.rstrip(string.punctuation), re.IGNORECASE)
    if match:
      new_title = rclean(title[:match.start(0)]) + " " + lclean(title[match.end(0):])
      if new_title:
        title = new_title
        loop = True

    # detect and remove starting parenthesis expression
    if title.startswith("(") and (title.rfind(")") != (len(title) - 1)):
      new_title = lclean(title[title.rfind(")") + 1:])
      if new_title:
        title = new_title
        loop = True

    for expression in expressions_suffix:
      # detect and remove common suffixes
      if endslike(title, expression):
        new_title = rclean(rmsuffix(title, expression))
        if new_title:
          title = new_title
          loop = True
          break

    for expression in expressions_prefix:
      # detect and remove common prefixes
      if startslike(title, expression):
        new_title = lclean(rmprefix(title, expression))
        if new_title:
          title = new_title
          loop = True
          break

    if loop:
      continue

    if not artist_removed:
      # detect and remove artist prefix
      if startslike(title, artist):
        new_title = lclean(rmprefix(title, artist))
        if new_title:
          title = new_title
          loop = True
          artist_removed = True
      elif startslike(title, artist.replace(" ", "")):
        new_title = lclean(rmprefix(title, artist.replace(" ", "")))
        if new_title:
          title = new_title
          loop = True
          artist_removed = True

      # detect and remove artist suffix
      elif endslike(title, artist):
        new_title = rclean(rmsuffix(title, artist))
        if new_title:
          title = new_title
          loop = True
          artist_removed = True
      elif endslike(title, artist.replace(" ", "")):
        new_title = rclean(rmsuffix(title, artist.replace(" ", "")))
        if new_title:
          title = new_title
          loop = True
          artist_removed = True

    # detect and remove album prefix
    elif startslike(title, album):
      new_title = lclean(rmprefix(title, album))
      if new_title:
        title = new_title
        loop = True

    # detect and remove album suffix
    elif endslike(title, album):
      new_title = rclean(rmsuffix(title, album))
      if new_title:
        title = new_title
        loop = True
        # detect and remove album suffix's prefix
        for suffix in ("taken from", "from the album", "from"):
          if endslike(title, suffix):
            new_title = rclean(rmsuffix(title, suffix))
            if new_title:
              title = new_title

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

  # normalize case
  title = sanitize.normalize_tag_case(title)

  if title != original_title:
    logging.getLogger().debug("Fixed title tag: %s -> %s" % (repr(original_title), repr(title)))

  return title


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
