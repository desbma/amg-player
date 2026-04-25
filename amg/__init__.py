#!/usr/bin/env python3

"""Browse & play embedded tracks from Angry Metal Guy music reviews."""

__version__ = "2026.03.3.1"
__author__ = "desbma"
__license__ = "GPLv3"

import argparse
import codecs
import collections
import concurrent.futures
import contextlib
import datetime
import enum
import io
import itertools
import json
import locale
import logging
import os
import re
import shelve
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
from collections.abc import Iterable, Sequence
from pathlib import Path

from lxml import cssselect as lxml_cssselect
from lxml import etree as lxml_etree  # ty: ignore[unresolved-import]
import PIL.Image
import PIL.ImageFilter
import platformdirs
import requests
import web_cache
import yt_dlp

import colorlog
import pathvalidate

from amg import menu, tag, ytdl_tqdm

HAS_JPEGOPTIM = shutil.which("jpegoptim") is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None

PlayerMode = enum.Enum("PlayerMode", ("MANUAL", "RADIO", "DISCOVER", "DISCOVER_DOWNLOAD"))
ReviewMetadata = collections.namedtuple(
    "ReviewMetadata", ("url", "artist", "album", "cover_thumbnail_url", "cover_url", "tags")
)

ROOT_URL = "https://www.angrymetalguy.com/"
REVIEW_URL = ROOT_URL  # f"{ROOT_URL}category/reviews/"
LAST_PLAYED_EXPIRATION_DAYS = 365
HTML_PARSER = lxml_etree.HTMLParser()
REVIEW_BLOCK_SELECTOR = lxml_cssselect.CSSSelector(
    "article.category-review, article.category-reviews, article[class*=tag-things-you-might-have-missed-]"
)
REVIEW_LINK_SELECTOR = lxml_cssselect.CSSSelector(".entry-title a")
REVIEW_COVER_SELECTOR = lxml_cssselect.CSSSelector("img.wp-post-image")
REVIEW_HEADER_SELECTOR = lxml_cssselect.CSSSelector("article.post header.entry-header div.entry-meta")
REVIEW_HEADER_DATE_REGEX = re.compile(r" on ([A-Z][a-z]+ \d+, [0-9]{4})")
PLAYER_IFRAME_SELECTOR = lxml_cssselect.CSSSelector("article.post iframe")
BANDCAMP_JS_SELECTOR = lxml_cssselect.CSSSelector("html > head > script[data-player-data]")
REVERBNATION_SCRIPT_SELECTOR = lxml_cssselect.CSSSelector("script")
REVIEW_FOOTER_SELECTOR = lxml_cssselect.CSSSelector("main.site-main article div.entry-content.clear > p")
RECORD_LABEL_REGEX = re.compile("Label: (.*)")
IS_TRAVIS = os.getenv("CI") and os.getenv("TRAVIS")
TCP_TIMEOUT = 30.1 if IS_TRAVIS else 15.1
YDL_MAX_DOWNLOAD_ATTEMPTS = 5
USER_AGENT = f"Mozilla/5.0 AMG-Player/{__version__}"
MAX_PARALLEL_DOWNLOADS = 4

PROXY = {protocol: os.getenv(f"{protocol}_proxy", "").replace("socks5h", "socks5") for protocol in ("http", "https")}


@contextlib.contextmanager
def date_locale_neutral():
    """Context manager to call with a neutral default locale."""
    loc = locale.getlocale(locale.LC_TIME)
    locale.setlocale(locale.LC_TIME, "C")
    try:
        yield
    finally:
        locale.setlocale(locale.LC_TIME, loc)


def fetch_page(url: str, *, http_cache: web_cache.WebCache | None = None) -> lxml_etree.XML:
    """Fetch page & parse it with LXML."""
    if (http_cache is not None) and (url in http_cache):
        logging.getLogger().info(f"Got data for URL {url!r} from cache")
        page = http_cache[url]
    else:
        page = fetch_ressource(url)
        if http_cache is not None:
            http_cache[url] = page
    return lxml_etree.XML(page.decode("utf-8"), HTML_PARSER)


