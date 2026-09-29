#!/usr/bin/env python3
"""Tag existing deliverables in place (audio untouched).   tag.py --title T --artist A FILE [FILE ...]"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mslib as L
ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="+"); ap.add_argument("--title"); ap.add_argument("--artist"); a = ap.parse_args()
for f in a.files: L.tag_file(f, a.title, a.artist); print("tagged", os.path.basename(f))
