"""Audio tag handling code."""

import base64
import calendar
import datetime
import functools
import io
import itertools
import logging
import operator
import re
import string
from collections.abc import Callable, Sequence
from pathlib import Path

import magic
import more_itertools
import mutagen
import mutagen.easymp4
import mutagen.flac
import mutagen.id3
import mutagen.mp3
import mutagen.mp4
import mutagen.ogg
import PIL.Image
import unidecode

from amg import sanitize


# What was once a small concise function has grown into the largest part of this project.
# This chains many checks to remove crap from title tags, because record people do not have conventions or
# common sense for that matter, and often try to stuff their grocery list and the name of their cat into
# what should be a simple title for the song.


# copy month names before changing locale
MONTH_NAMES = calendar.month_name[1:]
MONTH_NAMES_ABBR = calendar.month_abbr[1:]


Cleaner = Callable[[str], str]

RCLEAN_CHARS = "".join(c for c in (string.punctuation + string.whitespace) if c not in "!?)-]")
LCLEAN_CHARS = "".join(c for c in (string.punctuation + string.whitespace) if c not in "(")
SEP_CHARS = string.punctuation + string.whitespace


@functools.cache
def re_compile(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern:
    return re.compile(pattern, flags)


def rnorm(s: str) -> str:
    return unidecode.unidecode_expect_ascii(s.rstrip(string.punctuation)).rstrip(string.punctuation).lower()


def lnorm(s: str) -> str:
    return unidecode.unidecode_expect_ascii(s.lstrip(string.punctuation)).lstrip(string.punctuation).lower()


@functools.cache
def useless_expressions() -> tuple[str, ...]:
    expressions: set[str] = set()
    words1 = ("", "explicit", "full", "including", "new", "official", "stop motion", "the new")
    words2 = (
        "",
        "360",
        "album",
        "album/tour",
        "audio",
        "game",
        "lyric",
        "lyrics",
        "music",
        "promo",
        "single",
        "song",
        "stream",
        "studio",
        "track",
        "video",
        "visual",
    )
    words3 = (
        "4k",
        "album",
        "audio",
        "clip",
        "discovery",
        "edit",
        "excerpt",
        "hq",
        "in 4k",
        "lyric",
        "lyrics",
        "only",
        "premier",
        "premiere",
        "presentation",
        "promo",
        "single",
        "song",
        "stream",
        "streaming",
        "teaser",
        "track",
        "trailer",
        "version",
        "video",
        "visualiser",
        "visualizer",
        "vr",
    )
    for w1 in words1:
        for w2 in words2:
            for w3 in words3:
                if w3 != w2:
                    if w1 or w2:
                        for rsep in (" ", "-", ""):
                            rpart = rsep.join((w2, w3)).strip()
                            expressions.add(" ".join((w1, rpart)).strip())
                    else:
                        expressions.add(w3)
    expressions.update(
        (
            "full ep",
            "full-length",
            "hd",
            "official",
            "offical",
            "oficial",
            "pre-listening",
            "pre-order now",
            "pre-orders available",
            "prelistening",
            "preorders available",
            "s/t",
            "sw exclusive",
            "trailer for the upcoming album",
            "transcending obscurity",
            "transcending obscurity india",
            "trollzorn",
            "uncensored",
        )
    )
    year = datetime.datetime.today().year
    for y in range(2016, year + 1):
        expressions.add(str(y))
        for month_name, month_abbr, month_roman in zip(
            MONTH_NAMES,
            MONTH_NAMES_ABBR,
            ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"),
        ):
            expressions.add(f"{month_name} {y}")
            expressions.add(f"{month_abbr} {y}")
            expressions.add(f"{y} {month_roman}")
    expressions_list = sorted(expressions, key=lambda e: len(e), reverse=True)
    expressions_list.remove("song")
    return tuple(expressions_list)


@functools.cache
def metal_genre_groups() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    base_genres = [
        "crust",
        "black",
        "death",
        "doom",
        "grind",
        "grindcore",
        "progressive",
        "sci-fi",
        "thrash",
    ]
    composed_genres = tuple(
        genre_sep.join(pair) for pair in itertools.permutations(base_genres, 2) for genre_sep in "/- "
    )
    metal_genres = tuple(f"{genre} metal" for genre in tuple(base_genres) + composed_genres)
    base_genres.append("metal")
    for too_common_word in ("black", "death", "thrash"):
        base_genres.remove(too_common_word)
    return metal_genres, composed_genres, tuple(base_genres)


def build_pipeline(artist: str, album: str, record_label: str | None) -> list[Cleaner]:
    """Assemble the ordered list of title-cleaning callables."""
    metal_genres, composed_genres, base_genres = metal_genre_groups()
    cleaners: list[Cleaner] = [
        # remove consecutive spaces
        lambda x: " ".join(x.split()),
        # detect and remove '#hashtag' suffix
        regex_suffix_cleaner(r"(#[\w]+ ?)+"),
        # detect and remove 'taken from album xxx, out (on) yyy' suffix
        regex_suffix_cleaner("taken from .+, out "),
        # detect and remove 'a track of the upcoming xxx' suffix
        regex_suffix_cleaner("a track of upcoming "),
        # detect and remove 'episode x/y of' suffix
        regex_suffix_cleaner("episode [0-9/]+( of)"),
        # detect and remove 'album: xxx track yy'
        regex_cleaner("(album: .+ )?track [0-9]+"),
        # detect and remove 'from xxx LP' suffix
        regex_suffix_cleaner("(taken )?from .+ LP"),
        # detect and remove 'from xxx album' suffix
        regex_suffix_cleaner("(taken )?from .*album"),
        # detect and remove 'xxx out: yy.zz.aa' suffix
        regex_suffix_cleaner(r" [\[\(]?([^ ]+ out: )?[0-9]+\.[0-9]+\.[0-9]+[\]\)]?"),
        # detect and remove 'out yy.zz' suffix
        regex_suffix_cleaner(" out [0-9]+/[0-9]+"),
        # detect and remove 'out month xxth' suffix
        regex_suffix_cleaner(" out [a-z]+ [0-9]+th"),
        # detect and remove 'new album out xxx' suffix
        regex_suffix_cleaner("new album out .*$"),
        # detect and remove '[xxx music]' suffix
        regex_suffix_cleaner(r"[\[\( ][a-z]+ music$", suffixes=("music",)),
        # detect and remove 'xxx entertainment' suffix
        regex_suffix_cleaner(r"[\[\( ][a-z]+ entertainment$", suffixes=("entertainment",)),
        # detect and remove 'record label xxx' suffix
        regex_suffix_cleaner("record label:? [a-z0-9 ]+$"),
        # detect and remove 'next concert: xxx' suffix
        regex_suffix_cleaner("next concert: .+$"),
        # detect and remove 'feat.xxx' suffix
        regex_suffix_cleaner(r"feat\..+$"),
        # detect and remove 'ft. xxx'
        regex_cleaner(r"[\(\[ ]+ft\. [a-zA-Z\.\: ]+[\)\]]?"),
        # detect and remove '(xxx productions)'
        regex_cleaner(r"[^\w\s].+ productions?[^\w\s]"),
        # detect and remove 'xxx productions' prefix
        regex_prefix_cleaner(r"^[\w\s]+ productions?"),
    ]
    # detect and remove record label suffix
    if record_label is not None:
        cleaners.append(simple_suffix_cleaner(record_label))
    # detect and remove '- xxx metal' suffix
    for genre in metal_genres + composed_genres + base_genres:
        cleaners.append(
            regex_suffix_cleaner(
                r"[|\(\[/\] -]+(?:[0-9a-z/-\\,]+[ ]*)*" + genre + "( song)?$",
                suffixes=(genre, f"{genre} song"),
            )
        )
    # detect and remove '(thrash/death from whatever)' suffix
    for genre in metal_genres + composed_genres + base_genres:
        cleaners.append(regex_suffix_cleaner(r"[|\(\[/]+[ ]*" + genre + r" from [a-zA-Z-, ]+[\)\]]?$"))
    cleaners.extend(
        [
            # detect and remove 'xxx metal' prefix
            expressions_prefix_cleaner(metal_genres + composed_genres),
            # detect and remove 'xxx productions' suffix
            regex_suffix_cleaner(r"[\[\( ][a-z ]+ productions$", suffixes=(" productions",)),
            # detect and remove track number prefix
            regex_prefix_cleaner("^[0-9]+[ -.]+"),
            # detect and remove 'xxx records' suffix
            records_suffix_cleaner("recordings"),
            records_suffix_cleaner("records"),
            # detect and remove ' | xxx' suffixes
            regex_suffix_cleaner(r" \| .*$", suffixes=" | "),
            # detect and remove common useless expressions as prefix or suffix
            expressions_suffix_cleaner(useless_expressions()),
            expressions_prefix_cleaner(useless_expressions()),
            # detect and remove artist prefix or suffix
            artist_cleaner(artist),
            # detect and remove starting parenthesis expression
            start_parens_cleaner(),
            # detect and remove album prefix or suffix
            album_cleaner(album),
            # fix paired chars
            paired_char_cleaner(),
            # remove some punctuation
            lambda x: x.strip("-"),
            # normalize case
            sanitize.normalize_tag_case,
            # post normalize case fix
            lambda x: x.replace("PT.", "pt."),
        ]
    )
    return cleaners


def run_pipeline(title: str, cleaners: list[Cleaner]) -> str:
    """Run the cleaners until a fixed point is reached."""
    cur_title = title
    for _ in range(64):
        for cleaner in cleaners:
            new_title = cleaner(cur_title)
            if new_title and (new_title != cur_title):
                logging.getLogger().debug(
                    f"{getattr(cleaner, '__qualname__', cleaner)} changed title tag: {cur_title!r} -> {new_title!r}"
                )
                cur_title = new_title
                break
        else:
            break

    if cur_title != title:
        logging.getLogger().info(f"Fixed title tag: {title!r} -> {cur_title!r}")
    return cur_title


def rclean(s: str) -> str:
    """Remove garbage at right of string."""
    r = s.rstrip(RCLEAN_CHARS)
    if r.endswith(" -"):
        r = r[:-2].rstrip(RCLEAN_CHARS)
    return r


def lclean(s: str) -> str:
    """Remove garbage at left of string."""
    r = s.lstrip(LCLEAN_CHARS)
    c = unidecode.unidecode_expect_ascii(r.lstrip(LCLEAN_CHARS)).lstrip(LCLEAN_CHARS)
    if c != r:
        r = c
    return r


def startslike(s: str, pattern: str, *, sep: str | None = None) -> bool:
    """Return True if start of string s is similar to pattern."""
    s = lnorm(s)
    pattern = rnorm(pattern)
    cut = s[len(pattern) :]
    return s.startswith(pattern) and ((not sep) or (not cut) or (cut[0] in sep))


def endslike(s: str, pattern: str) -> bool:
    """Return True if end of string s is similar to pattern."""
    return rnorm(s).endswith(rnorm(pattern))


def rmsuffix(s: str, e: str) -> str:
    """Remove string suffix."""
    return s.rstrip(string.punctuation)[: -len(unidecode.unidecode_expect_ascii(e))]


def rmprefix(s: str, e: str) -> str:
    """Remove string prefix."""
    return s.lstrip(string.punctuation)[len(unidecode.unidecode_expect_ascii(e)) :]


def strip_prefix(title: str, prefix: str) -> str:
    if startslike(title, prefix, sep=SEP_CHARS):
        return lclean(rmprefix(title, prefix))
    return title


def strip_suffix(title: str, suffix: str) -> str:
    if endslike(title, suffix):
        new = rclean(rmsuffix(title, suffix))
        if new.lower() != "the":
            return new
    return title


def simple_suffix_cleaner(suffix: str) -> Cleaner:
    return lambda title: strip_suffix(title, suffix)


def regex_cleaner(pattern: str) -> Cleaner:
    regex = re_compile(pattern)

    def cleaner(title: str) -> str:
        rstripped = title.rstrip(string.punctuation)
        m = regex.search(rstripped)
        if m:
            return f"{rclean(rstripped[: m.start(0)])} {lclean(rstripped[m.end(0) :])}".rstrip()
        return title

    return cleaner


def regex_suffix_cleaner(pattern: str, *, suffixes: Sequence[str] = ()) -> Cleaner:
    regex = re_compile(pattern)

    def cleaner(title: str) -> str:
        if suffixes and not any(endslike(title, s) for s in suffixes):
            return title
        m = regex.search(title.rstrip(string.punctuation))
        if m:
            return rclean(title[: m.start(0)])
        return title

    return cleaner


def regex_prefix_cleaner(pattern: str) -> Cleaner:
    regex = re_compile(pattern)

    def cleaner(title: str) -> str:
        m = regex.search(title)
        if m:
            return lclean(title[m.end(0) :])
        return title

    return cleaner


def records_suffix_cleaner(record_word: str) -> Cleaner:
    regex = re_compile(r"([|\)\(\[]|on)[0-9a-z,/ ]+" + record_word + "$")

    def cleaner(title: str) -> str:
        if not endslike(title, record_word):
            return title
        m = regex.search(title.rstrip(string.punctuation))
        if m:
            return rclean(title[: m.start(0)])
        title = strip_suffix(title, record_word)
        return rclean(" ".join(title.split()[:-1]))

    return cleaner


def expressions_suffix_cleaner(expressions: Sequence[str]) -> Cleaner:
    entries: dict[str, int] = {}
    for e in expressions:
        e_norm = rnorm(e)
        if e_norm:
            entries[e_norm] = len(unidecode.unidecode_expect_ascii(e))
    ordered = sorted(entries, key=lambda e: len(e), reverse=True)
    regex = re_compile("(?:" + "|".join(re.escape(e) for e in ordered) + ")$", 0)

    def cleaner(title: str) -> str:
        while True:
            m = regex.search(rnorm(title))
            if not m:
                return title
            rm_len = entries.get(m.group(0))
            if rm_len is None:
                return title
            new = rclean(title.rstrip(string.punctuation)[:-rm_len])
            if (not new) or new.lower() == "the":
                return title
            title = new

    return cleaner


def expressions_prefix_cleaner(expressions: Sequence[str]) -> Cleaner:
    entries: dict[str, int] = {}
    for e in expressions:
        e_norm = rnorm(e)
        if e_norm:
            entries[e_norm] = len(unidecode.unidecode_expect_ascii(e))
    ordered = sorted(entries, key=lambda e: len(e), reverse=True)
    sep_class = re.escape(SEP_CHARS)
    regex = re_compile("^(?P<e>" + "|".join(re.escape(e) for e in ordered) + ")(?:[" + sep_class + r"]|$)", 0)

    def cleaner(title: str) -> str:
        while True:
            m = regex.match(lnorm(title))
            if not m:
                return title
            rm_len = entries.get(m.group("e"))
            if rm_len is None:
                return title
            new = lclean(title.lstrip(string.punctuation)[rm_len:])
            if not new:
                return title
            title = new

    return cleaner


def artist_cleaner(artist: str) -> Cleaner:
    variants = tuple(
        more_itertools.unique_everseen(
            (
                f"{artist} band",
                artist,
                artist.replace(" ", ""),
                artist.replace("and", "&"),
                artist.replace("&", "and"),
                artist.replace(", ", " and "),
                artist.replace(" and ", ", "),
                artist.replace("’", ""),
            )
        )
    )
    by_artist = "by " + artist
    state = [False, False]  # prefix_removed, suffix_removed

    def cleaner(title: str) -> str:
        for s_raw, suffix_only in itertools.zip_longest((by_artist,) + variants, (True,), fillvalue=False):
            assert isinstance(s_raw, str)
            s = s_raw
            if (not suffix_only) and (not state[0]) and startslike(title, s):
                state[0] = True
                return strip_prefix(title, s)
            if (not state[1]) and endslike(title, s):
                state[1] = True
                return strip_suffix(title, s)
        return title

    return cleaner


def album_cleaner(album: str) -> Cleaner:
    inner_suffixes = ("taken from", "from the album", "from")

    def cleaner(title: str) -> str:
        if startslike(title, album):
            return strip_prefix(title, album)
        if endslike(title, album):
            title = strip_suffix(title, album)
            for s in inner_suffixes:
                if endslike(title, s):
                    new = strip_suffix(title, s)
                    if new:
                        title = new
                        break
        return title

    return cleaner


def start_parens_cleaner() -> Cleaner:
    def cleaner(title: str) -> str:
        closing_pos = title.find(")")
        if title.startswith("(") and (closing_pos != (len(title) - 1)) and (len(title[1:closing_pos]) > 1):
            return lclean(title[closing_pos + 1 :])
        return title

    return cleaner


def paired_char_cleaner() -> Cleaner:
    char_pairs = ((("(", ")"), False), (('"', '"'), False), (("'", "'"), True))

    def cleaner(title: str) -> str:
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
        if title.startswith("(") and title.endswith(")"):
            title = title[1:-1]
        return title

    return cleaner


def normalize_title_tag(title: str, artist: str, album: str, record_label: str | None = None) -> str:
    """Remove useless prefix and suffix from title tag string."""
    return run_pipeline(title, build_pipeline(artist, album, record_label))


def tag(
    track_filepath: str | Path,
    review,
    metadata: dict[str, str],
    cover_data: bytes | None,
    record_label: str | None = None,
):
    """Tag an audio file, return tag dict excluding RG/R128 info and album art."""
    logging.getLogger().info(f"Tagging file {track_filepath!r}")
    mf = mutagen.File(track_filepath, easy=True)

    # sanitize tags
    mf["artist"] = sanitize.normalize_tag_case(review.artist)
    mf["album"] = sanitize.normalize_tag_case(review.album)
    try:
        mf["title"] = normalize_title_tag(metadata["title"], review.artist, review.album, record_label)
    except KeyError:
        mf["title"] = mf["album"]
    try:
        mf["comment"] = metadata["description"]
    except KeyError:
        pass
    tags = dict(mf)

    if cover_data is not None:
        if isinstance(mf, mutagen.mp3.EasyMP3) or isinstance(mf, mutagen.easymp4.EasyMP4):
            # EasyXXX helpers do not allow embedding album art, reopen as normal mutagen file
            mf.save()
            mf = mutagen.File(track_filepath)

        # embed album art
        embed_album_art(mf, cover_data)

    mf.save()

    return tags


def has_embedded_album_art(filepath: str | Path) -> bool:
    """Return True if file already has an embedded album art, False instead."""
    mf = mutagen.File(filepath)
    if isinstance(mf, mutagen.ogg.OggFileType):
        return "metadata_block_picture" in mf
    elif isinstance(mf, mutagen.mp3.MP3):
        return any(map(operator.methodcaller("startswith", "APIC:"), mf.keys()))
    elif isinstance(mf, mutagen.mp4.MP4):
        return "covr" in mf
    return False


def embed_album_art(mf: mutagen.File, cover_data: bytes):
    """Embed album art into audio file."""
    mime = magic.from_buffer(cover_data, mime=True)
    if isinstance(mf, mutagen.ogg.OggFileType):
        picture = mutagen.flac.Picture()
        picture.data = cover_data
        picture.type = mutagen.id3.PictureType.COVER_FRONT
        picture.mime = mime
        encoded_data = base64.b64encode(picture.write())
        mf["metadata_block_picture"] = encoded_data.decode("ascii")
    elif isinstance(mf, mutagen.mp3.MP3):
        mf.tags.add(mutagen.id3.APIC(mime=mime, type=mutagen.id3.PictureType.COVER_FRONT, data=cover_data))
        mf.save()
    elif isinstance(mf, mutagen.mp4.MP4):
        if mime == "image/jpeg":
            fmt = mutagen.mp4.AtomDataType.JPEG
        elif mime == "image/png":
            fmt = mutagen.mp4.AtomDataType.PNG
        else:
            # convert to jpeg
            in_bytes = io.BytesIO(cover_data)
            img = PIL.Image.open(in_bytes)
            out_bytes = io.BytesIO()
            img.save(out_bytes, format="JPEG", quality=85, optimize=True)
            cover_data = out_bytes.getvalue()
            fmt = mutagen.mp4.AtomDataType.JPEG
        mf["covr"] = [mutagen.mp4.MP4Cover(cover_data, imageformat=fmt)]