def fetch_ressource(url: str) -> bytes:
    """Fetch ressource, and write it to file."""
    logging.getLogger().debug(f"Fetching {url!r}...")
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=TCP_TIMEOUT, proxies=PROXY)
    response.raise_for_status()
    return response.content


def parse_review_block(review: lxml_etree.Element) -> ReviewMetadata | None:
    """Parse review block from main page and return a ReviewMetadata object."""
    tags = tuple(
        t.split("-", 1)[1]
        for t in review.get("class").split(" ")
        if (t.startswith("tag-") and not t.startswith("tag-review") and not t.split("-", 1)[1].isdigit())
    )
    review_link = REVIEW_LINK_SELECTOR(review)[0]
    url = review_link.get("href")
    title = lxml_etree.tostring(review_link, encoding="unicode", method="text").strip()
    expected_suffix = " Review"
    expected_prefix = "AMG’s Unsigned Band Rodeo: "
    if title.endswith(expected_suffix):
        title = title[: len(title) - len(expected_suffix)]
    elif "[Things You Might Have Missed" in title:
        title = title.rsplit("[", 1)[0].strip()
    if title.startswith(expected_prefix):
        # https://www.angrymetalguy.com/amgs-unsigned-band-rodeo-beeldenstorm-herkoms/
        title = title[len(expected_prefix) :].strip()
    try:
        artist, album = map(str.strip, title.split("–", 1))
    except ValueError:
        # most likely not a review, ie. http://www.angrymetalguy.com/ep-edition-things-you-might-have-missed-2016/
        return None

    def make_absolute_url(url: str) -> str:
        url_parts = urllib.parse.urlsplit(url)
        if url_parts.scheme:
            return url
        url_parts = urllib.parse.SplitResult("https", *url_parts[1:])
        return urllib.parse.urlunsplit(url_parts)

    review_img = REVIEW_COVER_SELECTOR(review)[0]
    cover_thumbnail_url = make_absolute_url(review_img.get("src"))
    srcset = review_img.get("srcset")
    if srcset is not None:
        cover_url: str | None = make_absolute_url(srcset.split(" ")[-2])
    else:
        cover_url = None
    return ReviewMetadata(url, artist, album, cover_thumbnail_url, cover_url, tags)


def get_reviews() -> Iterable[ReviewMetadata]:
    """Parse site and yield ReviewMetadata objects."""
    previous_review = None
    for i in itertools.count():
        url = REVIEW_URL
        if i > 0:
            url += f"page/{i + 1}"
        page = fetch_page(url)
        for review in REVIEW_BLOCK_SELECTOR(page):
            r = parse_review_block(review)
            if (r is not None) and (r != previous_review):
                yield r
                previous_review = r


def get_embedded_track(page: lxml_etree.Element, http_cache: web_cache.WebCache) -> tuple[Sequence[str] | None, bool]:
    """Parse page and extract embedded track."""
    urls: Sequence[str] | None = None
    audio_only = False
    try:
        try:
            iframe = PLAYER_IFRAME_SELECTOR(page)[0]
        except IndexError:
            pass
        else:
            iframe_url = iframe.get("src")
            if iframe_url is not None:
                yt_prefixes = ("https://www.youtube.com/embed/", "https://www.youtube-nocookie.com/embed/")
                bc_prefixes = ("https://bandcamp.com/EmbeddedPlayer/", "http://bandcamp.com/EmbeddedPlayer/")
                sc_prefix = "https://w.soundcloud.com/player/"
                rn_prefix = "https://www.reverbnation.com/widget_code/"
                if any(map(iframe_url.startswith, yt_prefixes)):
                    yt_id = urllib.parse.urlparse(iframe_url).path.rsplit("/", 1)[-1]
                    if yt_id != "undefined":
                        urls = (f"https://www.youtube.com/watch?v={yt_id}",)
                elif any(map(iframe_url.startswith, bc_prefixes)):
                    iframe_page = fetch_page(iframe_url, http_cache=http_cache)
                    js = BANDCAMP_JS_SELECTOR(iframe_page)[0]
                    js = js.attrib["data-player-data"]
                    js = json.loads(js)
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
                            js = script.text[script.text.find(js_prefix) + len(js_prefix) :].splitlines()[0].rstrip(";")
                            js = json.loads(js)
                            break
                    url = js["PLAYLIST"][0]["url"]
                    url = urllib.parse.urlsplit(url)
                    url = ("https",) + url[1:]
                    url = urllib.parse.urlunsplit(url)
                    urls = (url,)
                    audio_only = True
    except Exception as e:
        logging.getLogger().error(f"{e.__class__.__qualname__}: {e}")
    if urls is not None:
        logging.getLogger().debug(f"Track URL(s): {' '.join(urls)}")
    return urls, audio_only


