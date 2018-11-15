#!/usr/bin/env python3

""" Browse & play embedded tracks from Angry Metal Guy music reviews. """

__version__ = "2018.11.16.0"
__author__ = "desbma"
__license__ = "GPLv3"

import argparse
import collections
import contextlib
import datetime
import enum
import io
import itertools
import json
import locale
import logging
import operator
import os
import shutil
import shelve
import socket
import string
import subprocess
import tempfile
import urllib.parse
import webbrowser

HAS_JPEGOPTIM = (shutil.which("jpegoptim") is not None)
HAS_FFMPEG = (shutil.which("ffmpeg") is not None)

from amg import colored_logging
from amg import menu
from amg import mkstemp_ctx
from amg import sanitize
from amg import tag

import appdirs
import lxml.cssselect
import lxml.etree
import PIL.Image
import PIL.ImageFilter
import r128gain
import requests
import web_cache
import youtube_dl


PlayerMode = enum.Enum("PlayerMode",
                       ("MANUAL", "RADIO", "DISCOVER", "DISCOVER_DOWNLOAD"))
ReviewMetadata = collections.namedtuple("ReviewMetadata",
                                        ("url",
                                         "artist",
                                         "album",
                                         "cover_thumbnail_url",
                                         "cover_url",
                                         "date_published",
                                         "tags"))

ROOT_URL = "https://www.angrymetalguy.com/"
LAST_PLAYED_EXPIRATION_DAYS = 365
HTML_PARSER = lxml.etree.HTMLParser()
REVIEW_BLOCK_SELECTOR = lxml.cssselect.CSSSelector("article.category-review, "
                                                   "article.category-reviews, "
                                                   "article.tag-review, "
                                                   "article.tag-reviews, "
                                                   "article[class*=tag-things-you-might-have-missed-]")
REVIEW_LINK_SELECTOR = lxml.cssselect.CSSSelector(".entry-title a")
REVIEW_COVER_SELECTOR = lxml.cssselect.CSSSelector("img.wp-post-image")
REVIEW_DATE_SELECTOR = lxml.cssselect.CSSSelector("div.metabar-pad time.published")
PLAYER_IFRAME_SELECTOR = lxml.cssselect.CSSSelector("div.entry_content iframe")
BANDCAMP_JS_SELECTOR = lxml.cssselect.CSSSelector("html > head > script")
REVERBNATION_SCRIPT_SELECTOR = lxml.cssselect.CSSSelector("script")
IS_TRAVIS = os.getenv("CI") and os.getenv("TRAVIS")
TCP_TIMEOUT = 30.1 if IS_TRAVIS else 15.1
YDL_MAX_DOWNLOAD_TRIES = 5
USER_AGENT = "Mozilla/5.0 AMG-Player/{}".format(__version__)
MAX_COVER_SIZE = 1500


def fetch_page(url, *, http_cache=None):
  """ Fetch page & parse it with LXML. """
  if (http_cache is not None) and (url in http_cache):
    logging.getLogger().info("Got data for URL '%s' from cache" % (url))
    page = http_cache[url]
  else:
    logging.getLogger().debug("Fetching '%s'..." % (url))
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=TCP_TIMEOUT)
    response.raise_for_status()
    page = response.content
    if http_cache is not None:
      http_cache[url] = page
  return lxml.etree.XML(page.decode("utf-8"), HTML_PARSER)


def fetch_ressource(url, dest_filepath):
  """ Fetch ressource, and write it to file. """
  logging.getLogger().debug("Fetching '%s'..." % (url))
  headers = {"User-Agent": USER_AGENT}
  with contextlib.closing(requests.get(url, headers=headers, timeout=TCP_TIMEOUT, stream=True)) as response:
    response.raise_for_status()
    with open(dest_filepath, "wb") as dest_file:
      for chunk in response.iter_content(2 ** 14):
        dest_file.write(chunk)


