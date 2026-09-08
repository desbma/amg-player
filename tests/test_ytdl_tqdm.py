"""YoutubeDL progress bar tests."""

import io
import unittest
from collections.abc import Callable
from typing import Any

from amg import ytdl_tqdm

DOWNLOADED_BYTES = 1024
TOTAL_BYTES = 4096


class TestYtdlTqdm(unittest.TestCase):
    """YoutubeDL progress bar test suite."""

    def setUp(self) -> None:
        """Set up test case stuff."""
        self.progress = ytdl_tqdm.ytdl_tqdm(file=io.StringIO())
        self.addCleanup(self.progress.__exit__)
        ytdl_opts: dict[str, Any] = {}
        self.progress.setup_ytdl(ytdl_opts)
        self.hook: Callable[[dict[str, Any]], None] = ytdl_opts["progress_hooks"][0]

    def state(self, **sizes: int | None) -> dict[str, Any]:
        """Build a YoutubeDL downloading state."""
        return {"status": "downloading", "downloaded_bytes": DOWNLOADED_BYTES, "filename": "track.mp3", **sizes}

    def test_total_bytes(self) -> None:
        """Test progress report of a download of known size."""
        self.hook(self.state(total_bytes=TOTAL_BYTES))
        assert self.progress.tqdm is not None
        self.assertEqual(self.progress.tqdm.total, TOTAL_BYTES)
        self.assertEqual(self.progress.tqdm.n, DOWNLOADED_BYTES)

    def test_total_bytes_estimate(self) -> None:
        """Test progress report of a download of estimated size."""
        self.hook(self.state(total_bytes=None, total_bytes_estimate=TOTAL_BYTES))
        assert self.progress.tqdm is not None
        self.assertEqual(self.progress.tqdm.total, TOTAL_BYTES)

    def test_unknown_total_bytes(self) -> None:
        """Test progress report of a download of unknown size."""
        self.hook(self.state(total_bytes=None))
        assert self.progress.tqdm is not None
        self.assertIsNone(self.progress.tqdm.total)
        self.assertEqual(self.progress.tqdm.n, DOWNLOADED_BYTES)