class KnownReviews:
    """Persistent state for reviews to track played tracks."""

    class DataIndex(enum.IntEnum):
        """Review metadata identifier."""

        LAST_PLAYED = 0
        PLAY_COUNT = 1
        DATA_INDEX_COUNT = 2

    def __init__(self):
        data_dir = platformdirs.user_data_dir("amg-player")
        os.makedirs(data_dir, exist_ok=True)
        filepath = Path(data_dir) / "played.dat"
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

    def isKnownUrl(self, url: str) -> bool:
        """Return True if url if from a known review, False instead."""
        return url in self.data

    def setLastPlayed(self, url: str) -> None:
        """Memorize a review's track has been read."""
        try:
            e = list(self.data[url])
        except KeyError:
            e = []
        if len(e) < self.DataIndex.DATA_INDEX_COUNT:
            e.extend(None for _ in range(self.DataIndex.DATA_INDEX_COUNT - len(e)))
        try:
            e[self.DataIndex.PLAY_COUNT] += 1
        except TypeError:
            # be compatible with when play count was not stored
            e[self.DataIndex.PLAY_COUNT] = 2 if e[self.DataIndex.LAST_PLAYED] is not None else 1
        e[self.DataIndex.LAST_PLAYED] = datetime.datetime.now()
        self.data[url] = tuple(e)

    def getLastPlayed(self, url: str) -> datetime.datetime:
        """Return datetime of last review track playback."""
        return self.data[url][self.DataIndex.LAST_PLAYED]

    def getPlayCount(self, url: str) -> int:
        """Return number of time a track has been played."""
        try:
            return self.data[url][self.DataIndex.PLAY_COUNT]
        except IndexError:
            # be compatible with when play count was not stored
            return 1


def get_cover_data(review: ReviewMetadata) -> bytes:
    """Fetch cover and return buffer of image data."""
    cover_url = review.cover_url if review.cover_url is not None else review.cover_thumbnail_url
    return fetch_ressource(cover_url)


def download_and_merge(
    review: ReviewMetadata, track_urls: Sequence[str], tmp_dir: str, cover_filepath: str
) -> str | None:
    """Download track, merge audio & album art, and return merged filepath."""
    # fetch audio
    with ytdl_tqdm.ytdl_tqdm(leave=False, mininterval=0.05, miniters=1) as ytdl_progress:
        # https://github.com/ytdl-org/youtube-dl/blob/b8b622fbebb158db95edb05a8cc248668194b430/youtube_dl/YoutubeDL.py#L143-L323
        ydl_opts = {
            "outtmpl": str(Path(tmp_dir) / r"%(autonumber)s.%(ext)s"),
            "proxy": PROXY["https"],
            "cookiesfrombrowser": ("firefox",),
        }
        if sys.stderr.isatty() and logging.getLogger().isEnabledFor(logging.INFO):
            ytdl_progress.setup_ytdl(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download(track_urls)
        except yt_dlp.utils.DownloadError as e:
            msg = f"Download error: {e}"
            if ytdl_progress:
                ytdl_progress.tqdm.write(msg)  # ty: ignore[unresolved-attribute]
            else:
                # already logged
                # logging.getLogger().warning(msg)
                pass
    audio_filepaths = os.listdir(tmp_dir)
    audio_filepaths.sort()
    if not audio_filepaths:
        logging.getLogger().error("Download failed")
        return None
    # merge
    merged_filepath = str(Path(tmp_dir) / "merged.mkv")
    with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".txt", mode="wt") as concat_file:
        for audio_filepath in audio_filepaths:
            concat_file.write(f"file {audio_filepath}\n")
        concat_file.flush()
        cmd = (
            "ffmpeg",
            "-loglevel",
            "quiet",
            "-loop",
            "1",
            "-framerate",
            "0.05",
            "-i",
            cover_filepath,
            "-f",
            "concat",
            "-i",
            concat_file.name,
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-filter:v",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:a",
            "copy",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-tune:v",
            "stillimage",
            "-preset",
            "ultrafast",
            "-shortest",
            "-f",
            "matroska",
            merged_filepath,
        )
        logging.getLogger().debug(f"Merging Audio and image with command: {shlex.join(cmd)}")
        subprocess.run(cmd, check=True, cwd=tmp_dir)

    return merged_filepath