def parse_review_block(review):
  """ Parse review block from main page and return a ReviewMetadata object. """
  tags = tuple(t.split("-", 1)[1] for t in review.get("class").split(" ") if (t.startswith("tag-") and
                                                                              not t.startswith("tag-review") and
                                                                              not t.split("-", 1)[1].isdigit()))
  review_link = REVIEW_LINK_SELECTOR(review)[0]
  url = review_link.get("href")
  title = lxml.etree.tostring(review_link, encoding="unicode", method="text").strip()
  expected_suffix = " Review"
  if title.endswith(expected_suffix):
    title = title[:len(title) - len(expected_suffix)]
  elif "[Things You Might Have Missed" in title:
    title = title.rsplit("[", 1)[0].strip()
  try:
    artist, album = map(str.strip, title.split("–", 1))
  except ValueError:
    # most likely not a review, ie. http://www.angrymetalguy.com/ep-edition-things-you-might-have-missed-2016/
    return None
  def make_absolute_url(url):
    url_parts = urllib.parse.urlsplit(url)
    if url_parts.scheme:
      return url
    url_parts = ("https",) + url_parts[1:]
    return urllib.parse.urlunsplit(url_parts)
  review_img = REVIEW_COVER_SELECTOR(review)[0]
  cover_thumbnail_url = make_absolute_url(review_img.get("src"))
  srcset = review_img.get("srcset")
  if srcset is not None:
    cover_url = make_absolute_url(srcset.split(" ")[-2])
  else:
    cover_url = None
  published = REVIEW_DATE_SELECTOR(review)[0].get("datetime")
  published = datetime.datetime.strptime(published, "%Y-%m-%dT%H:%M:%S+00:00")
  return ReviewMetadata(url, artist, album, cover_thumbnail_url, cover_url, published, tags)


def get_reviews():
  """ Parse site and yield ReviewMetadata objects. """
  previous_review = None
  for i in itertools.count():
    url = ROOT_URL if (i == 0) else "%spage/%u" % (ROOT_URL, i + 1)
    page = fetch_page(url)
    for review in REVIEW_BLOCK_SELECTOR(page):
      r = parse_review_block(review)
      if (r is not None) and (r != previous_review):
        yield r
        previous_review = r


def get_embedded_track(page, http_cache):
  """ Parse page and extract embedded track. """
  urls = None
  audio_only = False
  try:
    try:
      iframe = PLAYER_IFRAME_SELECTOR(page)[0]
    except IndexError:
      pass
    else:
      iframe_url = iframe.get("src")
      if iframe_url is not None:
        yt_prefixes = ("https://www.youtube.com/embed/",
                       "https://www.youtube-nocookie.com/embed/")
        bc_prefix = "https://bandcamp.com/EmbeddedPlayer/"
        sc_prefix = "https://w.soundcloud.com/player/"
        rn_prefix = "https://www.reverbnation.com/widget_code/"
        if any(map(iframe_url.startswith, yt_prefixes)):
          yt_id = urllib.parse.urlparse(iframe_url).path.rsplit("/", 1)[-1]
          urls = ("https://www.youtube.com/watch?v=%s" % (yt_id),)
        elif iframe_url.startswith(bc_prefix):
          iframe_page = fetch_page(iframe_url, http_cache=http_cache)
          js = BANDCAMP_JS_SELECTOR(iframe_page)[-1].text
          js = next(filter(operator.methodcaller("__contains__",
                                                 "var playerdata ="),
                           js.split("\n")))
          js = js.split("=", 1)[1].rstrip(";" + string.whitespace)
          js = json.loads(js)
          # import pprint
          # pprint.pprint(js)
          # exit(7)
          urls = tuple(t["title_link"] for t in js["tracks"] if (t["track_streaming"] and t["file"]))
          audio_only = True
        elif iframe_url.startswith(sc_prefix):
          urls = (iframe_url.split("&", 1)[0],)
          audio_only = True
        elif iframe_url.startswith(rn_prefix):
          iframe_page = fetch_page(iframe_url, http_cache=http_cache)
          scripts = REVERBNATION_SCRIPT_SELECTOR(iframe_page)
          js_prefix = "var configuration = "
          for script in scripts:
            if (script.text) and (js_prefix in script.text):
              js = script.text[script.text.find(js_prefix) + len(js_prefix):].splitlines()[0].rstrip(";")
              js = json.loads(js)
              break
          url = js["PLAYLIST"][0]["url"]
          url = urllib.parse.urlsplit(url)
          url = ("https",) + url[1:]
          url = urllib.parse.urlunsplit(url)
          urls = (url,)
          audio_only = True
  except Exception as e:
    logging.getLogger().error("%s: %s" % (e.__class__.__qualname__, e))
  if urls is not None:
    logging.getLogger().debug("Track URL(s): %s" % (" ".join(urls)))
  return urls, audio_only


