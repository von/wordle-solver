#!/usr/bin/env python3
"""Given a Wordle guess and response, print all possible matches."""
import argparse
import cmd
import random
import string
import sys


class AssistCmd(cmd.Cmd):
    intro = "Welcome to Wordle assist. Enter 'help' for help."
    prompt = "> "

    def __init__(self, wordle):
        super().__init__()
        self.w = wordle

    def do_list(self, arg):
        """List all possible words"""
        print("\n".join(list(self.w.possible)))

    def do_random(self, arg):
        """Print a random possible word"""
        print(random.choice(self.w.possible))

    def do_quit(self, arg):
        """Quit"""
        return True

    def default(self, line):
        words = line.split()
        if len(words) != 2:
            return super().default(line)
        try:
            self.w.process_guess(words[0], words[1])
        except RuntimeError as e:
            print(f"Error: {e}")
            return
        p = len(self.w.possible)
        print(f"{p} possible word{'s' if p > 1 else ''}")


class Wordle:

    def __init__(self):
        # List of valid words
        self.words = self.load_word_list()
        # Possible words given any processing
        self.possible = self.words
        # Filters is a list of functions which must return True
        # for a given word for it to be a valid possible answer to
        # the puzzle
        self.filters = []
        # Parameters
        #
        # Maximum number of guesses in a game
        self.guess_limit = 6

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
        filters = []
        # Handle Green and Orange results telling us certain places
        # must or must not be certain letters
        for i, c in enumerate(letters):
            if responses[i] == "G":
                filters.append(self.filter_index_eq(i, c))
            elif responses[i] == "O":
                filters.append(self.filter_index_ne(i, c))
        # Walk each character in the guess and process how many times
        # it appears
        for c, r in response_by_char.items():
            green = r.count("G")
            orange = r.count("O")
            white = r.count("W")
            if white == len(r):
                # No hits, if this character appears in a word, it's
                # not a match.
                filters.append(self.filter_not(c))
            elif white > 0:
                # Hits with one or more miss, we know exactly how many times
                # this character has to appear in the answer
                filters.append(
                        self.filter_count_eq(c, green + orange))
            else:
                # All hits, no misses. We only know the minimum
                # number of times this character appears inthe answer
                filters.append(
                    self.filter_count_ge(c, green + orange))
        self.possible = [w for w in self.possible
                         if all([f(w) for f in filters])]
        self.filters.extend(filters)

    @staticmethod
    def generate_response(word, guess):
        """Given a word and a guess, generate a response string"""
        letters = list(word)
        response = ["W", "W", "W", "W", "W"]
        # First determine all the correct letters
        # Remove them from letters to avoid them being double counted.
        for i, l in enumerate(list(guess)):
            if letters[i] == l:
                response[i] = "G"
                letters[i] = None
        # Now find any letters that match remaining letters but are in
        # the wrong place. Remove letters as we match to them as to not
        # double count them.
        for i, l in enumerate(list(guess)):
            if response[i] == "G":
                continue
            if l in letters:
                response[i] = "O"
                letters[letters.index(l)] = None
        success = response.count("G") == 5
        return (success, "".join(response))

    def play(self):
        """Play a game"""
        guess_num = 1
        word = random.choice(self.words)
        while guess_num <= self.guess_limit:
            guess = input(f"Your guess ({guess_num}/{self.guess_limit})? ")
            guess_num += 1
            success, response = self.generate_response(word, guess)
            if success:
                print("Success!")
                break
            else:
                print(response)
        if not success:
            print(f"Sorry, you have run out of guesses. The word was {word}")

    def assist(self):
        """Assist in playing Wordle"""
        AssistCmd(self).cmdloop()


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

    subparsers = parser.add_subparsers(help='sub-command help')

    parser_play = subparsers.add_parser('play', help=cmd_play.__doc__)
    parser_play.set_defaults(func=cmd_play)

    parser_assist = subparsers.add_parser('assist', help=cmd_assist.__doc__)
    parser_assist.set_defaults(func=cmd_assist)

    parser_process = subparsers.add_parser('process', help=cmd_process.__doc__)
    parser_process.set_defaults(func=cmd_process)
    parser_process.add_argument("word", metavar="word", type=str, nargs=1,
                                help="guessed word")
    parser_process.add_argument(
        "result", metavar="result", type=str, nargs=1,
        help="result encoded as Gs, Os, and Ws (e.g. OWWGO)")

    return parser


def cmd_play(w, args):
    """Play wordle"""
    w.play()
    return(0)


def cmd_process(w, args):
    """Process a guess and response"""
    w.process_guess(args.word[0], args.result[0])
    print("\n".join(list(w.possible)))
    return(0)


def cmd_assist(w, args):
    """Assst with playing Wordle"""
    w.assist()
    return(0)


def main(argv=None):
    parser = make_argparser()
    args = parser.parse_args(argv if argv else sys.argv[1:])
    w = Wordle()
    return args.func(w, args)


if __name__ == "__main__":
    sys.exit(main())