def backslash_unescape(s: str) -> str:
    """Revert backslash escaping."""
    # https://stackoverflow.com/a/57192592
    return codecs.decode(codecs.encode(s, "latin-1", "backslashreplace"), "unicode-escape")


def download_track(
    review: ReviewMetadata,
    date_published: datetime.date,
    track_idx: int,
    track_url: str,
    tmp_dir: str,
    tqdm_line_lock: threading.Lock,
):
    """Download a single track, and return its metadata."""
    with contextlib.ExitStack() as cm:
        filename_template = (
            f"{date_published.strftime('%Y%m%d')}. "
            f"{pathvalidate.sanitize_filename(review.artist)} - "
            f"{pathvalidate.sanitize_filename(review.album)} - "
            f"{track_idx + 1:02d}."
            r"%(ext)s"
        )
        ydl_opts = {
            "outtmpl": str(Path(tmp_dir) / filename_template),
            "format": "opus/vorbis/bestaudio",
            "postprocessors": [{"key": "FFmpegExtractAudio"}],
            "proxy": PROXY[urllib.parse.urlsplit(track_url).scheme],
            "socket_timeout": TCP_TIMEOUT,
            "quiet": True,
            "logger": logging.getLogger(),
            "no_warnings": True,
        }
        if sys.stderr.isatty() and logging.getLogger().isEnabledFor(logging.INFO):
            cm.enter_context(tqdm_line_lock)
            ytdl_progress = cm.enter_context(
                ytdl_tqdm.ytdl_tqdm(leave=False, miniters=1, position=track_idx % MAX_PARALLEL_DOWNLOADS)
            )
            ytdl_progress.setup_ytdl(ydl_opts)
        else:
            ytdl_progress = None

        for attempt in range(1, YDL_MAX_DOWNLOAD_ATTEMPTS + 1):
            msg = (
                f"Downloading audio for track #{track_idx + 1} from {track_url!r} "
                f"(attempt {attempt}/{YDL_MAX_DOWNLOAD_ATTEMPTS})"
            )
            if ytdl_progress:
                ytdl_progress.tqdm.write(msg)  # ty: ignore[unresolved-attribute]
            else:
                logging.getLogger().info(msg)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    metadata = ydl.extract_info(track_url)
            except yt_dlp.utils.DownloadError as e:
                if e.exc_info is not None and isinstance(e.exc_info[1], (socket.gaierror, socket.timeout)):
                    continue
                raise
            return {
                k: backslash_unescape(metadata[k])
                for k in ("artist", "album", "title")
                if ((k in metadata) and metadata[k])
            }


