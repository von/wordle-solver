#!/usr/bin/env python3
"""Given a Wordle guess and response, print all possible matches."""
import argparse
import string
import sys


class Wordle:

    def __init__(self):
        # List of valid words
        self.words = self.load_word_list()
        # Filters is a list of functions which must return True
        # for a given word for it to be a valid possible answer to
        # the puzzle
        self.filters = []

    # Create filters as closures to force early binding
    # See https://docs.python-guide.org/writing/gotchas/#late-binding-closures
    @staticmethod
    def filter_index_eq(i, c):
        """Return a filter that requires index i to be character c"""
        return lambda w: w[i] == c

    @staticmethod
    def filter_index_ne(i, c):
        """Return a filter that requires index i not to be character c"""
        return lambda w: w[i] != c

    @staticmethod
    def filter_not(c):
        """Return a filter that requires word not to contain letter c"""
        return lambda w: c not in w

    @staticmethod
    def filter_count_eq(c, n):
        """Return a filter that requires letter c n times"""
        return lambda w: w.count(c) == n

    @staticmethod
    def filter_count_ge(c, n):
        """Return a filter that requires letter c at least n times"""
        return lambda w: w.count(c) >= n

    def load_word_list(self):
        """Load and return a list of words"""
        try:
            with open("/usr/share/dict/words") as f:
                words = filter(lambda w: len(w) == 5,
                               [s.strip() for s in f.readlines()])
        except FileNotFoundError:
            raise RuntimeError("Dictionary not found")
        # Remove proper nouns
        words = filter(lambda w: w[0] in string.ascii_lowercase, words)
        return list(words)

    def process_guess(self, word, response):
        """Process a guess (a word and a response)

        word is a five-letter word
        response is five characters: G, O, or W"""
        letters = list(word)
        if len(letters) != 5:
            raise RuntimeError(f"Illegal length for word: {word}")
        responses = list(response)
        if len(responses) != 5:
            raise RuntimeError(f"Illegal length for response: {response}")
        response_by_char = {}
        # Create dictionary with characters for keys and an array of results
        # as the value
        for c, r in zip(letters, responses):
            if r not in ("G", "O", "W"):
                raise RuntimeError(f"Illegal response: {response}")
            v = response_by_char.get(c, [])
            v.append(r)
            response_by_char[c] = v
        # Handle Green and Orange results telling us certain places
        # must or must not be certain letters
        for i, c in enumerate(letters):
            if responses[i] == "G":
                self.filters.append(self.filter_index_eq(i, c))
            elif responses[i] == "O":
                self.filters.append(self.filter_index_ne(i, c))
        # Walk each character in the guess and process how many times
        # it appears
        for c, r in response_by_char.items():
            green = r.count("G")
            orange = r.count("O")
            white = r.count("W")
            if white == len(r):
                # No hits, if this character appears in a word, it's
                # not a match.
                self.filters.append(self.filter_not(c))
            elif white > 0:
                # Hits with one or more miss, we know exactly how many times
                # this character has to appear in the answer
                self.filters.append(
                        self.filter_count_eq(c, green + orange))
            else:
                # All hits, no misses. We only know the minimum
                # number of times this character appears inthe answer
                self.filters.append(
                    self.filter_count_ge(c, green + orange))

    def possible_words(self):
        """Return a list of possible words given processed guesses"""
        # Return list of all words for which all filters return True
        return [w for w in self.words if all([f(w) for f in self.filters])]


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
    w = Wordle()
    w.process_guess(args.word[0], args.result[0])
    print("\n".join(list(w.possible_words())))
    return(0)


if __name__ == "__main__":
    sys.exit(main())
