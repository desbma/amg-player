import base64
import datetime
import logging
import operator
import re
import string
import subprocess

import mutagen
import mutagen.easyid3
import mutagen.easymp4

from amg import sanitize


R128_REF_LOUDNESS_DBFS = -23
RG_REF_LOUDNESS_DBFS = -14


def normalize_title_tag(title, artist, album):
  """ Remove useless prefix and suffix from title tag string. """
  original_title = title

  # basic string funcs
  rclean_chars = list(string.punctuation)
  for c in "!?)":
    rclean_chars.remove(c)
  rclean_chars = str(rclean_chars) + string.whitespace
  def rclean(s):
    return s.rstrip(rclean_chars)
  def startslike(s, l):
    return s.lower().startswith(l.lower())
  def endslike(s, l):
    return s.rstrip(string.punctuation).lower().endswith(l)
  def rmsuffix(s, e):
    return s.rstrip(string.punctuation)[:-len(e)]

  title = rclean(title.strip(string.whitespace))

  # build list of common useless expressions
  expressions = []
  words1 = ("", "official", "new")
  words2 = ("", "video", "music", "track", "lyric", "album", "promo", "stream")
  words3 = ("video", "track", "premiere", "version", "clip", "audio", "stream")
  for w1 in words1:
    for w2 in words2:
      for w3 in words3:
        if (w1 or w2) and (w3 != w2):
          for rsep in (" ", ""):
            rpart = rsep.join((w2, w3)).strip()
            expressions.append(" ".join((w1, rpart)).strip())
  expressions.extend(("pre-orders available", "preorders available", "hd",
                      "official", "pre-listening", "prelistening"))
  year = datetime.datetime.today().year
  for y in range(year - 5, year + 1):
    expressions.append(str(y))
  expressions.sort(key=len, reverse=True)

  # detect and remove  'taken from album xxx, out on yyy' suffix
  match = re.search("taken from .*, out on", title, re.IGNORECASE)
  if match:
    new_title = rclean(title[:match.start(0)])
    if new_title:
      title = new_title

  loop = True
  while loop:
    loop = False

    # detect and remove 'xxx records' suffix
    expression = "records"
    if endslike(title, expression):
      new_title = rclean(rmsuffix(title, expression))
      new_title = rclean(" ".join(new_title.split()[:-1]))
      if new_title:
        title = new_title
        loop = True

    for expression in expressions:
      # detect and remove common suffixes
      if endslike(title, expression):
        new_title = rclean(rmsuffix(title, expression))
        if new_title:
          title = new_title
          loop = True
          break

      # detect and remove common prefixes
      if startslike(title, expression):
        new_title = title[len(expression):]
        new_title = new_title.lstrip(string.punctuation + string.whitespace)
        if new_title:
          title = new_title
          loop = True
          break

    if loop:
      continue

    # detect and remove artist prefix
    if startslike(title, artist):
      new_title = title[len(artist):]
      new_title = new_title.lstrip(string.punctuation + string.whitespace)
      if new_title:
        title = new_title
        loop = True
    elif startslike(title, artist.replace(" ", "")):
      new_title = title[len(artist.replace(" ", "")):]
      new_title = new_title.lstrip(string.punctuation + string.whitespace)
      if new_title:
        title = new_title
        loop = True

    # detect and remove album prefix
    elif startslike(title, album):
      new_title = title[len(album):]
      new_title = new_title.lstrip(string.punctuation + string.whitespace)
      if new_title:
        title = new_title
        loop = True

    # detect and remove album suffix
    if endslike(title, album.lower()):
      new_title = rclean(rmsuffix(title, album.lower()))
      if new_title:
        title = new_title
        loop = True

  # detect unpaired chars
  char_pairs = ("()", "\"" * 2, "'" * 2)
  for c1, c2 in char_pairs:
    if title.endswith(c2) and (c1 not in title[:-1]):
      title = title[:-1]
    elif title.startswith(c1) and (c2 not in title[1:]):
      title = title[1:]

  # normalize case
  title = sanitize.normalize_tag_case(title)

  if title != original_title:
    logging.getLogger().debug("Fixed title tag: '%s' -> '%s'" % (original_title, title))

  return title


