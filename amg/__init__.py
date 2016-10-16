#!/usr/bin/env python3

""" Browse & play embedded tracks from Angry Metal Guy music reviews. """

__version__ = "0.2.8"
__author__ = "desbma"
__license__ = "GPLv3"

import argparse
import collections
import contextlib
import datetime
import enum
import itertools
import json
import locale
import logging
import operator
import os
import shutil
import shelve
import string
import subprocess
import tempfile
import urllib.parse
import webbrowser

from amg import colored_logging

import appdirs
import cursesmenu
import lxml.cssselect
import lxml.etree
import requests
import web_cache
import youtube_dl


PlayerMode = enum.Enum("PlayerMode",
                       ("MANUAL", "RADIO", "DISCOVER"))
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
REVIEW_BLOCK_SELECTOR = lxml.cssselect.CSSSelector("article.tag-review")
REVIEW_LINK_SELECTOR = lxml.cssselect.CSSSelector(".entry-title a")
REVIEW_COVER_SELECTOR = lxml.cssselect.CSSSelector("img.wp-post-image")
REVIEW_DATE_SELECTOR = lxml.cssselect.CSSSelector("div.metabar-pad time.published")
PLAYER_IFRAME_SELECTOR = lxml.cssselect.CSSSelector("div.entry_content iframe")
BANDCAMP_JS_SELECTOR = lxml.cssselect.CSSSelector("html > head > script")


def fetch_page(url, *, http_cache=None):
  """ Fetch page & parse it with LXML. """
  if (http_cache is not None) and (url in http_cache):
    logging.getLogger().info("Got data for URL '%s' from cache" % (url))
    page = http_cache[url]
  else:
    logging.getLogger().debug("Fetching '%s'..." % (url))
    response = requests.get(url, timeout=9.1)
    response.raise_for_status()
    page = response.content
    if http_cache is not None:
      http_cache[url] = page
  return lxml.etree.XML(page.decode("utf-8"), HTML_PARSER)


def fetch_ressource(url, dest_filepath):
  """ Fetch ressource, and write it to file. """
  logging.getLogger().debug("Fetching '%s'..." % (url))
  with contextlib.closing(requests.get(url, timeout=9.1, stream=True)) as response:
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
  artist, album = map(str.strip, title.split("–", 1))
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
  published = datetime.datetime.strptime(published, "%Y-%m-%dT%H:%M:%S+00:00").date()
  return ReviewMetadata(url, artist, album, cover_thumbnail_url, cover_url, published, tags)


def get_reviews():
  """ Parse site and yield ReviewMetadata objects. """
  for i in itertools.count():
    url = ROOT_URL if (i == 0) else "%spage/%u" % (ROOT_URL, i + 1)
    page = fetch_page(url)
    for review in REVIEW_BLOCK_SELECTOR(page):
      yield parse_review_block(review)


def get_embedded_track(page, http_cache):
  """ Parse page and extract embedded track. """
  url = None
  audio_only = False
  try:
    try:
      iframe = PLAYER_IFRAME_SELECTOR(page)[0]
    except IndexError:
      pass
    else:
      iframe_url = iframe.get("src")
      if iframe_url is not None:
        yt_prefix = "https://www.youtube.com/embed/"
        bc_prefix = "https://bandcamp.com/EmbeddedPlayer/"
        sc_prefix = "https://w.soundcloud.com/player/"
        if iframe_url.startswith(yt_prefix):
          yt_id = iframe_url[len(yt_prefix):]
          url = "https://www.youtube.com/watch?v=%s" % (yt_id)
        elif iframe_url.startswith(bc_prefix):
          iframe_page = fetch_page(iframe_url, http_cache=http_cache)
          js = BANDCAMP_JS_SELECTOR(iframe_page)[-1].text
          js = next(filter(operator.methodcaller("__contains__",
                                                 "var playerdata ="),
                           js.split("\n")))
          js = js.split("=", 1)[1].rstrip(";" + string.whitespace)
          js = json.loads(js)
          url = js["linkback"]
          audio_only = True
        elif iframe_url.startswith(sc_prefix):
          url = iframe_url.split("&", 1)[0]
          audio_only = True
  except Exception as e:
    logging.getLogger().error("%s: %s" % (e.__class__.__qualname__, e))
  if url is not None:
    logging.getLogger().debug("Track URL: %s" % (url))
  return url, audio_only


