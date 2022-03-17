""" Audio tag handling code. """

import abc
import base64
import calendar
import collections
import datetime
import functools
import itertools
import logging
import operator
import re
import string
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import more_itertools
import mutagen
import unidecode

from amg import sanitize


class TitleNormalizer:

    """
    Class to chain all title tag transformations.

    What was once a small concise function has grown into the largest part of this project.
    This chains many checks to remove crap from title tags, because record people do not have conventions or
    common sense for that matter, and often try to stuff their grocery list and the name of their cat into
    what should be a simple title for the song.
    """

    def __init__(self, artist: str, album: str):  # noqa: C901
        self.cleaners: List[Tuple[TitleCleanerBase, Tuple[Any]]] = []

        # TODO separate cleaner from params and copy/reuse cleaners in TitleNormalizer.cleanup

        # remove consecutive spaces
        self.registerCleaner(FunctionCleaner(lambda x: " ".join(x.split()), execute_once=True))

        # detect and remove '#hashtag' suffix
        self.registerCleaner(RegexSuffixCleaner(r"(#[\w]+ ?)+", contains=("#"), execute_once=True))

        # detect and remove 'taken from album xxx, out (on) yyy' suffix
        self.registerCleaner(
            RegexSuffixCleaner("taken from .+, out ", contains=("taken from", "out"), execute_once=True)
        )

        # detect and remove 'a track of the upcoming xxx' suffix
        self.registerCleaner(
            RegexSuffixCleaner("a track of upcoming ", contains=("a track of upcoming"), execute_once=True)
        )

        # detect and remove 'album: xxx track yy'
        self.registerCleaner(RegexCleaner("(album: .+ )?track [0-9]+", contains=("track",), execute_once=True))

        # detect and remove 'from xxx LP' suffix
        self.registerCleaner(RegexSuffixCleaner("from .+ LP", contains=("from", "LP"), execute_once=True))

        # detect and remove 'from xxx album' suffix
        self.registerCleaner(RegexSuffixCleaner("from .*album", contains=("from", "album"), execute_once=True))

        # detect and remove 'xxx out: yy.zz.aa' suffix
        self.registerCleaner(
            RegexSuffixCleaner(r" [\[\(]?([^ ]+ out: )?[0-9]+\.[0-9]+\.[0-9]+[\]\)]?", execute_once=True)
        )

        # detect and remove 'out yy.zz' suffix
        self.registerCleaner(RegexSuffixCleaner(" out [0-9]+/[0-9]+", contains=(" out ",), execute_once=True))

        # detect and remove 'out month xxth' suffix
        self.registerCleaner(RegexSuffixCleaner(" out [a-z]+ [0-9]+th", contains=(" out ",), execute_once=True))

        # detect and remove 'new album out xxx' suffix
        self.registerCleaner(RegexSuffixCleaner("new album out .*$", contains=("new album out ",), execute_once=True))

        # detect and remove '[xxx music]' suffix
        self.registerCleaner(RegexSuffixCleaner(r"[\[\( ][a-z]+ music$", suffixes=("music",), execute_once=True))

        # detect and remove 'xxx entertainment' suffix
        self.registerCleaner(
            RegexSuffixCleaner(r"[\[\( ][a-z]+ entertainment$", suffixes=("entertainment",), execute_once=True)
        )

        # detect and remove 'record label xxx' suffix
        self.registerCleaner(
            RegexSuffixCleaner("record label:? [a-z0-9 ]+$", contains=("record label",), execute_once=True)
        )

        # detect and remove 'next concert: xxx' suffix
        self.registerCleaner(RegexSuffixCleaner("next concert: .+$", contains=("next concert: ",), execute_once=True))

        # detect and remove 'feat.xxx' suffix
        self.registerCleaner(RegexSuffixCleaner(r"feat\..+$", contains=("feat.",), execute_once=True))

        # detect and remove 'ft. xxx'
        self.registerCleaner(RegexCleaner(r"[\(\[ ]+ft\. [a-zA-Z\.\: ]+[\)\]]?", contains=("ft.",), execute_once=True))

        # detect and remove '(xxx productions)'
        self.registerCleaner(
            RegexCleaner(r"[^\w\s].+ productions?[^\w\s]", contains=("production",), execute_once=True)
        )

        # detect and remove 'xxx productions' prefix
        self.registerCleaner(RegexPrefixCleaner(r"^[\w\s]+ productions?", contains=("production",), execute_once=True))

        # detect and remove '- xxx metal' suffix
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
        for genre in metal_genres + composed_genres + tuple(base_genres):
            self.registerCleaner(
                RegexSuffixCleaner(
                    r"[|\(\[/\]\)-]+[ ]*(?:[0-9a-z/-]+[ ]*)*" + genre + "( song)?$",
                    suffixes=(genre, f"{genre} song"),
                    execute_once=True,
                    remove_if_skipped=False,
                )
            )

        # detect and remove '(thrash/death from whatever)' suffix
        for genre in metal_genres + composed_genres + tuple(base_genres):
            self.registerCleaner(
                RegexSuffixCleaner(
                    r"[|\(\[/]+[ ]*" + genre + r" from [a-zA-Z-, ]+[\)\]]?$",
                    contains=(f"{genre} from ",),
                    execute_once=True,
                )
            )

        # detect and remove 'xxx metal' prefix
        for genre in metal_genres + composed_genres:
            self.registerCleaner(SimplePrefixCleaner(execute_once=True), (genre,))

        # detect and remove 'xxx productions' suffix
        self.registerCleaner(RegexSuffixCleaner(r"[\[\( ][a-z ]+ productions$", suffixes=(" productions",)))

        # detect and remove track number prefix
        self.registerCleaner(RegexPrefixCleaner("^[0-9]+[ -.]+"))

        # detect and remove 'xxx records' suffix
        self.registerCleaner(RecordsSuffixCleaner("recordings"))
        self.registerCleaner(RecordsSuffixCleaner("records"))

        # detect and remove ' | xxx' suffixes
        self.registerCleaner(RegexSuffixCleaner(r" \| .*$", suffixes=" | ", execute_once=True))

        # build list of common useless expressions
        expressions = set()
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
            for month_name, month_abbr in zip(MONTH_NAMES, MONTH_NAMES_ABBR):
                expressions.add(f"{month_name} {y}")
                expressions.add(f"{month_abbr} {y}")
        expressions_list = list(sorted(expressions, key=len, reverse=True))
        expressions_list.remove("song")
        suffix_cleaner = SimpleSuffixCleaner()
        for expression in expressions_list:
            self.registerCleaner(suffix_cleaner, (expression,))
        prefix_cleaner = SimplePrefixCleaner()
        for expression in expressions_list:
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
        """Register a new cleaner object."""
        assert isinstance(cleaner, TitleCleanerBase)
        self.cleaners.append((cleaner, args))

    def cleanup(self, title: str) -> str:
        """Do the string cleanup by running all cleaners."""
        cur_title = title
        to_del_indexes: Deque[int] = collections.deque()
        start_index = 0

        while self.cleaners:

            cleaner: TitleCleanerBase
            for i, (cleaner, args) in enumerate(itertools.islice(self.cleaners, start_index, None), start_index):

                remove_cur_cleaner = False
                restart_loop = False

                if cleaner.doSkip(cur_title, *args):
                    if cleaner.remove_if_skipped and not cleaner.doKeep():
                        remove_cur_cleaner = True

                else:
                    new_title = cleaner.cleanup(cur_title, *args)
                    if new_title and (new_title != cur_title):
                        logging.getLogger().debug(
                            f"{cleaner.__class__.__name__} changed title tag: "
                            f"{repr(cur_title)} -> {repr(new_title)}"
                        )
                        # update string and remove this cleaner to avoid calling it several times
                        cur_title = new_title
                        remove_cur_cleaner = not cleaner.doKeep()
                        restart_loop = True

                    elif cleaner.execute_once:
                        remove_cur_cleaner = True
                        # this cleaner did not match and we will remove it, continue from same index
                        if start_index == 0:
                            start_index = i

                if remove_cur_cleaner:
                    to_del_indexes.append(i)
                if restart_loop:
                    start_index = 0
                    break

            else:
                # all cleaners have been called and string did not change title
                break

            while to_del_indexes:
                del self.cleaners[to_del_indexes.pop()]

        if cur_title != title:
            logging.getLogger().info(f"Fixed title tag: {repr(title)} -> {repr(cur_title)}")
        return cur_title