class KnownReviews:

  class DataIndex(enum.IntEnum):
    LAST_PLAYED = 0
    PLAY_COUNT = 1
    DATA_INDEX_COUNT = 2

  def __init__(self):
    data_dir = appdirs.user_data_dir("amg-player")
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, "played.dat")
    self.data = shelve.open(filepath, protocol=3)
    # cleanup old entries
    now = datetime.datetime.now()
    to_del = []
    for url, (last_played, *_) in self.data.items():
      delta = now - last_played
      if delta.days > LAST_PLAYED_EXPIRATION_DAYS:
        to_del.append(url)
    for url in to_del:
      del self.data[url]

  def isKnownUrl(self, url):
    """ Return True if url if from a known review, False instead. """
    return url in self.data

  def setLastPlayed(self, url):
    """ Memorize a review's track has been read. """
    try:
      e = list(self.data[url])
    except KeyError:
      e = []
    if len(e) < __class__.DataIndex.DATA_INDEX_COUNT:
      e.extend(None for _ in range(__class__.DataIndex.DATA_INDEX_COUNT - len(e)))
    try:
      e[__class__.DataIndex.PLAY_COUNT] += 1
    except TypeError:
      # be compatible with when play count was not stored
      e[__class__.DataIndex.PLAY_COUNT] = 2 if e[__class__.DataIndex.LAST_PLAYED] is not None else 1
    e[__class__.DataIndex.LAST_PLAYED] = datetime.datetime.now()
    self.data[url] = tuple(e)

  def getLastPlayed(self, url):
    """ Return datetime of last review track playback. """
    return self.data[url][__class__.DataIndex.LAST_PLAYED]

  def getPlayCount(self, url):
    """ Return number of time a track has been played. """
    try:
      return self.data[url][__class__.DataIndex.PLAY_COUNT]
    except IndexError:
      # be compatible with when play count was not stored
      return 1


def get_cover_data(review):
  """ Fetch cover and return buffer of JPEG data. """
  cover_url = review.cover_url if review.cover_url is not None else review.cover_thumbnail_url
  cover_ext = os.path.splitext(urllib.parse.urlsplit(cover_url).path)[1][1:].lower()

  with mkstemp_ctx.mkstemp(prefix="amg_", suffix=".%s" % (cover_ext)) as filepath:
    fetch_ressource(cover_url, filepath)

    if cover_ext == "png":
      # convert to JPEG
      img = PIL.Image.open(filepath)
      if img.mode != "RGB":
        img = img.convert("RGB")
      f = io.BytesIO()
      img.save(f, format="JPEG", quality=90, optimize=True)
      f.seek(0)
      out_bytes = f.read()
    else:
      if HAS_JPEGOPTIM:
        cmd = ("jpegoptim", "-q", "--strip-all", filepath)
        subprocess.check_call(cmd)
      with open(filepath, "rb") as f:
        out_bytes = f.read()

  return out_bytes


def download_and_merge(review, track_urls, tmp_dir, cover_filepath):
  """ Download track, merge audio & album art, and return merged filepath. """
  # fetch audio
  # https://github.com/rg3/youtube-dl/blob/master/youtube_dl/YoutubeDL.py#L121-L269
  ydl_opts = {"outtmpl": os.path.join(tmp_dir, r"%(autonumber)s.%(ext)s")}
  try:
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
      ydl.download(track_urls)
  except youtube_dl.utils.DownloadError as e:
    # already logged
    # logging.getLogger().warning("Download error : %s" % (e))
    pass
  audio_filepaths = os.listdir(tmp_dir)
  audio_filepaths.sort()
  if not audio_filepaths:
    logging.getLogger().error("Download failed")
    return
  concat_filepath = tempfile.mktemp(dir=tmp_dir, suffix=".txt")
  with open(concat_filepath, "wt") as concat_file:
    for audio_filepath in audio_filepaths:
      concat_file.write("file %s\n" % (audio_filepath))

  # merge
  merged_filepath = tempfile.mktemp(dir=tmp_dir, suffix=".mkv")
  cmd = ("ffmpeg",
         "-loglevel", "quiet",
         "-loop", "1", "-framerate", "0.05", "-i", cover_filepath,
         "-f", "concat", "-i", concat_filepath,
         "-map", "0:v", "-map", "1:a",
         "-filter:v", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-c:a", "copy",
         "-c:v", "libx264", "-crf", "18", "-tune:v", "stillimage", "-preset", "ultrafast",
         "-shortest",
         "-f", "matroska", merged_filepath)
  logging.getLogger().debug("Merging Audio and image with command: %s" % (subprocess.list2cmdline(cmd)))
  subprocess.check_call(cmd, cwd=tmp_dir)

  return merged_filepath


