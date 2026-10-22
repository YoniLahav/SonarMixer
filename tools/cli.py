"""Talk to the configured audio provider directly (no app needed).

  python tools/cli.py                 list channels and their state
  python tools/cli.py game +5         change by 5 percentage points
  python tools/cli.py media 40        set to 40%
  python tools/cli.py mute chat       toggle mute
  python tools/cli.py --provider windows   (any command, using another provider)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knobmixer import config, providers  # noqa: E402


def main(args):
    cfg, _ = config.load()
    kind = cfg["provider"]["type"]
    if "--provider" in args:
        i = args.index("--provider")
        kind = args[i + 1]
        del args[i:i + 2]
    p = providers.create(kind, cfg["provider"]["options"] if kind == cfg["provider"]["type"] else {})
    try:
        if not args:
            state = p.get_state()
            for c in p.channels():
                st = state.get(c["id"])
                desc = "n/a" if st is None else f"{st['volume'] * 100:5.1f}%{'  MUTED' if st['muted'] else ''}"
                print(f"{c['id']:24} {desc:14} {c['label']}")
        elif args[0] == "mute":
            ch = args[1]
            p.set_mute(ch, not p.get_state([ch])[ch]["muted"])
        else:
            ch, arg = args
            cur = p.get_state([ch])[ch]["volume"]
            v = cur + float(arg) / 100 if arg[0] in "+-" else float(arg) / 100
            print(f"{ch} -> {p.set_volume(ch, v) * 100:.1f}%")
    finally:
        p.close()


if __name__ == "__main__":
    main(sys.argv[1:])
