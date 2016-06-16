Angry Metal Guy Player
======================

[![Latest Version](https://img.shields.io/pypi/v/amg.svg?style=flat)](https://pypi.python.org/pypi/amg-player/)
[![Tests Status](https://img.shields.io/travis/desbma/amg-player/master.svg?label=tests&style=flat)](https://travis-ci.org/desbma/amg-player)
[![Coverage](https://img.shields.io/coveralls/desbma/amg-player/master.svg?style=flat)](https://coveralls.io/github/desbma/amg-player?branch=master)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/amg.svg?style=flat)](https://pypi.python.org/pypi/amg/)
[![License](https://img.shields.io/github/license/desbma/amg-player.svg?style=flat)](https://pypi.python.org/pypi/amg/)

Angry Metal Guy Player (amg) is a Python multi platform command line tool to automatically play tracks from [Angry Metal Guy](https://www.angrymetalguy.com/) reviews.

I created this because:  

* I like Angry Metal Guy, and discovered great music (both metal and totally non-metal) thanks to their reviews
* I often disagree with their ratings (in fact I disagree more often than I agree), both for overrating and underrating
* Even when I disagree, I like reading their reviews
* I want to listen to the music **before** I read the review, to avoid getting influenced
* To be efficient, I want to listen to the tracks like a radio, and read the review to learn more only when I like something


## Features

* Can work either in interactive mode (manually select tracks) or totally automatic (play new tracks like a radio)
* Supports embedded tracks from: YouTube, Bandcamp, SoundCloud
* Play YouTube video if available, or generate a video on the fly with the cover image + audio track(s) (requires FFMpeg or Libav)


## Installation

Angry Metal Guy Player requires [Python](https://www.python.org/downloads/) >= 3.3.

### From PyPI (with PIP)

1. If you don't already have it, [install pip](http://www.pip-installer.org/en/latest/installing.html) for Python 3 (not needed if you are using Python >= 3.4)
2. Install Angry Metal Guy Player: `pip3 install amg`

### From source

1. If you don't already have it, [install setuptools](https://pypi.python.org/pypi/setuptools#installation-instructions) for Python 3
2. Clone this repository: `git clone https://github.com/desbma/sacad`
3. Install Angry Metal Guy Player: `python3 setup.py install`

**Angry Metal Guy Player only supports [MPV player](https://mpv.io/) for now.**


## Command line usage

Run `amg -h` to get full command line reference.

### Examples

* Browse and play interactively last 50 reviews:

    `amg -c 50`

* Choose the first track to play, then play all tracks in chronological order:

    `amg -m radio`

* Play last 20 tracks in chronological order, skipping those already played:

    `amg -c 20 -m discover`


## License

[GPLv3](https://www.gnu.org/licenses/gpl-3.0-standalone.html)