def download_audio(
    review: ReviewMetadata,
    date_published: datetime.date,
    track_urls: Sequence[str],
    *,
    max_cover_size: int,
    record_label: str | None = None,
) -> bool:
    """Download audio track(s) to file(s) in current directory, return True if success."""
    with tempfile.TemporaryDirectory(prefix="amg_") as tmp_dir:
        # download
        tqdm_line_locks = [threading.Lock() for _ in range(MAX_PARALLEL_DOWNLOADS)]
        tracks_metadata = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOWNLOADS) as executor:
            futures = []
            for (track_idx, track_url), tqdm_line_lock in zip(enumerate(track_urls), itertools.cycle(tqdm_line_locks)):
                futures.append(
                    executor.submit(
                        download_track, review, date_published, track_idx, track_url, tmp_dir, tqdm_line_lock
                    )
                )

            # raise exception if any
            for future in futures:
                tracks_metadata.append(future.result())

        track_filepaths = tuple(sorted(str(p) for p in Path(tmp_dir).iterdir()))
        if not track_filepaths:
            logging.getLogger().error("Download failed")
            return False

        if not all(map(tag.has_embedded_album_art, track_filepaths)):
            # get cover
            cover_data: bytes | None = get_cover_data(review)
            assert cover_data is not None

            # post process cover
            in_bytes = io.BytesIO(cover_data)
            img = PIL.Image.open(in_bytes)
            if img.mode != "RGB":
                img = img.convert("RGB")
            # resize covers above threshold
            if (img.size[0] > max_cover_size) or (img.size[1] > max_cover_size):
                logging.getLogger().info("Resizing cover...")

                # resize
                img.thumbnail((max_cover_size, max_cover_size), PIL.Image.Resampling.LANCZOS)

                # apply unsharp filter to remove resize blur (equivalent to (images/graphics)magick -unsharp
                # 1.5x1+0.7+0.02)
                # we don't use PIL.ImageFilter.SHARPEN or PIL.ImageEnhance.Sharpness because we want precise control
                # over parameters
                unsharper = PIL.ImageFilter.UnsharpMask(radius=1.5, percent=70, threshold=5)
                img = img.filter(unsharper)

                # get bytes
                out_bytes = io.BytesIO()
                img.save(out_bytes, format="JPEG", quality=85, optimize=True)
                cover_data = out_bytes.getvalue()

        else:
            cover_data = None

        # add tags & embed cover
        files_tags = {}
        for track_filepath, track_metadata in zip(track_filepaths, tracks_metadata):
            try:
                files_tags[track_filepath] = tag.tag(track_filepath, review, track_metadata, cover_data, record_label)
            except Exception as e:
                # raise
                logging.getLogger().warning(
                    f"Failed to add tags to file {track_filepath!r}: {e.__class__.__qualname__} {e}"
                )

        # RG
        rsgain_cmd = ["rsgain", "custom", "-s", "i", "-o", "s"]
        if len(track_filepaths) > 1:
            rsgain_cmd.append("-a")
        rsgain_cmd.extend(track_filepaths)
        subprocess.run(rsgain_cmd, check=True)

        # move tracks
        cur_umask = os.umask(0)
        os.umask(cur_umask)
        for track_filepath in track_filepaths:
            dest_filename = Path(track_filepath).name
            # add title tag in filename if available
            try:
                file_tags = files_tags[track_filepath]
            except KeyError:
                pass
            else:
                p = Path(dest_filename)
                filename, ext = p.stem, p.suffix
                filename = ". ".join((filename, pathvalidate.sanitize_filename(file_tags["title"][-1])))
                if len(filename) > 128:
                    # actual limit (PATH_MAX) is much higher on Linux
                    # but we keep a large margin for directory path, extension
                    # and potential lower limits due to filesystem
                    filename = f"{filename[:128]}-"
                dest_filename = "".join((filename, ext))
            dest_dir = Path.cwd() / date_published.strftime("%Y-%m")
            os.makedirs(dest_dir, exist_ok=True)
            dest_filepath = dest_dir / dest_filename
            logging.getLogger().debug(f"Moving {repr(track_filepath)} to {repr(dest_filepath)}")
            shutil.move(track_filepath, dest_filepath)
            # restore sane perms fucked up by yt-dlp
            cur_mode = os.stat(dest_filepath).st_mode
            new_mode = cur_mode & ~cur_umask & ~0o111
            os.chmod(dest_filepath, new_mode)

        return True


