#!/usr/bin/env python3

import collections
import contextlib
import functools
import os
import shutil
import tempfile
import unittest

import mutagen
import requests

import sacad.recurse as recurse


try:
  redirect_stdout = contextlib.redirect_stdout
except AttributeError:
  # contextlib.redirect_stdout is not available (Python 3.3), build our own
  import sys
  @contextlib.contextmanager
  def redirect_stdout(s):
    original_stdout, sys.stdout = sys.stdout, s
    try:
      yield
    finally:
      sys.stdout = original_stdout


@unittest.skip
class TestRecursive(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.temp_dir = tempfile.TemporaryDirectory()
    cls.album1_dir = os.path.join(cls.temp_dir.name, "album1")
    os.mkdir(cls.album1_dir)
    url = "https://upload.wikimedia.org/wikipedia/en/4/45/ACDC_-_Back_In_Black-sample.ogg"
    with contextlib.closing(requests.get(url, stream=True)) as response:
      response.raise_for_status()
      filepath1 = os.path.join(cls.album1_dir, "2 track.ogg")
      with open(filepath1, "wb") as f:
        for chunk in response.iter_content(2 ** 14):
          f.write(chunk)
    mf = mutagen.File(filepath1)
    mf["artist"] = "ARTIST1"
    mf["album"] = "ALBUM1"
    mf.save()

    cls.album2_dir = os.path.join(cls.temp_dir.name, "album2")
    os.mkdir(cls.album2_dir)
    filepath2 = os.path.join(cls.album2_dir, "1.dat")
    with open(filepath2, "wb") as f:
      f.write(b"\x00" * 8)
    filepath3 = os.path.join(cls.album2_dir, "2 track.ogg")
    shutil.copyfile(filepath1, filepath3)
    mf = mutagen.File(filepath3)
    mf["artist"] = "ARTIST2"
    mf["album"] = "ALBUM2"
    mf.save()

    cls.not_album_dir = os.path.join(cls.temp_dir.name, "not an album")
    os.mkdir(cls.not_album_dir)
    shutil.copyfile(filepath2, os.path.join(cls.not_album_dir, "a.dat"))

    cls.invalid_album_dir = os.path.join(cls.temp_dir.name, "invalid album")
    os.mkdir(cls.invalid_album_dir)
    shutil.copyfile(filepath2, os.path.join(cls.invalid_album_dir, "2 track.ogg"))
    filepath4 = os.path.join(cls.invalid_album_dir, "3 track.ogg")
    shutil.copyfile(filepath1, filepath4)
    mf = mutagen.File(filepath4)
    del mf["album"]
    mf.save()

  @classmethod
  def tearDownClass(cls):
    cls.temp_dir.cleanup()

  def test_analyze_lib(self):
    with open(os.devnull, "wb") as dn, redirect_stdout(dn):
      work = recurse.analyze_lib(__class__.temp_dir.name, "a.jpg")
      self.assertEqual(len(work), 2)
      self.assertIn(__class__.album1_dir, work)
      self.assertEqual(work[__class__.album1_dir], ("ARTIST1", "ALBUM1"))
      self.assertIn(__class__.album2_dir, work)
      self.assertEqual(work[__class__.album2_dir], ("ARTIST2", "ALBUM2"))

      work = recurse.analyze_lib(__class__.temp_dir.name, "1.dat")
      self.assertEqual(len(work), 1)
      self.assertIn(__class__.album1_dir, work)
      self.assertEqual(work[__class__.album1_dir], ("ARTIST1", "ALBUM1"))

  def test_get_metadata(self):
    self.assertEqual(recurse.get_metadata(map(functools.partial(os.path.join,
                                                                __class__.album1_dir),
                                              os.listdir(__class__.album1_dir))),
                     ("ARTIST1", "ALBUM1"))
    self.assertEqual(recurse.get_metadata(map(functools.partial(os.path.join,
                                                                __class__.album2_dir),
                                              os.listdir(__class__.album2_dir))),
                     ("ARTIST2", "ALBUM2"))
    self.assertEqual(recurse.get_metadata(map(functools.partial(os.path.join,
                                                                __class__.not_album_dir),
                                              os.listdir(__class__.not_album_dir))),
                     (None, None))
    self.assertEqual(recurse.get_metadata(map(functools.partial(os.path.join,
                                                                __class__.invalid_album_dir),
                                              os.listdir(__class__.invalid_album_dir))),
                     ("ARTIST1", None))

  def test_analyze_dir(self):
    with open(os.devnull, "wb") as dn, redirect_stdout(dn):
      stats = collections.defaultdict(int)
      r = recurse.analyze_dir(stats,
                              __class__.album1_dir,
                              os.listdir(__class__.album1_dir),
                              "1.jpg",
                              None,
                              0)
      self.assertIn("files", stats)
      self.assertEqual(stats["files"], 1)
      self.assertIn("albums", stats)
      self.assertEqual(stats["albums"], 1)
      self.assertIn("missing covers", stats)
      self.assertEqual(stats["missing covers"], 1)
      self.assertNotIn("errors", stats)
      self.assertEqual(r[0], ("ARTIST1", "ALBUM1"))

      stats.clear()
      r = recurse.analyze_dir(stats,
                              __class__.album2_dir,
                              os.listdir(__class__.album2_dir),
                              "1.jpg",
                              None,
                              0)
      self.assertIn("files", stats)
      self.assertEqual(stats["files"], 2)
      self.assertIn("albums", stats)
      self.assertEqual(stats["albums"], 1)
      self.assertIn("missing covers", stats)
      self.assertEqual(stats["missing covers"], 1)
      self.assertNotIn("errors", stats)
      self.assertEqual(r[0], ("ARTIST2", "ALBUM2"))
      stats.clear()
      r = recurse.analyze_dir(stats,
                              __class__.album2_dir,
                              os.listdir(__class__.album2_dir),
                              "1.dat",
                              None,
                              0)
      self.assertIn("files", stats)
      self.assertEqual(stats["files"], 2)
      self.assertIn("albums", stats)
      self.assertEqual(stats["albums"], 1)
      self.assertNotIn("missing covers", stats)
      self.assertNotIn("errors", stats)
      self.assertEqual(r[0], (None, None))

      stats.clear()
      r = recurse.analyze_dir(stats,
                              __class__.not_album_dir,
                              os.listdir(__class__.not_album_dir),
                              "1.jpg",
                              None,
                              0)
      self.assertIn("files", stats)
      self.assertEqual(stats["files"], 1)
      self.assertNotIn("albums", stats)
      self.assertNotIn("missing covers", stats)
      self.assertNotIn("errors", stats)
      self.assertEqual(r[0], (None, None))

      stats.clear()
      r = recurse.analyze_dir(stats,
                              __class__.invalid_album_dir,
                              os.listdir(__class__.invalid_album_dir),
                              "1.jpg",
                              None,
                              0)
      self.assertIn("files", stats)
      self.assertEqual(stats["files"], 2)
      self.assertIn("albums", stats)
      self.assertEqual(stats["albums"], 1)
      self.assertIn("missing covers", stats)
      self.assertEqual(stats["missing covers"], 1)
      self.assertIn("errors", stats)
      self.assertEqual(stats["errors"], 1)
      self.assertEqual(r[0], ("ARTIST1", None))


if __name__ == "__main__":
  # run tests
  unittest.main()