class KnownReviews:

  class DataIndex(enum.IntEnum):
    LAST_PLAYED = 0
    PLAY_COUNT = 1
    DATA_INDEX_COUNT = 2

  def __init__(self):
    data_dir = appdirs.user_data_dir("amg-player")
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


def download_and_merge(review, track_url, tmp_dir):
  # fetch audio
  # https://github.com/rg3/youtube-dl/blob/master/youtube_dl/YoutubeDL.py#L121-L269
  ydl_opts = {"outtmpl": os.path.join(tmp_dir, r"%(autonumber)s.%(ext)s")}
  with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    ydl.download((track_url,))
  audio_filepaths = os.listdir(tmp_dir)
  concat_filepath = tempfile.mktemp(dir=tmp_dir, suffix=".txt")
  with open(concat_filepath, "wt") as concat_file:
    for audio_filepath in audio_filepaths:
      concat_file.write("file %s\n" % (audio_filepath))

  # fetch cover
  img_filepath = tempfile.mktemp(dir=tmp_dir, suffix=".jpg")
  if review.cover_url is not None:
    fetch_ressource(review.cover_url, img_filepath)
  else:
    fetch_ressource(review.cover_thumbnail_url, img_filepath)

  # merge
  cmd = (shutil.which("ffmpeg") or shutil.which("avconv"),
         "-loglevel", "quiet",
         "-loop", "1", "-framerate", "1", "-i", img_filepath,
         "-f", "concat", "-i", concat_filepath,
         "-filter:v", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-c:a", "copy",
         "-c:v", "libx264", "-crf", "18", "-tune:v", "stillimage", "-preset", "ultrafast",
         "-shortest",
         "-f", "matroska", "-")
  logging.getLogger().debug("Merging Audio and image with command: %s" % (subprocess.list2cmdline(cmd)))
  return subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=tmp_dir)