def play(review: ReviewMetadata, track_urls: Sequence[str], *, merge_with_picture: bool) -> None:
    """Play it fucking loud."""
    # TODO support other players (vlc, avplay, ffplay...)
    merge_with_picture = merge_with_picture and HAS_FFMPEG
    if merge_with_picture:
        with tempfile.NamedTemporaryFile(prefix="amg_", delete_on_close=False) as cover_file:
            cover_data = get_cover_data(review)
            cover_file.write(cover_data)
            cover_file.close()
            cover_filepath = cover_file.name

            with tempfile.TemporaryDirectory(prefix="amg_") as tmp_dir:
                merged_filepath = download_and_merge(review, track_urls, tmp_dir, cover_filepath)
                if merged_filepath is None:
                    return None
                cmd: tuple[str, ...] = ("mpv", merged_filepath)
                logging.getLogger().debug(f"Playing with command: {shlex.join(cmd)}")
                subprocess.run(cmd, check=True)

    else:
        for track_url in track_urls:
            cmd_dl = ("yt-dlp", "-o", "-", track_url)
            logging.getLogger().debug(f"Downloading with command: {shlex.join(cmd_dl)}")
            dl_process = subprocess.Popen(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            cmd = ("mpv", "--force-seekable=yes", "-")
            logging.getLogger().debug(f"Playing with command: {shlex.join(cmd)}")
            subprocess.run(cmd, check=True, stdin=dl_process.stdout)


def cl_main():  # noqa: C901
    """Command line entry point."""
    # parse args
    arg_parser = argparse.ArgumentParser(
        description=f"AMG Player v{__version__}. {__doc__}", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    arg_parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=max(20, shutil.get_terminal_size()[1] - 7),
        dest="count",
        help="Amount of recent reviews to fetch",
    )
    arg_parser.add_argument(
        "-m",
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
                "discover_download" like "discover" but downloads tracks.""",
    )
    arg_parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        default=False,
        dest="interactive",
        help="Before playing each track, ask user confirmation, and allow opening review URL.",
    )
    arg_parser.add_argument(
        "-s",
        "--max-embedded-cover-size",
        type=int,
        default=1024,
        help="Maximum size of embedded cover art for downloaded tracks, above which image will be downsized.",
    )
    arg_parser.add_argument(
        "-v",
        "--verbosity",
        choices=("warning", "normal", "debug"),
        default="normal",
        dest="verbosity",
        help="Level of logging output",
    )
    args = arg_parser.parse_args()
    args.mode = PlayerMode[args.mode.upper()]

    # setup logger
    logger = logging.getLogger()
    logging_level = {"warning": logging.WARNING, "normal": logging.INFO, "debug": logging.DEBUG}
    logging.getLogger().setLevel(logging_level[args.verbosity])
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("PIL").setLevel(logging.ERROR)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging_formatter = colorlog.ColoredFormatter(fmt="%(log_color)s%(threadName)s: %(message)s")
    else:
        logging_formatter = colorlog.ColoredFormatter(fmt="%(log_color)s%(message)s")
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
    cache_dir = platformdirs.user_cache_dir("amg-player")
    os.makedirs(cache_dir, exist_ok=True)
    cache_filepath = Path(cache_dir) / "http_cache.db"
    http_cache = web_cache.WebCache(
        cache_filepath,
        "reviews",
        caching_strategy=web_cache.CachingStrategy.FIFO,
        expiration=60 * 60 * 24 * 30 * 3,  # 3 months
        compression=web_cache.Compression.DEFLATE,
    )
    purged_count = http_cache.purge()
    row_count = len(http_cache)
    logging.getLogger().debug(f"HTTP Cache contains {row_count} entries ({purged_count} removed)")

    # initial menu
    if args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO):
        menu_ret = menu.AmgMenu.setupAndShow(args.mode, reviews, known_reviews, http_cache)

    to_play = None
    track_loop = True
    while track_loop:
        if args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO):
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
                to_play = reviews[0 : reviews.index(review) + 1]
                to_play.reverse()
                to_play = iter(to_play)
        elif args.mode in (PlayerMode.DISCOVER, PlayerMode.DISCOVER_DOWNLOAD):
            # auto play all non played tracks
            if to_play is None:
                to_play = filter(lambda x: not known_reviews.isKnownUrl(x.url), reversed(reviews))
        if args.mode in (PlayerMode.RADIO, PlayerMode.DISCOVER, PlayerMode.DISCOVER_DOWNLOAD):
            assert to_play is not None
            try:
                review = next(to_play)
            except StopIteration:
                break

        # fetch review & play
        review_page = fetch_page(review.url, http_cache=http_cache)
        header = REVIEW_HEADER_SELECTOR(review_page)[0]
        date_published = lxml_etree.tostring(header, encoding="unicode", method="text").strip()
        date_published_match = REVIEW_HEADER_DATE_REGEX.search(date_published)
        assert date_published_match is not None
        date_published = date_published_match.group(1)
        with date_locale_neutral():
            date_published = datetime.datetime.strptime(date_published, "%B %d, %Y").date()
        try:
            footer_elem = REVIEW_FOOTER_SELECTOR(review_page)[-1]
        except IndexError:
            record_label = None
        else:
            footer_str = lxml_etree.tostring(footer_elem, encoding="unicode", method="text").strip()
            record_label_match = RECORD_LABEL_REGEX.search(footer_str)
            if record_label_match is not None:
                record_label = record_label_match.group(1)
            else:
                record_label = None
        track_urls, audio_only = get_embedded_track(review_page, http_cache)
        if track_urls is None:
            logging.getLogger().warning("Unable to extract embedded track")
        else:
            print("-" * (shutil.get_terminal_size()[0] - 1))
            print(
                f"Artist: {review.artist}\n"
                f"Album: {review.album}\n"
                f"Review URL: {review.url}\n"
                f"Published: {date_published.strftime('%x %H:%M')}\n"
                f"Tags: {', '.join(review.tags)}"
            )
            if args.interactive:
                input_loop = True
                while input_loop:
                    c = None
                    while c not in frozenset("pdrsq"):
                        c = input("[P]lay / [D]ownload / Go to [R]eview / [S]kip to next track / Exit [Q] ? ").lower()
                    if c == "p":
                        play(review, track_urls, merge_with_picture=audio_only)
                        known_reviews.setLastPlayed(review.url)
                        input_loop = False
                    elif c == "d":
                        download_audio(
                            review,
                            date_published,
                            track_urls,
                            max_cover_size=args.max_embedded_cover_size,
                            record_label=record_label,
                        )
                        input_loop = False
                    elif c == "r":
                        webbrowser.open_new_tab(review.url)
                    elif c == "s":
                        input_loop = False
                    elif c == "q":
                        input_loop = False
                        track_loop = False
            else:
                if (
                    (args.mode in (PlayerMode.MANUAL, PlayerMode.RADIO))
                    and (action is menu.AmgMenu.UserAction.DOWNLOAD_AUDIO)
                ) or (args.mode is PlayerMode.DISCOVER_DOWNLOAD):
                    try:
                        download_audio(
                            review,
                            date_published,
                            track_urls,
                            max_cover_size=args.max_embedded_cover_size,
                            record_label=record_label,
                        )
                    except yt_dlp.DownloadError as e:
                        if args.mode is PlayerMode.DISCOVER_DOWNLOAD:
                            logging.getLogger().exception(
                                f"Failed download {track_urls!r}: {e.__class__.__qualname__} {e}"
                            )
                        else:
                            raise
                else:
                    play(review, track_urls, merge_with_picture=audio_only)
                known_reviews.setLastPlayed(review.url)

        if track_loop and (args.mode is PlayerMode.MANUAL):
            # update menu and display it
            menu_ret = menu.AmgMenu.setupAndShow(
                args.mode, reviews, known_reviews, http_cache, selected_idx=selected_idx
            )


if __name__ == "__main__":
    cl_main()