def download_audio(review, track_urls):
  """ Download track audio to file in current directory, return True if success. """
  with tempfile.TemporaryDirectory(prefix="amg_") as tmp_dir:
    for try_idx in range(1, YDL_MAX_DOWNLOAD_TRIES + 1):
      logging.getLogger().info("Downloading audio for track(s) %s (%u/%u)" % (" ".join(track_urls), try_idx, YDL_MAX_DOWNLOAD_TRIES))
      ydl_opts = {"outtmpl": os.path.join(tmp_dir,
                                          ("%s-" % (review.date_published.strftime("%Y%m%d%H%M%S"))) +
                                          r"%(autonumber)s" +
                                          (". %s - %s" % (sanitize.sanitize_for_path(review.artist.replace(os.sep, "_")),
                                                          sanitize.sanitize_for_path(review.album.replace(os.sep, "_")))) +
                                          r".%(ext)s"),
                  "format": "opus/vorbis/bestaudio",
                  "postprocessors": [{"key": "FFmpegExtractAudio"},
                                     {"key": "FFmpegMetadata"}],
                  "socket_timeout": TCP_TIMEOUT}
      try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
          ydl.download(track_urls)
      except youtube_dl.utils.DownloadError as e:
        if isinstance(e.exc_info[1], socket.timeout):
          continue
        # already logged
        # logging.getLogger().warning("Download error : %s" % (e))
      break
    track_filepaths = tuple(map(lambda x: os.path.join(tmp_dir, x),
                                os.listdir(tmp_dir)))
    if not track_filepaths:
      logging.getLogger().error("Download failed")
      return False

    if not all(map(tag.has_embedded_album_art, track_filepaths)):
      # get cover
      cover_data = get_cover_data(review)

      # post process cover
      in_bytes = io.BytesIO(cover_data)
      img = PIL.Image.open(in_bytes)
      if img.mode != "RGB":
        img = img.convert("RGB")
      # resize covers above MAX_COVER_SIZExMAX_COVER_SIZE
      if (img.size[0] > MAX_COVER_SIZE) or (img.size[1] > MAX_COVER_SIZE):
        logging.getLogger().info("Resizing cover...")

        # resize
        img.thumbnail((MAX_COVER_SIZE, MAX_COVER_SIZE), PIL.Image.LANCZOS)

        # apply unsharp filter to remove resize blur (equivalent to (images/graphics)magick -unsharp 1.5x1+0.7+0.02)
        # we don't use PIL.ImageFilter.SHARPEN or PIL.ImageEnhance.Sharpness because we want precise control over
        # parameters
        unsharper = PIL.ImageFilter.UnsharpMask(radius=1.5, percent=70, threshold=5)
        img = img.filter(unsharper)

        # get bytes
        out_bytes = io.BytesIO()
        img.save(out_bytes, format="JPEG", quality=90, optimize=True)
        cover_data = out_bytes.getvalue()

    else:
      cover_data = None

    # add tags & embed cover
    files_tags = {}
    for track_filepath in track_filepaths:
      try:
        files_tags[track_filepath] = tag.tag(track_filepath, review, cover_data)
      except Exception as e:
        # raise
        logging.getLogger().warning("Failed to add tags to file '%s': %s %s" % (track_filepath,
                                                                                e.__class__.__qualname__,
                                                                                e))
    # RG/R128
    if HAS_FFMPEG:
      r128gain.process(track_filepaths, album_gain=len(track_filepaths) > 1)

    # move tracks
    for track_filepath in track_filepaths:
      dest_filename = os.path.basename(track_filepath)
      # add title tag in filename if available
      try:
        file_tags = files_tags[track_filepath]
      except KeyError:
        pass
      else:
        filename, ext = os.path.splitext(dest_filename)
        filename = " - ".join((filename, sanitize.sanitize_for_path(file_tags["title"][0])))
        dest_filename = "".join((filename, ext))
      dest_filepath = os.path.join(os.getcwd(), dest_filename)
      logging.getLogger().debug("Moving %s to %s" % (repr(track_filepath), repr(dest_filepath)))
      shutil.move(track_filepath, dest_filepath)

    return True


