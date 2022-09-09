#!/usr/bin/env python3
"""Given a Wordle guess and response, print all possible matches."""
import argparse
import cmd
import random
import string
import sys


class AssistCmd(cmd.Cmd):
    """Command loop for 'assist'"""

    intro = "Welcome to Wordle assist. Enter 'help' for help."
    prompt = "> "

    def __init__(self, wordle):
        super().__init__()
        self.s = Solver()

    def do_list(self, arg):
        """List all possible words"""
        print("\n".join(list(self.s.possible)))

    def do_random(self, arg):
        """Print a random possible word"""
        print(random.choice(self.s.possible))

    def do_random_weighted(self, arg):
        """Print a random word selected based on weighting of what we know"""
        def weight(word):
            return sum([self.s.letter_knowledge[letter]
                        for letter in list(word)])
        weights = [weight(word) for word in self.s.words]
        print(random.choices(self.s.words, weights)[0])

    def do_quit(self, arg):
        """Quit"""
        return True

    def do_dump(self, arg):
        """Dump wordle state"""
        print(self.s.dump())

    def default(self, line):
        words = line.split()
        if len(words) != 2:
            return super().default(line)
        try:
            self.s.process_guess(words[0], words[1])
        except RuntimeError as e:
            print(f"Error: {e}")
            return
        p = len(self.s.possible)
        print(f"{p} possible word{'s' if p > 1 else ''}")


class PlayCmd(cmd.Cmd):
    """Command loop for 'play'"""

    intro = "Welcome to Wordle"

    def __init__(self, wordle):
        super().__init__()
        self.w = wordle
        self.guess_num = 1
        self.word = random.choice(self.w.word_list())
        self.prompt = f"Your guess ({self.guess_num}/{self.w.guess_limit})? "

    def do_quit(self, arg):
        """Quit"""
        return True

    def default(self, line):
        words = line.split()
        if len(words) != 1:
            return super().default(line)
        guess = words[0]
        if len(guess) != 5:
            print("Guess must be a 5-letter word")
            return
        self.guess_num += 1
        success, response = self.w.generate_response(self.word, guess)
        if success:
            print("Success!")
            return True
        print(response)
        if self.guess_num > self.w.guess_limit:
            print("Sorry, you have run out of guesses."
                  f" The word was {self.word}")
            return True
        self.prompt = f"Your guess ({self.guess_num}/{self.w.guess_limit})? "


class Wordle:

    # Words dict/words the NYT doesn't consider to be words
    nyt_non_words = [
        "bensh",
        "kusam",
        "rokee",
        "skewl",
        "tungo",
        "yabbi"
    ]

    guess_limit = 6

    @classmethod
    def word_list(cls):
        """Load and return a list of words"""
        try:
            with open("/usr/share/dict/words") as f:
                words = [s.strip() for s in f.readlines()]
        except FileNotFoundError:
            raise RuntimeError("Dictionary not found")

        def filt(w):
            return (len(w) == 5 and
                    # Remove proper nouns
                    w[0] in string.ascii_lowercase and
                    # Remove words NYT doesn't consider words
                    w not in cls.nyt_non_words)
        words = filter(filt, words)
        return list(words)

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
        PlayCmd(self).cmdloop()


class Solver:

    # Values for letter_knowledge. Also weights for word selection.
    #
    # We know nothing about if/where the letter appears
    NO_KNOWLEDGE = .2
    # We know something about if/where the letter appears
    # but we don't know we have complete knowledge.
    SOME_KNOWLEDGE = .1
    # We know everywhere the letter appears
    COMPLETE_KNOWLEDGE = 0

    def __init__(self):
        self.words = Wordle.word_list()
        # Possible words given any processing
        self.possible = self.words
        # Filters is a list of functions which must return True
        # for a given word for it to be a valid possible answer to
        # the puzzle
        self.filters = []
        # What we know about the letters
        self.letter_knowledge = {}
        for letter in string.ascii_lowercase:
            self.letter_knowledge[letter] = self.NO_KNOWLEDGE

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

    def process_guess(self, word, response):  # noqa - too complex
        """Process a guess (a word and a response)

        word is a five-letter word
        response is five characters: G, O, or W"""
        letters = list(word.lower())
        if len(letters) != 5:
            raise RuntimeError(f"Illegal length for word: {word}")
        responses = list(response.upper())
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
            # Figure out what we know about this letter
            # If all greens and at least one white, we know everything
            # else we just know something.
            if white > 0 and white + green == len(r):
                self.letter_knowledge[c] = self.COMPLETE_KNOWLEDGE
            elif self.letter_knowledge[c] != self.COMPLETE_KNOWLEDGE:
                self.letter_knowledge[c] = self.SOME_KNOWLEDGE
        self.possible = [w for w in self.possible
                         if all([f(w) for f in filters])]
        self.filters.extend(filters)

    def assist(self):
        """Assist in playing Wordle"""
        AssistCmd(self).cmdloop()

    def dump(self):
        """Return our state as a string"""
        s = ""
        for letter, weight in self.letter_knowledge.items():
            s += f"{letter}: {weight}\n"
        return s


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
    s = Solver()
    s.process_guess(args.word[0], args.result[0])
    print("\n".join(list(s.possible)))
    return(0)


def cmd_assist(w, args):
    """Assst with playing Wordle"""
    s = Solver()
    s.assist()
    return(0)


def main(argv=None):
    parser = make_argparser()
    args = parser.parse_args(argv if argv else sys.argv[1:])
    w = Wordle()
    return args.func(w, args)


if __name__ == "__main__":
    sys.exit(main())
