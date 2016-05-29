#!/usr/bin/env python3

""" Browse & play embedded tracks from Angry Metal Guy music reviews. """

__version__ = "0.0.1"
__author__ = "desbma"
__license__ = "GPLv3"

import argparse
import collections
import datetime
import itertools
import json
import locale
import logging
import operator
import os
import pickle
import signal
import string
import subprocess

from amg import colored_logging

import appdirs
import lxml.cssselect
import lxml.etree
import requests


ReviewMetadata = collections.namedtuple("ReviewMetadata",
                                        ("url",
                                         "artist",
                                         "album",
                                         "cover_thumbnail_url",
                                         "cover_url",
                                         "date_published",
                                         "tags"))

ROOT_URL = "https://www.angrymetalguy.com/"
HTML_PARSER = lxml.etree.HTMLParser()
REVIEW_BLOCK_SELECTOR = lxml.cssselect.CSSSelector("article.tag-review")
REVIEW_LINK_SELECTOR = lxml.cssselect.CSSSelector(".entry-title a")
REVIEW_COVER_SELECTOR = lxml.cssselect.CSSSelector("img.wp-post-image")
REVIEW_DATE_SELECTOR = lxml.cssselect.CSSSelector("div.metabar-pad time.published")
PLAYER_IFRAME_SELECTOR = lxml.cssselect.CSSSelector("div.entry_content iframe")
BANDCAMP_JS_SELECTOR = lxml.cssselect.CSSSelector("html > head > script")


def fetch(url):
  """ Fetch page & parse it with LXML. """
  logging.getLogger().debug("Fetching '%s'..." % (url))
  response = requests.get(url, timeout=9.1)
  response.raise_for_status()
  page = response.content.decode("utf-8")
  return lxml.etree.XML(page, HTML_PARSER)


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
  cover_url = "http:%s" % (review_img.get("srcset").split(" ")[-2])
  published = REVIEW_DATE_SELECTOR(review)[0].get("datetime")
  published = datetime.datetime.strptime(published, "%Y-%m-%dT%H:%M:%S+00:00").date()
  return ReviewMetadata(url, artist, album, cover_thumbnail_url, cover_url, published, tags)


def get_reviews():
  """ Parse site and yield ReviewMetadata objects. """
  for i in itertools.count():
    url = ROOT_URL if (i == 0) else "%spage/%u" % (ROOT_URL, i + 1)
    page = fetch(url)
    for review in REVIEW_BLOCK_SELECTOR(page):
      yield parse_review_block(review)


def get_embedded_track(page):
  """ Parse page and extract embedded track. """
  # TODO handle soundcloud
  try:
    iframe = PLAYER_IFRAME_SELECTOR(page)[0]
    iframe_url = iframe.get("src")
    if iframe_url is not None:
      yt_prefix = "https://www.youtube.com/embed/"
      bc_prefix = "https://bandcamp.com/EmbeddedPlayer/"
      if iframe_url.startswith(yt_prefix):
        yt_id = iframe_url[len(yt_prefix):]
        return "https://www.youtube.com/watch?v=%s" % (yt_id)
      elif iframe_url.startswith(bc_prefix):
        iframe_page = fetch(iframe_url)
        js = BANDCAMP_JS_SELECTOR(iframe_page)[-1].text
        js = next(filter(operator.methodcaller("__contains__",
                                               "var playerdata ="),
                         js.split("\n")))
        js = js.split("=", 1)[1].rstrip(";" + string.whitespace)
        js = json.loads(js)
        return js["linkback"]
  except Exception as e:
    logging.getLogger().error("%s: %s" % (e.__class__.__qualname__, e))


def set_read(url):
  """ Memorize a review's track has been read, return new deque of read URLs. """
  data = get_read_urls()
  data.append((url, datetime.datetime.now()))
  data_dir = appdirs.user_data_dir("amg-player")
  if not os.path.isdir(data_dir):
    os.makedirs(data_dir, exist_ok=True)
  filepath = os.path.join(data_dir, "read.dat")
  with open(filepath, "wb") as f:
    pickle.dump(data, f)
  return data


