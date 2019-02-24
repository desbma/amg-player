""" Show YoutubeDL download progress with a tqdm progress bar. """

import os
import shutil

import tqdm


def ltrunc(s, l):
  """ Truncate string from left. """
  assert(l > 0)
  if len(s) <= l:
    return s
  return f"…{s[-(l - 1):]}"


class ytdl_tqdm:

  def __init__(self, ytdl_opts=None, **kwargs):
    """ See tqdm.tqdm for args description. """
    self.tqdm = None
    self.prev_downloaded_bytes = 0
    self.tqdm_kwargs = kwargs
    if ytdl_opts is not None:
      self.setup_ytdl(ytdl_opts)

  def __bool__(self):
    return self.tqdm is not None

  def __enter__(self):
    return self

  def __exit__(self, *args):
    if self.tqdm is not None:
      return self.tqdm.close()

  def setup_ytdl(self, ytdl_opts):
    new_opts = {"quiet": True,
                "no_warnings": True,
                "progress_hooks": (self._log_progress,)}
    ytdl_opts.update(new_opts)

    assert(self.tqdm is None)
    self.tqdm = self._get_new_tqdm()

    return ytdl_opts

  def _log_progress(self, ytdl_state):
    if ytdl_state["status"] != "downloading":
      return

    # get current state
    downloaded_bytes = ytdl_state["downloaded_bytes"]
    try:
      total_bytes = ytdl_state["total_bytes"]
    except KeyError:
      total_bytes = ytdl_state["total_bytes_estimate"]

    # update state
    if self.prev_downloaded_bytes > downloaded_bytes:
      # new YoutubeDL file, build a new progress bar
      self.tqdm.close()
      self.tqdm = self._get_new_tqdm()
      newly_downloaded_bytes = downloaded_bytes
    else:
      newly_downloaded_bytes = downloaded_bytes - self.prev_downloaded_bytes

    # update description
    columns = shutil.get_terminal_size((80, 0))[0]
    filename = os.path.basename(ytdl_state["filename"])
    desc = ltrunc(filename, columns // 5)
    self.tqdm.set_description(desc, refresh=False)

    # update bar
    self.tqdm.total = total_bytes
    self.tqdm.update(newly_downloaded_bytes)
    self.prev_downloaded_bytes = downloaded_bytes

  def _get_new_tqdm(self):
    # default args
    tqdm_kwargs = {"unit": "B",
                   "unit_scale": True,
                   "unit_divisor": 1024}
    # merge with user args
    tqdm_kwargs.update(self.tqdm_kwargs)
    return tqdm.tqdm(**tqdm_kwargs)