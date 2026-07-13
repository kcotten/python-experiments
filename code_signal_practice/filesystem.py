import datetime
import json
import os
import pprint
import shutil
import time
from collections import defaultdict
from dataclasses import asdict, dataclass

test_dir = "/Users/kris/Downloads"


# Given a root directory path and an age threshold in days, return a list of all files
# (recursively) that have not been modified within that threshold. Include
# file path and size in bytes.
@dataclass
class File:
    path: str
    bytes: int
    days_old: float


def not_modified(dir: str, age: int):
    now = time.time()
    cutoff = age * 86400  # seconds in a day
    results = []
    # files = os.walk(dir)
    for path, _, filenames in os.walk(dir):
        # print(path)
        for fname in filenames:
            fpath = os.path.join(path, fname)
            try:
                stat = os.stat(fpath)
                current_age = now - stat.st_mtime
                if current_age > cutoff:
                    # print(f"appending {fpath}")
                    results.append(
                        File(fpath, stat.st_size, round(current_age / 86400, 1))
                    )
            except:
                continue

    # return sorted(results, key=lambda tup: tup[2], reverse=True)
    print(json.dumps([asdict(f) for f in results], indent=2))


# not_modified("/Users/kris/Downloads", 60)


# Given a root directory, find all groups of duplicate files (by content). Return a
# list of groups, where each group is a list of paths that share identical content.
def file_hash(fpath: str, chunk_size: int = 65536):
    from hashlib import sha256

    h = sha256()
    with open(fpath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def duplicates(root: str):
    sizemap = defaultdict(list)
    for path, _, filenames in os.walk(root):
        for fname in filenames:
            fpath = os.path.join(path, fname)
            try:
                size = os.path.getsize(fpath)
                sizemap[size].append(fpath)

            except:
                continue

    hmap = defaultdict(list)
    for size, paths in sizemap.items():
        if len(paths) < 2:
            continue
        for path in paths:
            try:
                digest = file_hash(path)
                hmap[digest].append(path)
            except:
                continue
    return [paths for paths in hmap.values() if len(paths) > 1]


pprint.pprint(duplicates(test_dir))


def organize_by_date(source_dir: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    for fname in os.listdir(source_dir):
        src = os.path.join(source_dir, fname)
        if not os.path.isfile(src):
            continue
        try:
            mtime = os.path.getmtime(src)
            folder = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m")
            dest_dir = os.path.join(source_dir, folder)
            os.makedirs(dest_dir, exist_ok=True)

            dest = os.path.join(dest_dir, fname)
            if os.path.exists(dest):
                base, ext = os.path.splitext(fname)
                dest = os.path.join(dest_dir, f"{base}_{int(mtime)}{ext}")

            shutil.move(src, dest)
            counts[folder] = counts.get(folder, 0) + 1
        except OSError:
            continue

    return counts