def play(review, track_urls, *, merge_with_picture):
  """ Play it fucking loud! """
  # TODO support other players (vlc, avplay, ffplay...)
  merge_with_picture = merge_with_picture and HAS_FFMPEG
  if merge_with_picture:
    with mkstemp_ctx.mkstemp(prefix="amg_", suffix=".jpg") as cover_filepath:
      cover_data = get_cover_data(review)
      with open(cover_filepath, "wb") as f:
        f.write(cover_data)

      with tempfile.TemporaryDirectory(prefix="amg_") as tmp_dir:
        merged_filepath = download_and_merge(review, track_urls, tmp_dir, cover_filepath)
        if merged_filepath is None:
          return
        cmd = ("mpv", merged_filepath)
        logging.getLogger().debug("Playing with command: %s" % (subprocess.list2cmdline(cmd)))
        subprocess.check_call(cmd)

  else:
    for track_url in track_urls:
      cmd_dl = ("youtube-dl", "-o", "-", track_url)
      logging.getLogger().debug("Downloading with command: %s" % (subprocess.list2cmdline(cmd_dl)))
      dl_process = subprocess.Popen(cmd_dl,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
      cmd = ("mpv", "--force-seekable=yes", "-")
      logging.getLogger().debug("Playing with command: %s" % (subprocess.list2cmdline(cmd)))
      subprocess.check_call(cmd, stdin=dl_process.stdout)


def cl_main():
  # parse args
  arg_parser = argparse.ArgumentParser(description="AMG Player v%s. %s" % (__version__, __doc__),
                                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  arg_parser.add_argument("-c",
                          "--count",
                          type=int,
                          default=20,
                          dest="count",
                          help="Amount of recent reviews to fetch")
  arg_parser.add_argument("-m",
                          "--mode",
                          choices=tuple(m.name.lower() for m in PlayerMode),
                          default=PlayerMode.MANUAL.name.lower(),
                          dest="mode",
                          help="""Playing mode.
                                  "manual" let you select tracks to play one by one.
                                  "radio" let you select the first one, and then plays all tracks by chronological
                                  order.
                                  "discover" automatically plays all tracks by chronological order from the first non
                                  played one.
                                  "discover_download" like "discover" but downloads tracks.""")
  arg_parser.add_argument("-i",
                          "--interactive",
                          action="store_true",
                          default=False,
                          dest="interactive",
                          help="Before playing each track, ask user confirmation, and allow opening review URL.")
  arg_parser.add_argument("-v",
                          "--verbosity",
                          choices=("warning", "normal", "debug"),
                          default="normal",
                          dest="verbosity",
                          help="Level of logging output")
  args = arg_parser.parse_args()
  args.mode = PlayerMode[args.mode.upper()]

  # setup logger
  logger = logging.getLogger()
  logging_level = {"warning": logging.WARNING,
                   "normal": logging.INFO,
                   "debug": logging.DEBUG}
  logging.getLogger().setLevel(logging_level[args.verbosity])
  logging.getLogger("requests").setLevel(logging.ERROR)
  logging.getLogger("urllib3").setLevel(logging.ERROR)
  logging.getLogger("PIL").setLevel(logging.ERROR)
  logging_formatter = colored_logging.ColoredFormatter(fmt="%(message)s")
  logging_handler = logging.StreamHandler()
  logging_handler.setFormatter(logging_formatter)
  logger.addHandler(logging_handler)

  # locale (for date display)
  locale.setlocale(locale.LC_ALL, "")

  # warn if missing tools
  if not HAS_FFMPEG:
    logging.getLogger().warning("FFmpeg is not installed, some features won't be available")

  # get reviews
  known_reviews = KnownReviews()
  reviews = list(itertools.islice(get_reviews(), args.count))

  # http cache
  cache_dir = appdirs.user_cache_dir("amg-player")
  os.makedirs(cache_dir, exist_ok=True)
  cache_filepath = os.path.join(cache_dir, "http_cache.db")
  http_cache = web_cache.WebCache(cache_filepath,
                                  "reviews",
                                  caching_strategy=web_cache.CachingStrategy.FIFO,
                                  expiration=60 * 60 * 24 * 30 * 3,  # 3 months
                                  compression=web_cache.Compression.DEFLATE)
  purged_count = http_cache.purge()
  row_count = len(http_cache)
  logging.getLogger().debug("HTTP Cache contains %u entries (%u removed)" % (row_count, purged_count))

  # initial menu
  if args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO):
    menu_ret = menu.AmgMenu.setupAndShow(args.mode, reviews, known_reviews, http_cache)

  to_play = None
  track_loop = True
  while track_loop:
    if (args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO)):
      if menu_ret is None:
        break
      else:
        selected_idx, action = menu_ret

    if args.mode is PlayerMode.MANUAL:
      # fully interactive mode
      review = reviews[selected_idx]
    elif args.mode is PlayerMode.RADIO:
      # select first track interactively, then auto play
      if to_play is None:
        review = reviews[selected_idx]
        to_play = reviews[0:reviews.index(review) + 1]
        to_play.reverse()
        to_play = iter(to_play)
    elif args.mode in (PlayerMode.DISCOVER, PlayerMode.DISCOVER_DOWNLOAD):
      # auto play all non played tracks
      if to_play is None:
        to_play = filter(lambda x: not known_reviews.isKnownUrl(x.url),
                         reversed(reviews))
    if args.mode in (PlayerMode.RADIO, PlayerMode.DISCOVER, PlayerMode.DISCOVER_DOWNLOAD):
      try:
        review = next(to_play)
      except StopIteration:
        break

    # fetch review & play
    review_page = fetch_page(review.url, http_cache=http_cache)
    track_urls, audio_only = get_embedded_track(review_page, http_cache)
    if track_urls is None:
      logging.getLogger().warning("Unable to extract embedded track")
    else:
      print("-" * (shutil.get_terminal_size()[0] - 1))
      print("Artist: %s\n"
            "Album: %s\n"
            "Review URL: %s\n"
            "Published: %s\n"
            "Tags: %s" % (review.artist,
                          review.album,
                          review.url,
                          review.date_published.strftime("%x %H:%M"),
                          ", ".join(review.tags)))
      if args.interactive:
        input_loop = True
        while input_loop:
          c = None
          while c not in frozenset("pdrsq"):
            c = input("[P]lay / [D]ownload / Go to [R]eview / [S]kip to next track / Exit [Q] ? ").lower()
          if c == "p":
            known_reviews.setLastPlayed(review.url)
            play(review, track_urls, merge_with_picture=audio_only)
            input_loop = False
          elif c == "d":
            download_audio(review, track_urls)
            input_loop = False
          elif c == "r":
            webbrowser.open_new_tab(review.url)
          elif c == "s":
            input_loop = False
          elif c == "q":
            input_loop = False
            track_loop = False
      else:
        known_reviews.setLastPlayed(review.url)
        if (((args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO)) and
                (action is menu.AmgMenu.UserAction.DOWNLOAD_AUDIO)) or
                (args.mode is PlayerMode.DISCOVER_DOWNLOAD)):
          download_audio(review, track_urls)
        else:
          play(review, track_urls, merge_with_picture=audio_only)

    if track_loop and (args.mode is PlayerMode.MANUAL):
      # update menu and display it
      menu_ret = menu.AmgMenu.setupAndShow(args.mode, reviews, known_reviews, http_cache, selected_idx=selected_idx)


if __name__ == "__main__":
  cl_main()
