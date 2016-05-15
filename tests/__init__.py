#!/usr/bin/env python3

import logging
import unittest



class TestAmg(unittest.TestCase):
  pass


if __name__ == "__main__":
  # disable logging
  logging.basicConfig(level=logging.CRITICAL + 1)
  #logging.basicConfig(level=logging.DEBUG)

  # run tests
  unittest.main()
