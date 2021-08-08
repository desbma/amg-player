""" Remove unwanted chars or patterns from strings. """

import itertools
import string
from typing import Optional

import unidecode

VALID_PATH_CHARS = frozenset(f"-_.()!#$%%&'@^{{}}~ {string.ascii_letters}{string.digits}")
TAG_LOWERCASE_WORDS = frozenset(
    (
        "a",
        "an",
        "and",
        "at",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "over",
        "the",
        "to",
        "with",
        "de",
        "des",
        "du",
        "le",
        "la",
        "les",
        "by",
        "vs",
    )
)


def sanitize_for_path(s: str) -> str:
    """Sanitize a string to be FAT/NTFS friendly when used in file path."""
    s = s.translate(str.maketrans("/\\|*", "---x"))
    s = "".join(c for c in unidecode.unidecode_expect_ascii(s) if c in VALID_PATH_CHARS)
    s = s.strip()
    s = s.rstrip(".")  # this if for FAT on Android
    return s


def normalize_tag_case(s: str) -> str:
    """Normalize case of an audio tag string."""

    def split_sep_char(w, c):
        parts = w.split(c, 1)
        if len(parts) > 1:
            parts[1] = c + parts[1]
        parts = tuple(filter(None, parts))
        return parts

    def remove_punct(s):
        return "".join(c for c in s if c not in string.punctuation)

    old_words = tuple(itertools.chain.from_iterable(split_sep_char(w, "(") for w in s.split()))
    new_words = []
    prev_word: Optional[str] = None
    roman_letters = frozenset("IVXLCDM")
    punct_followed_all_uppercase = set(".-")
    punct_followed_uppercase = set(string.punctuation)
    punct_followed_uppercase.remove("'")
    for i, old_word in enumerate(old_words):
        if (
            (prev_word is not None) and ((prev_word[-1] in punct_followed_all_uppercase) and old_word[0].isupper())
        ) or ("." in old_word):
            new_word = old_word
        elif old_word[0] in "[(-":
            new_word = old_word
        elif old_word.find("'") == 1:
            if i > 0:
                new_word = "'".join((old_word[0].lower(), old_word[2:].capitalize()))
            else:
                new_word = old_word
        elif (
            (i != 0)
            and (old_word.lower() in TAG_LOWERCASE_WORDS)
            and (prev_word is not None)
            and (prev_word[-1] not in punct_followed_uppercase)
        ):
            new_word = old_word.lower()
        elif all(map(roman_letters.__contains__, remove_punct(old_word))):
            new_word = old_word
        else:
            new_word = old_word.capitalize()
        new_word = new_word.replace("I'M", "I'm")
        new_words.append(new_word)
        prev_word = old_word
    return " ".join(new_words)