class TitleCleanerBase:

    """Base class for all title cleaner subclasses."""

    RCLEAN_CHARS = "".join(c for c in (string.punctuation + string.whitespace) if c not in "!?)-]")
    LCLEAN_CHARS = "".join(c for c in (string.punctuation + string.whitespace) if c not in "(")

    def __init__(self, *, execute_once: bool = False, remove_if_skipped: bool = None):
        self.execute_once = execute_once
        self.remove_if_skipped = remove_if_skipped if (remove_if_skipped is not None) else execute_once

    def doSkip(self, title: str, *args) -> bool:
        """Return True if this cleaner can be skipped for this title string."""
        return False

    def doKeep(self) -> bool:
        """Return True if this cleaner should not be removed even if it matched."""
        return False

    @abc.abstractmethod
    def cleanup(self, title: str, *args: Tuple[Any]) -> str:
        """Cleanup a title string, and return the updated string."""
        pass

    def rclean(self, s: str) -> str:
        """Remove garbage at right of string."""
        r = s.rstrip(self.__class__.RCLEAN_CHARS)
        if r.endswith(" -"):
            r = r[:-2].rstrip(self.__class__.RCLEAN_CHARS)
        return r

    def lclean(self, s: str) -> str:
        """Remove garbage at left of string."""
        r = s.lstrip(self.__class__.LCLEAN_CHARS)
        c = unidecode.unidecode_expect_ascii(r.lstrip(self.__class__.LCLEAN_CHARS)).lstrip(self.__class__.LCLEAN_CHARS)
        if c != r:
            r = c
        return r

    @functools.lru_cache(maxsize=32768)
    def rnorm(self, s: str) -> str:
        """Normalize string unicode chars and remove useless chars from its right."""
        return unidecode.unidecode_expect_ascii(s.rstrip(string.punctuation)).rstrip(string.punctuation).lower()

    @functools.lru_cache(maxsize=32768)
    def lnorm(self, s: str) -> str:
        """Normalize string unicode chars and remove useless chars from its left."""
        return unidecode.unidecode_expect_ascii(s.lstrip(string.punctuation)).lstrip(string.punctuation).lower()

    def startslike(self, s: str, pattern: str, *, sep: Optional[str] = None) -> bool:
        """Return True if start of string s is similar to pattern."""
        s = self.lnorm(s)
        pattern = self.rnorm(pattern)
        cut = s[len(pattern) :]
        return s.startswith(pattern) and ((not sep) or (not cut) or (cut[0] in sep))

    def endslike(self, s: str, pattern: str) -> bool:
        """Return True if end of string s is similar to pattern."""
        return self.rnorm(s).endswith(self.rnorm(pattern))

    def rmsuffix(self, s: str, e: str) -> str:
        """Remove string suffix."""
        return s.rstrip(string.punctuation)[: -len(unidecode.unidecode_expect_ascii(e))]

    def rmprefix(self, s: str, e: str) -> str:
        """Remove string prefix."""
        return s.lstrip(string.punctuation)[len(unidecode.unidecode_expect_ascii(e)) :]


