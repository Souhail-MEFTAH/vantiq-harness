"""Copy the harness into each demo's tools/ directory.

Vendored, not imported across folders, for the same reason guide_style.py is:
every demo is exported and restored as an independent namespace, and a
cross-folder import breaks the moment someone restores one on its own.

The copies must stay byte-identical to the source. Edit here, run this, and the
verification below proves the seven copies agree.
"""
import filecmp
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = ["vq.py", "source.py", "lint.py", "uilint.py", "client.py", "push.py",
         "opscheck.py", "selftest.py", "notes_index.py", "NOTES.md", "README.md"]
DEMOS = ["Supply Chain Mgt", "Defense", "Manufacturing/DemoSeries_Manufacturing",
         "Healthcare", "Logistics", "Retail", "Public Safety"]


def main(check_only=False):
    problems = 0
    for demo in DEMOS:
        dest = os.path.join(ROOT, demo.replace("/", os.sep), "tools", "vharness")
        if not os.path.isdir(os.path.dirname(dest)):
            print("  %-34s no tools/ directory, skipped" % demo.split("/")[0])
            continue
        os.makedirs(dest, exist_ok=True)
        same = 0
        for fn in FILES:
            src = os.path.join(HERE, fn)
            if not os.path.exists(src):
                continue
            dst = os.path.join(dest, fn)
            if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
                same += 1
                continue
            if check_only:
                print("  %-34s %s differs" % (demo.split("/")[0], fn))
                problems += 1
            else:
                shutil.copy2(src, dst)
        print("  %-34s %d file(s) in tools/vharness" % (demo.split("/")[0], len(FILES)))
    # prove it
    for demo in DEMOS:
        dest = os.path.join(ROOT, demo.replace("/", os.sep), "tools", "vharness")
        for fn in FILES:
            src, dst = os.path.join(HERE, fn), os.path.join(dest, fn)
            if os.path.exists(dst) and not filecmp.cmp(src, dst, shallow=False):
                print("  !! %s/%s differs from source" % (demo, fn))
                problems += 1
    print("\n%s" % ("all copies identical to source" if not problems
                    else "%d discrepancies" % problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