def play(review, track_url, *, merge_with_picture):
  """ Play it fucking loud! """
  # TODO support other players (vlc, avplay, ffplay...)
  if (merge_with_picture and
          ((shutil.which("ffmpeg") is not None) or (shutil.which("avconv") is not None))):
    with tempfile.TemporaryDirectory() as tmp_dir,\
            download_and_merge(review, track_url, tmp_dir) as merge_process:
      cmd = ("mpv", "-")
      logging.getLogger().debug("Playing with command: %s" % (subprocess.list2cmdline(cmd)))
      subprocess.check_call(cmd, stdin=merge_process.stdout)
      merge_process.terminate()
  else:
    cmd_dl = ("youtube-dl", "-o", "-", track_url)
    logging.getLogger().debug("Downloading with command: %s" % (subprocess.list2cmdline(cmd_dl)))
    dl_process = subprocess.Popen(cmd_dl,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
    cmd = ("mpv", "--force-seekable=yes", "-")
    logging.getLogger().debug("Playing with command: %s" % (subprocess.list2cmdline(cmd)))
    subprocess.check_call(cmd, stdin=dl_process.stdout)


class AmgMenu(cursesmenu.CursesMenu):

  """ Custom menu to choose review/track. """

  UserAction = enum.Enum("ReviewAction", ("DEFAULT", "OPEN_REVIEW"))

  def __init__(self, *, reviews, known_reviews, http_cache, mode, selected_idx):
    menu_subtitle = {PlayerMode.MANUAL: "Select a track to play",
                     PlayerMode.RADIO: "Select track to start playing from"}
    super().__init__("AMG Player v%s" % (__version__),
                     "%s mode: %s "
                     "(ENTER to play, "
                     "r to open review, "
                     "q to exit)" % (mode.name.capitalize(),
                                     menu_subtitle[mode]),
                     True)
    if selected_idx is not None:
      self.current_option = selected_idx
    review_strings = __class__.reviewsToStrings(reviews, known_reviews, http_cache)
    for index, (review, review_string) in enumerate(zip(reviews, review_strings)):
      self.append_item(ReviewItem(review, review_string, index, self))

  def process_user_input(self):
    """ Override key handling to add "open review" and "quick exit" features.

    See cursesmenu.CursesMenu.process_user_input
    """
    self.user_action = __class__.UserAction.DEFAULT
    c = super().process_user_input()
    if c in frozenset(map(ord, "rR")):
      self.user_action = __class__.UserAction.OPEN_REVIEW
      self.select()
    elif c in frozenset(map(ord, "qQ")):
      # select last item (exit item)
      self.current_option = len(self.items) - 1
      self.select()

  def get_last_user_action(self):
    """ Return last user action when item was selected. """
    return self.user_action

  @staticmethod
  def reviewsToStrings(reviews, known_reviews, http_cache):
    """ Generate a list of string representations of reviews. """
    lines = []
    for i, review in enumerate(reviews):
      try:
        play_count = known_reviews.getPlayCount(review.url)
        played = "Last played: %s (%u time%s)" % (known_reviews.getLastPlayed(review.url).strftime("%x %X"),
                                                  play_count,
                                                  "s" if play_count > 1 else "")
      except KeyError:
        if review.url in http_cache:
          review_page = fetch_page(review.url, http_cache=http_cache)
          if get_embedded_track(review_page, http_cache)[0] is None:
            played = "No track"
          else:
            played = "Last played: never"
        else:
          played = "Last played: never"
      lines.append(("%s - %s" % (review.artist, review.album),
                    "Published: %s" % (review.date_published.strftime("%x")),
                    played))
    # auto align/justify
    max_lens = [0] * len(lines[0])
    for line in lines:
      for i, s in enumerate(line):
        if len(s) > max_lens[i]:
          max_lens[i] = len(s)
    sep = "\t"
    for i, line in enumerate(lines):
      lines[i] = "%s%s" % (" " if i < 9 else "",
                           sep.join(s.ljust(max_len) for s, max_len in zip(line, max_lens)))
    return lines

  @staticmethod
  def setupAndShow(mode, reviews, known_reviews, http_cache, selected_idx=None):
    """ Setup and display interactive menu, return selected review index or None if exist requested. """
    menu = AmgMenu(reviews=reviews,
                   known_reviews=known_reviews,
                   http_cache=http_cache,
                   mode=mode,
                   selected_idx=selected_idx)
    menu.show()
    idx = menu.selected_option
    return None if (idx == len(reviews)) else idx


class ReviewItem(cursesmenu.items.SelectionItem):

  """ Custom menu item (menu line), overriden to support several actions per item. """

  def __init__(self, review, review_string, index, menu):
    super().__init__(review_string, index, menu)
    self.review = review

  def action(self):
    if self.menu.get_last_user_action() is AmgMenu.UserAction.OPEN_REVIEW:
      webbrowser.open_new_tab(self.review.url)
      self.should_exit = False
    else:
      self.should_exit = True


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
                                  played one.""")
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
  logging_formatter = colored_logging.ColoredFormatter(fmt="%(message)s")
  logging_handler = logging.StreamHandler()
  logging_handler.setFormatter(logging_formatter)
  logger.addHandler(logging_handler)

  # locale (for date display)
  locale.setlocale(locale.LC_ALL, "")

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
    selected_idx = AmgMenu.setupAndShow(args.mode, reviews, known_reviews, http_cache)

  to_play = None
  track_loop = True
  while track_loop:
    if (args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO)) and (selected_idx is None):
      break

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
    elif args.mode is PlayerMode.DISCOVER:
      # auto play all non played tracks
      if to_play is None:
        to_play = filter(lambda x: not known_reviews.isKnownUrl(x.url),
                         reversed(reviews))
    if args.mode in (PlayerMode.RADIO, PlayerMode.DISCOVER):
      try:
        review = next(to_play)
      except StopIteration:
        break

    # fetch review & play
    review_page = fetch_page(review.url, http_cache=http_cache)
    track_url, audio_only = get_embedded_track(review_page, http_cache)
    if track_url is None:
      logging.getLogger().warning("Unable to extract embedded track")
    else:
      print("-" * (shutil.get_terminal_size()[0] - 1))
      print("Artist: %s\n"
            "Album: %s\n"
            "Review URL: %s\n"
            "Date published: %s\n"
            "Tags: %s" % (review.artist,
                          review.album,
                          review.url,
                          review.date_published,
                          ", ".join(review.tags)))
      if args.interactive:
        input_loop = True
        while input_loop:
          c = None
          while c not in frozenset("prsq"):
            c = input("Play (p) / Go to review (r) / Skip to next track (s) / Exit (q) ? ").lower()
          if c == "p":
            known_reviews.setLastPlayed(review.url)
            play(review, track_url, merge_with_picture=audio_only)
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
        play(review, track_url, merge_with_picture=audio_only)

    if track_loop and (args.mode is PlayerMode.MANUAL):
      # update menu and display it
      selected_idx = AmgMenu.setupAndShow(args.mode, reviews, known_reviews, http_cache, selected_idx=selected_idx)


if __name__ == "__main__":
  cl_main()
