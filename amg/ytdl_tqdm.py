"""Show YoutubeDL download progress with a tqdm progress bar."""

import logging
import shutil
from pathlib import Path
from typing import Any, Self

import tqdm
from tqdm.std import tqdm as Tqdm


def ltrunc(s: str, length: int) -> str:
    """Truncate string from left."""
    assert length > 0
    if len(s) <= length:
        return s
    return f"…{s[-(length - 1) :]}"


class ytdl_tqdm:
    """Convenient context manager to report ytdl download progress."""

    def __init__(self, ytdl_opts: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """See tqdm.tqdm for args description."""
        self.tqdm: Tqdm[Any] | None = None
        self.prev_downloaded_bytes = 0
        self.tqdm_kwargs: dict[str, Any] = kwargs
        if ytdl_opts is not None:
            self.setup_ytdl(ytdl_opts)

    def __bool__(self) -> bool:
        """Return True if there is an associated progress bar, False instead."""
        return self.tqdm is not None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        tqdm_bar = self.tqdm
        if tqdm_bar is not None:
            tqdm_bar.close()

    def setup_ytdl(self, ytdl_opts: dict[str, Any]) -> dict[str, Any]:
        """Initialize tqdm bar, update YoutubeDL options, and return them."""
        ytdl_opts.update({"quiet": True, "no_warnings": True, "logger": logging.getLogger()})
        ytdl_opts.setdefault("progress_hooks", []).append(self._log_progress)

        assert self.tqdm is None
        self.tqdm = self._get_new_tqdm()

        return ytdl_opts

    def _log_progress(self, ytdl_state: dict[str, Any]) -> None:
        """Report youtube-dl progress (callback)."""
        if ytdl_state["status"] != "downloading":
            return

        tqdm_bar = self.tqdm
        assert tqdm_bar is not None

        # get current state
        downloaded_bytes = int(ytdl_state["downloaded_bytes"])
        total_bytes = int(ytdl_state.get("total_bytes", ytdl_state["total_bytes_estimate"]))

        # update state
        if self.prev_downloaded_bytes > downloaded_bytes:
            # new YoutubeDL file, reset progress bar
            try:
                tqdm_bar.reset()
            except AttributeError:
                # tqdm < 4.32.0
                tqdm_bar.close()
                tqdm_bar = self._get_new_tqdm()
                self.tqdm = tqdm_bar
            newly_downloaded_bytes = downloaded_bytes
        else:
            newly_downloaded_bytes = downloaded_bytes - self.prev_downloaded_bytes

        # update description
        columns = shutil.get_terminal_size((80, 0))[0]
        filename = Path(str(ytdl_state["filename"])).name
        desc = ltrunc(filename, columns // 5)
        tqdm_bar.set_description(desc, refresh=False)

        # update bar
        tqdm_bar.total = total_bytes
        tqdm_bar.update(newly_downloaded_bytes)
        self.prev_downloaded_bytes = downloaded_bytes

    def _get_new_tqdm(self) -> Tqdm[Any]:
        """Set up and return a new tqdm instance."""
        # default args
        tqdm_kwargs = {"unit": "B", "unit_scale": True, "unit_divisor": 1024}
        # merge with user args
        tqdm_kwargs.update(self.tqdm_kwargs)
        return tqdm.tqdm(**tqdm_kwargs)
