#!/usr/bin/env python3

""" Browse & play embedded tracks from Angry Metal Guy music reviews. """

__version__ = "0.2.0"
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

from amg import colored_logging

import appdirs
import cursesmenu
import lxml.cssselect
import lxml.etree
import requests
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


def fetch_page(url):
  """ Fetch page & parse it with LXML. """
  logging.getLogger().debug("Fetching '%s'..." % (url))
  response = requests.get(url, timeout=9.1)
  response.raise_for_status()
  page = response.content.decode("utf-8")
  return lxml.etree.XML(page, HTML_PARSER)


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
  review_img = REVIEW_COVER_SELECTOR(review)[0]
  cover_thumbnail_url = "http:%s" % (review_img.get("src"))
  srcset = review_img.get("srcset")
  if srcset is not None:
    cover_url = "http:%s" % (srcset.split(" ")[-2])
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


def get_embedded_track(page):
  """ Parse page and extract embedded track. """
  url = None
  audio_only = False
  try:
    iframe = PLAYER_IFRAME_SELECTOR(page)[0]
    iframe_url = iframe.get("src")
    if iframe_url is not None:
      yt_prefix = "https://www.youtube.com/embed/"
      bc_prefix = "https://bandcamp.com/EmbeddedPlayer/"
      sc_prefix = "https://w.soundcloud.com/player/"
      if iframe_url.startswith(yt_prefix):
        yt_id = iframe_url[len(yt_prefix):]
        url = "https://www.youtube.com/watch?v=%s" % (yt_id)
      elif iframe_url.startswith(bc_prefix):
        iframe_page = fetch_page(iframe_url)
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


def set_played(url):
  """ Memorize a review's track has been read, return new dict of read URLs. """
  data = get_played_urls()
  data[url] = (datetime.datetime.now(), )
  return data


def get_played_urls():
  """ Get deque of URLs of reviews URLs whose tracks have already been read. """
  data_dir = appdirs.user_data_dir("amg-player")
  filepath = os.path.join(data_dir, "played.dat")
  data = shelve.open(filepath, protocol=3)
  # cleanup old entries
  now = datetime.datetime.now()
  to_del = []
  for url, (last_played, *_) in data.items():
    delta = now - last_played
    if delta.days > LAST_PLAYED_EXPIRATION_DAYS:
      to_del.append(url)
  for url in to_del:
    del data[url]
  return data


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
  print("Playing track from album '%s' from '%s'...\nReview URL: %s" % (review.album,
                                                                        review.artist,
                                                                        review.url))
  if (merge_with_picture and
          ((shutil.which("ffmpeg") is not None) or (shutil.which("avconv") is not None))):
    with tempfile.TemporaryDirectory() as tmp_dir,\
            download_and_merge(review, track_url, tmp_dir) as merge_process:
      cmd = ("mpv", "-")
      logging.getLogger().debug("Playing with command: %s" % (subprocess.list2cmdline(cmd)))
      subprocess.check_call(cmd, stdin=merge_process.stdout)
      merge_process.terminate()
  else:
    cmd = ("mpv", track_url)
    logging.getLogger().debug("Playing with command: %s" % (subprocess.list2cmdline(cmd)))
    subprocess.check_call(cmd)


def reviews_to_strings(reviews, already_played_urls):
  """ Generate a list of string representations of reviews. """
  lines = []
  for i, review in enumerate(reviews):
    try:
      last_played = already_played_urls[review.url][0].strftime("%x %X")
    except KeyError:
      last_played = "never"
    lines.append(("%s - %s" % (review.artist, review.album),
                  "Published: %s" % (review.date_published.strftime("%x")),
                  "Last played: %s" % (last_played)))
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


def setup_and_show_menu(mode, reviews, already_played_urls, selected_idx=None):
  """ Setup and display interactive menu, return selected review index or None if exist requested. """
  menu_subtitle = {PlayerMode.MANUAL: "Select a track to play",
                   PlayerMode.RADIO: "Select track to start playing from"}
  menu = cursesmenu.SelectionMenu(reviews_to_strings(reviews, already_played_urls),
                                  "AMG Player",
                                  "%s mode: %s" % (mode.name.capitalize(),
                                                   menu_subtitle[mode]))
  if selected_idx is not None:
    menu.current_option = selected_idx
  menu.show()
  idx = menu.selected_option
  return None if (idx == len(reviews)) else idx


def cl_main():
  # parse args
  arg_parser = argparse.ArgumentParser(description=__doc__,
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
  already_played_urls = get_played_urls()
  reviews = list(itertools.islice(get_reviews(), args.count))

  # initial menu
  if args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO):
    selected_idx = setup_and_show_menu(args.mode, reviews, already_played_urls)

  if args.mode is PlayerMode.MANUAL:
    # fully interactive mode
    while selected_idx is not None:
      review = reviews[selected_idx]
      review_page = fetch_page(review.url)
      track_url, audio_only = get_embedded_track(review_page)
      if track_url is None:
        logging.getLogger().warning("Unable to extract embedded track")
      else:
        already_played_urls = set_played(review.url)
        play(review, track_url, merge_with_picture=audio_only)

      # update menu and display it
      selected_idx = setup_and_show_menu(args.mode, reviews, already_played_urls, selected_idx=selected_idx)

  elif (args.mode is PlayerMode.RADIO) and (selected_idx is not None):
    # select first track interactively, then auto play
    review = reviews[selected_idx]
    to_play = reviews[0:reviews.index(review) + 1]
    to_play.reverse()
    for review in to_play:
      review_page = fetch_page(review.url)
      track_url, audio_only = get_embedded_track(review_page)
      if track_url is None:
        logging.getLogger().warning("Unable to extract embedded track")
      else:
        already_played_urls = set_played(review.url)
        play(review, track_url, merge_with_picture=audio_only)

  elif args.mode is PlayerMode.DISCOVER:
    # auto play all non played tracks
    for review in reversed(reviews):
      if review.url in already_played_urls:
        continue
      review_page = fetch_page(review.url)
      track_url, audio_only = get_embedded_track(review_page)
      if track_url is None:
        logging.getLogger().warning("Unable to extract embedded track")
      else:
        already_played_urls = set_played(review.url)
        play(review, track_url, merge_with_picture=audio_only)


if __name__ == "__main__":
  cl_main()
