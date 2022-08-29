#!/usr/bin/env python3
"""Given a Wordle guess and response, print all possible matches."""
import argparse
import sys


class Wordle:

    def __init__(self, guess, response):
        self.guess = list(guess)
        if len(self.guess) != 5:
            raise RuntimeError(f"Illegal length for word: {guess}")
        self.results = list(response)
        if len(self.results) != 5:
            raise RuntimeError(f"Illegal length for response: {response}")
        self.by_char = {}
        # Create diction with characters for keys and an array of results
        # as the value
        for c, r in zip(self.guess, self.results):
            if r not in ("G", "O", "W"):
                raise RuntimeError(f"Illegal response: {response}")
            v = self.by_char.get(c, [])
            v.append(r)
            self.by_char[c] = v

    def greens(self):
        return [c for c, r in zip(self.guess, self.results) if r == "G"]

    def oranges(self):
        return [c for c, r in zip(self.guess, self.results) if r == "O"]

    def whites(self):
        return [c for c, r in zip(self.guess, self.results) if r == "W"]

    def filter(self):
        """Create and return a filter function"""
        f = "def filter(w):\n"
        # Handle Green letters
        for i, c in enumerate(self.guess):
            if self.results[i] == "G":
                f += f"    if w[{i}] != '{c}':\n"
                f += "         return False\n"
            elif self.results[i] == "O":
                f += f"    if w[{i}] == '{c}':\n"
                f += "         return False\n"
        for c, r in self.by_char.items():
            g = r.count("G")
            o = r.count("O")
            w = r.count("W")
            if w == len(r):
                f += f"    if '{c}' in w:\n"
                f += "        return False\n"
            elif w > 0:
                f += f"    if w.count('{c}') != {g + o}:\n"
                f += "        return False\n"
            else:
                f += f"    if w.count('{c}') < {g + o}:\n"
                f += "        return False\n"
        f += "    return True\n"
        loc = locals()
        exec(f, globals(), loc)
        return loc["filter"]


def make_argparser():
    """Return arparse.ArgumentParser instance"""
    parser = argparse.ArgumentParser(
        description=__doc__,  # printed with -h/--help
        # Don't mess with format of description
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # To have --help print defaults with trade-off it changes
        # formatting, use: ArgumentDefaultsHelpFormatter
    )
    # Only allow one of debug/quiet mode
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument("-d", "--debug",
                                 action='store_true', default=False,
                                 help="Turn on debugging")
    verbosity_group.add_argument("-q", "--quiet",
                                 action="store_true", default=False,
                                 help="run quietly")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    parser.add_argument("word", metavar="word", type=str, nargs=1,
                        help="guessed word")
    parser.add_argument("result", metavar="result", type=str, nargs=1,
                        help="result encoded as Gs, Os, and Ws (e.g. OWWGO)")
    return parser


def main(argv=None):
    parser = make_argparser()
    args = parser.parse_args(argv if argv else sys.argv[1:])
    w = Wordle(args.word[0], args.result[0])
    try:
        with open("/usr/share/dict/words") as f:
            words = filter(lambda w: len(w) == 5,
                           [s.strip() for s in f.readlines()])
    except FileNotFoundError:
        print("Dictionary not found")
        return(1)
    f = w.filter()
    possible = filter(f, words)
    print("\n".join(list(possible)))
    return(0)


if __name__ == "__main__":
    sys.exit(main())
