Angry Metal Guy Player
======================

[![Tests Status](https://img.shields.io/travis/desbma/amg-player/master.svg?label=tests&style=flat)](https://travis-ci.org/desbma/amg-player)
[![Coverage](https://img.shields.io/coveralls/desbma/amg-player/master.svg?style=flat)](https://coveralls.io/github/desbma/amg-player?branch=master)

Angry Metal Guy Player (amg) is a Python command line tool to automatically play tracks from [Angry Metal Guy](https://www.angrymetalguy.com/) reviews.

I created this because:  

* I like Angry Metal Guy, and discovered great music (both metal and totally non-metal) thanks to their reviews
* I often disagree with their ratings (in fact I disagree more often than I agree), both for overrating and underrating
* Even when I disagree, I like reading their reviews
* I want to listen to the music **before** I read the review, to avoid getting influenced
* To be efficient, I want to listen to the tracks like a radio, and read the review to learn more only when I like something


**This is a work in progress** (ie. probably not usable for you right now).


## Features

* Supports embedded tracks from: YouTube, Bandcamp, SoundCloud

*TODO*

## Installation

*TODO*


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