def get_read_urls():
  """ Get deque of URLs of reviews URLs whose tracks have already been read. """
  data_dir = appdirs.user_data_dir("amg-player")
  filepath = os.path.join(data_dir, "read.dat")
  try:
    with open(filepath, "rb") as f:
      data =  pickle.load(f)
  except (FileNotFoundError, EOFError):
    data = collections.deque((), 1000)
  return data


def terminal_choice(items):
  """ Ask user to choose an item in the terminal. """
  c = 0
  while c not in range(1, len(items) + 1):
    try:
      c = int(input("? "))
    except ValueError:
      continue
    except KeyboardInterrupt:
      exit(128 + signal.SIGINT)
  return items[c - 1]


def play(review, track_url):
  """ Play it fucking loud! """
  # TODO support other players (vlc, avplay, ffplay...)
  # TODO use cover url as video image if track is not a video
  print("Playing track from album '%s' from '%s'...\nReview URL: %s" % (review.album,
                                                                        review.artist,
                                                                        review.url))
  subprocess.check_call(("mpv", track_url))


def print_review_entry(i, review, already_read_urls):
  """ Print review metadata for interactive selection. """
  indent = " " * 5
  print("% 3u. %s - %s" % (i, review.artist, review.album))
  print("%sTags: %s" % (indent, ", ".join(review.tags)))
  print("%sPublished: %s" % (indent, review.date_published.strftime("%x")))
  try:
    idx = tuple(map(operator.itemgetter(0),
                    already_read_urls)).index(review.url)
  except ValueError:
    print("%s** Not yet played **" % (indent))
  else:
    last_played = already_read_urls[idx][1]
    print("%sLast played: %s" % (indent, last_played.strftime("%x %X")))


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
                          choices=("manual", "radio", "discover"),
                          default="manual",
                          dest="mode",
                          help="""Playing mode.
                                  "manual" let you select tracks to play one by one.
                                  "radio" let you select the first one, and then plays all tracks by chronological order.
                                  "discover" automatically plays all tracks by chronological order from the first non played one.""")
  arg_parser.add_argument("-v",
                          "--verbosity",
                          choices=("warning", "normal", "debug"),
                          default="normal",
                          dest="verbosity",
                          help="Level of logging output")
  args = arg_parser.parse_args()

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

  # initial menu
  already_read_urls = get_read_urls()
  if args.mode in ("manual", "radio"):
    reviews = []
    for i, review in zip(range(1, args.count + 1), get_reviews()):
      reviews.append(review)
      print_review_entry(i, review, already_read_urls)

  if args.mode == "manual":
    # fully interactive mode
    while True:
      review = terminal_choice(reviews)
      review_page = fetch(review.url)
      track_url = get_embedded_track(review_page)
      if track_url is None:
        logging.getLogger().warning("Unable to extract embedded track")
        continue
      already_read_urls = set_read(review.url)
      play(review, track_url)

      for i, review in enumerate(reviews, 1):
        print_review_entry(i, review, already_read_urls)

  elif args.mode == "radio":
    # select first track interactively, then auto play
    review = terminal_choice(reviews)
    to_play = reviews[0:reviews.index(review) + 1]
    to_play.reverse()
    for review in to_play:
      review_page = fetch(review.url)
      track_url = get_embedded_track(review_page)
      if track_url is None:
        logging.getLogger().warning("Unable to extract embedded track")
        continue
      already_read_urls = set_read(review.url)
      play(review, track_url)

  elif args.mode == "discover":
    # auto play all non played tracks
    reviews = list(itertools.islice(get_reviews(), args.count))
    for review in reversed(reviews):
      if review.url in map(operator.itemgetter(0),
                           already_read_urls):
        continue
      review_page = fetch(review.url)
      track_url = get_embedded_track(review_page)
      if track_url is None:
        logging.getLogger().warning("Unable to extract embedded track")
        continue
      already_read_urls = set_read(review.url)
      play(review, track_url)


if __name__ == "__main__":
  cl_main()