class FunctionCleaner(TitleCleanerBase):

    """Cleaner to apply a function to the title string."""

    def __init__(self, func, **kwargs):
        super().__init__(**kwargs)
        assert callable(func)
        self.func = func

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        return self.func(title)


class SimplePrefixCleaner(TitleCleanerBase):

    """Cleaner to remove a static string prefix."""

    def cleanup(self, title: str, prefix: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        if self.startslike(title, prefix, sep=string.punctuation + string.whitespace):
            title = self.lclean(self.rmprefix(title, prefix))
        return title


class SimpleSuffixCleaner(TitleCleanerBase):

    """Cleaner to remove a static string suffix."""

    def cleanup(self, title: str, suffix: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        if self.endslike(title, suffix):
            new_title = self.rclean(self.rmsuffix(title, suffix))
            if new_title.lower() != "the":
                title = new_title
        return title


class ArtistCleaner(SimplePrefixCleaner, SimpleSuffixCleaner):

    """Cleaner to remove artist prefix/suffix."""

    def __init__(self, *args, **kwargs):
        self.prefix_removed = False
        self.suffix_removed = False
        super().__init__(*args, **kwargs)

    def doKeep(self) -> bool:
        """See TitleCleanerBase.doKeep."""
        return not self.suffix_removed

    def cleanup(self, title: str, artist: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        artist_variants = tuple(
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
        for s, suffix_only in itertools.zip_longest(("by " + artist,) + artist_variants, (True,), fillvalue=False):
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

    """Cleaner to remove album prefix/suffix."""

    def cleanup(self, title: str, album: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
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

    """Cleaner to remove a regex match."""

    def __init__(self, regex: str, *, contains: Sequence[str] = (), flags: int = re.IGNORECASE, **kwargs):
        super().__init__(**kwargs)
        self.regex = re.compile(regex, flags)
        self.contains = contains

    def doSkip(self, title: str, *args) -> bool:
        """See TitleCleanerBase.doSkip."""
        if self.contains:
            lower_title = title.lower()
            skip = not any(map(lower_title.__contains__, self.contains))
            if skip:
                self.remove_if_skipped = True
            return skip
        return super().doSkip(title, *args)

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        rstripped = title.rstrip(string.punctuation)
        match = self.regex.search(rstripped)
        if match:
            title = f"{self.rclean(rstripped[:match.start(0)])} {self.lclean(rstripped[match.end(0):])}".rstrip()
        return title


class RegexSuffixCleaner(RegexCleaner):

    """Cleaner to remove a regex suffix match."""

    def __init__(self, regex: str, *, suffixes: Sequence[str] = (), **kwargs):
        super().__init__(regex, **kwargs)
        self.suffixes = suffixes

    def doSkip(self, title: str, *args):
        """See TitleCleanerBase.doSkip."""
        if self.suffixes:
            return not any(self.endslike(title, suffix) for suffix in self.suffixes)
        return super().doSkip(title, *args)

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        match = self.regex.search(title.rstrip(string.punctuation))
        if match:
            title = self.rclean(title[: match.start(0)])
        return title


class RegexPrefixCleaner(RegexCleaner):

    """Cleaner to remove a regex prefix match."""

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        match = self.regex.search(title)
        if match:
            title = self.lclean(title[match.end(0) :])
        return title


class RecordsSuffixCleaner(RegexSuffixCleaner, SimpleSuffixCleaner):

    """Cleaner to remove record suffix."""

    def __init__(self, record_word, **kwargs):
        self.record_word = record_word
        super().__init__(r"([|\)\(\[]|on)[0-9a-z,/ ]+" + record_word + "$", suffixes=(record_word,), **kwargs)

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        # detect and remove 'xxx records' suffix
        match = self.regex.search(title.rstrip(string.punctuation))
        if match:
            # '(xxx yyy records)' suffix
            title = self.rclean(title[: match.start(0)])
        else:
            title = SimpleSuffixCleaner.cleanup(self, title, self.record_word)
            title = self.rclean(" ".join(title.split()[:-1]))
        return title


class StartParenthesesCleaner(TitleCleanerBase):

    """Cleaner to remove parentheses string prefix."""

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        # detect and remove starting parenthesis expression
        closing_pos = title.find(")")
        if title.startswith("(") and (closing_pos != (len(title) - 1)) and (len(title[1:closing_pos]) > 1):
            return self.lclean(title[closing_pos + 1 :])
        return title


class PairedCharCleaner(TitleCleanerBase):

    """Cleaner to fix chars that go by pair."""

    def cleanup(self, title: str) -> str:  # type: ignore
        """See TitleCleanerBase.cleanup."""
        # detect and remove unpaired chars
        char_pairs = ((("(", ")"), False), (('"', '"'), False), (("'", "'"), True))
        c1: str
        c2: str
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


def normalize_title_tag(title: str, artist: str, album: str) -> str:
    """Remove useless prefix and suffix from title tag string."""
    normalizer = TitleNormalizer(artist, album)
    return normalizer.cleanup(title)


def tag(track_filepath: str, review, metadata: Dict[str, str], cover_data: Optional[bytes]):
    """Tag an audio file, return tag dict excluding RG/R128 info and album art."""
    logging.getLogger().info(f"Tagging file {track_filepath!r}")
    mf = mutagen.File(track_filepath, easy=True)

    # sanitize tags
    mf["artist"] = sanitize.normalize_tag_case(review.artist)
    mf["album"] = sanitize.normalize_tag_case(review.album)
    try:
        mf["title"] = normalize_title_tag(metadata["title"], review.artist, review.album)
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


def has_embedded_album_art(filepath: str) -> bool:
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
    if isinstance(mf, mutagen.ogg.OggFileType):
        picture = mutagen.flac.Picture()
        picture.data = cover_data
        picture.type = mutagen.id3.PictureType.COVER_FRONT
        picture.mime = "image/jpeg"
        encoded_data = base64.b64encode(picture.write())
        mf["metadata_block_picture"] = encoded_data.decode("ascii")
    elif isinstance(mf, mutagen.mp3.MP3):
        mf.tags.add(mutagen.id3.APIC(mime="image/jpeg", type=mutagen.id3.PictureType.COVER_FRONT, data=cover_data))
        mf.save()
    elif isinstance(mf, mutagen.mp4.MP4):
        mf["covr"] = [mutagen.mp4.MP4Cover(cover_data, imageformat=mutagen.mp4.AtomDataType.JPEG)]


# copy month names before changing locale
MONTH_NAMES = calendar.month_name[1:]
MONTH_NAMES_ABBR = calendar.month_abbr[1:]
