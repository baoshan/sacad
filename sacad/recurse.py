#!/usr/bin/env python3

""" Recursively search and download album covers for a music library. """

import argparse
import collections
import concurrent.futures
import itertools
import logging
import os
import shutil
import sys
import time

import mutagen

import sacad


AUDIO_EXTENSIONS = ("aac",
                    "ape",
                    "flac",
                    "m4a",
                    "mp3",
                    "mp4",
                    "ogg",
                    "oga",
                    "opus",
                    "wv")


def analyze_lib(lib_dir, cover_filename):
  """ Recursively analyze library, and return a dict of path -> (artist, album). """
  work = {}
  scrobbler = itertools.cycle("|/-\\")
  stats = collections.OrderedDict(((k, 0) for k in("dirs", "files", "albums", "missing covers", "errors")))
  time_progress_shown = show_analyze_progress(stats, scrobbler)
  for rootpath, rel_dirpaths, rel_filepaths in os.walk(lib_dir):
    stats["dirs"] += 1
    metadata, time_progress_shown = analyze_dir(stats, rootpath, rel_filepaths, cover_filename, scrobbler, time_progress_shown)
    if all(metadata):
      work[rootpath] = metadata
  show_analyze_progress(stats, scrobbler, end=True)
  return work


def get_metadata(audio_filepaths):
  """ Return a tuple of album, artist from a list of audio files. """
  artist, album = None, None
  for audio_filepath in audio_filepaths:
    mf = mutagen.File(audio_filepath)
    if mf is None:
      continue
    artist = mf.get("albumartist",
                    mf.get("artist", None))
    if artist is not None:
      artist = artist[0]
    album = mf.get("album", None)
    if album is not None:
      album = album[0]
    if artist and album:
      # stop at the first file that succeeds (for performance)
      break
  return artist, album


def analyze_dir(stats, parent_dir, rel_filepaths, cover_filename, scrobbler, time_progress_shown):
  """ Analyze a directory (non recursively) to get its album metadata if it is one. """
  metadata = None, None
  audio_filepaths = []
  for rel_filepath in rel_filepaths:
    stats["files"] += 1
    time_progress_shown = show_analyze_progress(stats, scrobbler, time_progress_shown=time_progress_shown)
    try:
      ext = os.path.splitext(rel_filepath)[1][1:].lower()
    except IndexError:
      continue
    if ext in AUDIO_EXTENSIONS:
      audio_filepaths.append(os.path.join(parent_dir, rel_filepath))
  if audio_filepaths:
    stats["albums"] += 1
    if not os.path.isfile(os.path.join(parent_dir, cover_filename)):
      stats["missing covers"] += 1
      metadata = get_metadata(audio_filepaths)
      if not all(metadata):
        # failed to get metadata for this album
        stats["errors"] += 1
  return metadata, time_progress_shown


def show_analyze_progress(stats, scrobbler, *, time_progress_shown=0, end=False):
  """ Display analysis global progress. """
  now = time.monotonic()
  if (sys.stdout.isatty() and
     (end or (now - time_progress_shown > 0.1))):  # do not refresh display at each call (for performance)
    time_progress_shown = now
    print("Analyzing library %s | %s" % (next(scrobbler) if not end else "-",
                                         "  ".join(("%u %s" % (v, k)) for k, v in stats.items())),
          end="\r" if not end else "\n")
  return time_progress_shown


def get_covers(work, args):
  """ Get missing covers. """
  with concurrent.futures.ProcessPoolExecutor() as executor:
    # post work
    futures = {}
    for path, (artist, album) in work.items():
      future = executor.submit(sacad.search_and_download,
                               album,
                               artist,
                               args.format,
                               args.size,
                               args.size_tolerance_prct,
                               args.amazon_tlds,
                               args.no_lq_sources,
                               os.path.join(path, args.filename))
      futures[future] = (path, artist, album)

    # follow progress
    stats = collections.OrderedDict(((k, 0) for k in("ok", "errors", "no result found")))
    errors = []
    not_found = []
    for i, future in enumerate(concurrent.futures.as_completed(futures)):
      path, artist, album = futures[future]
      try:
        status = future.result()
      except:
        stats["errors"] += 1
        errors.append((path, artist, album))
      else:
        if status:
          stats["ok"] += 1
        else:
          stats["no result found"] += 1
          not_found.append((path, artist, album))
      show_get_covers_progress(i,
                               len(work),
                               stats,
                               artist=artist,
                               album=album)
  if work:
    show_get_covers_progress(i + 1, len(work), stats, end=True)
  for path, artist, album in not_found:
    print("Unable to find cover for '%s' by '%s' from '%s'" % (album, artist, path))
  for path, artist, album in errors:
    print("Error occured while searching cover for '%s' by '%s' from '%s'" % (album, artist, path))
  if errors:
    print("Please report this at https://github.com/desbma/sacad/issues")


def show_get_covers_progress(current_idx, total_count, stats, *, artist=None, album=None, end=False):
  """ Display search and download global progress. """
  if not sys.stdout.isatty():
    return
  line_width = shutil.get_terminal_size(fallback=(80, 0))[0] - 1
  print(" " * line_width, end="\r")
  print("Searching and downloading covers %u%% (%u/%u)%s | %s" % (100 * current_idx // total_count,
                                                                  current_idx,
                                                                  total_count,
                                                                  (" | Current album: '%s' '%s'" % (artist, album)) if not end else "",
                                                                  "  ".join(("%u %s" % (v, k)) for k, v in stats.items())),
        end="\r" if not end else "\n")


def cl_main():
  # parse args
  arg_parser = argparse.ArgumentParser(description="SACAD (recursive tool) v%s.%s" % (sacad.__version__,
                                                                                      __doc__),
                                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  arg_parser.add_argument("lib_dir",
                          help="Music library directory to recursively analyze")
  arg_parser.add_argument("size",
                          type=int,
                          help="Target image size")
  arg_parser.add_argument("filename",
                          help="Cover image filename")
  sacad.setup_common_args(arg_parser)
  args = arg_parser.parse_args()
  args.format = os.path.splitext(args.filename)[1][1:].lower()
  try:
    args.format = sacad.SUPPORTED_IMG_FORMATS[args.format]
  except KeyError:
    print("Unable to guess image format from extension, or unknown format: %s" % (args.format))
    exit(1)

  # silence the logger
  logging.getLogger().setLevel(logging.ERROR)

  # do the job
  work = analyze_lib(args.lib_dir, args.filename)
  get_covers(work, args)