def tag(track_filepath, review, cover_data):
  """ Tag an audio file. """
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

  if isinstance(mf, mutagen.easyid3.EasyID3) or isinstance(mf, mutagen.easymp4.EasyMP4):
    # EasyXXX helpers do not allow embedding album art or RG tags, reopen as normal mutagen file
    mf.save()
    mf = mutagen.File(track_filepath)

  if cover_data is not None:
    # embed album art
    embed_album_art(mf, cover_data)

  # RG/R128
  add_rg_or_r128_tag(track_filepath, mf)

  mf.save()


def get_r128_loudness(audio_filepath):
  """ Get R128 loudness level and peak, in dbFS. """
  cmd = ("ffmpeg",
         "-hide_banner", "-nostats",
         "-i", audio_filepath,
         "-map", "a",
         "-filter_complex", "ebur128=peak=true",
         "-f", "null", "-")
  output = subprocess.check_output(cmd,
                                   stdin=subprocess.DEVNULL,
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True)
  output = output.splitlines()
  for i in reversed(range(len(output))):
    line = output[i]
    if line.startswith("[Parsed_ebur128") and line.endswith("Summary:"):
      break
  output = filter(None, map(str.strip, output[i:]))
  r128_stats = dict(tuple(map(str.strip, line.split(":", 1))) for line in output if not line.endswith(":"))
  r128_stats = {k: float(v.split(" ", 1)[0]) for k, v in r128_stats.items()}
  return r128_stats["I"], r128_stats["Peak"]


def encode_float_to_fixed_point_7dot8(f):
  """ Encode float f to a fixed point Q7.8 integer. """
  # https://en.wikipedia.org/wiki/Q_(number_format)#Float_to_Q
  return int(round(f * (2 ** 8), 0))


def add_rg_or_r128_tag(track_filepath, mf):
  """ Add ReplayGain/R128 tags to file. """
  level, peak = get_r128_loudness(track_filepath)
  if isinstance(mf, mutagen.oggvorbis.OggVorbis):
    # https://wiki.xiph.org/VorbisComment#Replay_Gain
    mf["REPLAYGAIN_TRACK_GAIN"] = "%.2f dB" % (RG_REF_LOUDNESS_DBFS - level)
    # peak_dbfs = 20 * log10(max_sample) <=> max_sample = 10^(peak_dbfs / 20)
    mf["REPLAYGAIN_TRACK_PEAK"] = "%.8f" % (10 ** (peak / 20))
  elif isinstance(mf, mutagen.oggopus.OggOpus):
    # https://wiki.xiph.org/OggOpus#Comment_Header
    # for now, use ReplayGain -14 dBFS as reference loudness
    # this is what foobar2000 and GMMP do
    fp = encode_float_to_fixed_point_7dot8(RG_REF_LOUDNESS_DBFS - level)
    assert(-32768 <= fp <= 32767)
    mf["R128_TRACK_GAIN"] = str(fp)
  elif isinstance(mf, mutagen.mp3.MP3):
    # http://wiki.hydrogenaud.io/index.php?title=ReplayGain_2.0_specification#ID3v2
    mf.tags.add(mutagen.id3.TXXX(encoding=mutagen.id3.Encoding.LATIN1,
                                 desc="REPLAYGAIN_TRACK_GAIN",
                                 text="%.2f dB" % (RG_REF_LOUDNESS_DBFS - level)))
    mf.tags.add(mutagen.id3.TXXX(encoding=mutagen.id3.Encoding.LATIN1,
                                 desc="REPLAYGAIN_TRACK_PEAK",
                                 text="%.6f" % (10 ** (peak / 20))))
    # other legacy formats:
    # http://wiki.hydrogenaud.io/index.php?title=ReplayGain_legacy_metadata_formats#ID3v2_RGAD
    # http://wiki.hydrogenaud.io/index.php?title=ReplayGain_legacy_metadata_formats#ID3v2_RVA2
  elif isinstance(mf, mutagen.mp4.MP4):
    # https://github.com/xbmc/xbmc/blob/9e855967380ef3a5d25718ff2e6db5e3dd2e2829/xbmc/music/tags/TagLoaderTagLib.cpp#L806-L812
    mf["----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_GAIN"] = mutagen.mp4.MP4FreeForm(("%.2f dB" % (RG_REF_LOUDNESS_DBFS - level)).encode())
    mf["----:COM.APPLE.ITUNES:REPLAYGAIN_TRACK_PEAK"] = mutagen.mp4.MP4FreeForm(("%.6f" % (10 ** (peak / 20))).encode())


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
