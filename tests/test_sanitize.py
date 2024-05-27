"""String sanitization related tests."""

import unittest

import amg.sanitize as sanitize


class TestSanitize(unittest.TestCase):
    """String sanitization test suite."""

    def test_normalize_tag_case(self):
        """Fix tag capitalization."""
        references = {
            "A Little Test": "A Little Test",
            "I Like L.A": "I Like L.A",
            "Of The Moon": "Of the Moon",
            "Just A Bunch Of Letters": "Just a Bunch of Letters",
            "Episode VI": "Episode VI",
            "EPISODE VIA": "Episode Via",
            "VI VI VI": "VI VI VI",
            "Episode VI: name": "Episode VI: Name",
            "Matsya - The Fish": "Matsya - The Fish",
            "I'M ALIVE!": "I'm Alive!",
            "MARK OF THE BEAST PT. 2: SCION OF DARKNESS": "Mark of the Beast PT. 2: Scion of Darkness",
            "BZZ: THE": "Bzz: The",
            "薄氷(Thin Ice)": "薄氷 (Thin Ice)",
            "III-III: Imha Tarikatı (Sect of Destruction)": "III-III: Imha Tarikatı (Sect of Destruction)",
            "Cosa Del Pantano": "Cosa del Pantano",
            "Lunatic-Liar-Lord": "Lunatic-Liar-Lord",
            "The Day After 'Trinity'": "The Day After 'Trinity'",
            "Amalgamations of Gore/Skin Display": "Amalgamations of Gore/Skin Display",
        }
        for before, after in references.items():
            self.assertEqual(sanitize.normalize_tag_case(before), after)
