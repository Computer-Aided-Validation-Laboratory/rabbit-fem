#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

def resolve_symlinks(target_dir: str):
    target_dir = os.path.abspath(target_dir)
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target_dir,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        return
    root_dir = res.stdout.strip()
    print(f"Resolving Git symlinks in {root_dir}...")

    ls_res = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=root_dir,
        capture_output=True,
        text=True,
    )
    if ls_res.returncode != 0:
        return

    count = 0
    for line in ls_res.stdout.splitlines():
        if not line.startswith("120000"):
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        sl = parts[1].strip()
        full_sl = os.path.normpath(os.path.join(root_dir, sl))
        if not os.path.exists(full_sl):
            continue

        try:
            with open(full_sl, "r", encoding="utf-8", errors="ignore") as f:
                target_rel = f.read().strip()
            if not target_rel or "\n" in target_rel:
                continue
            target_full = os.path.normpath(os.path.join(os.path.dirname(full_sl), target_rel))
            if os.path.exists(target_full):
                if os.path.isdir(target_full):
                    os.remove(full_sl)
                    shutil.copytree(target_full, full_sl, dirs_exist_ok=True)
                else:
                    os.remove(full_sl)
                    shutil.copy2(target_full, full_sl)
                count += 1
        except Exception:
            pass

    print(f"Symlinks resolved successfully ({count} converted) in {root_dir}.")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    resolve_symlinks(target)

if __name__ == "__main__":
    main()
