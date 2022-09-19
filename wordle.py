#!/usr/bin/env python3
"""Given a Wordle guess and response, print all possible matches."""
import argparse
import cmd
import collections
import functools
import random
import statistics
import string
import sys


class AssistCmd(cmd.Cmd):
    """Command loop for 'assist'"""

    intro = "Welcome to Wordle assist. Enter 'help' for help."
    prompt = "> "

    def __init__(self, wordle):
        super().__init__()
        self.s = Solver()
        self.guess_num = 1

    def do_list(self, arg):
        """List all possible words"""
        print("\n".join(list(self.s.possible)))

    def do_guess(self, arg):
        """Print a guess"""
        print(self.s.generate_guess(self.guess_num))

    def do_quit(self, arg):
        """Quit"""
        return True

    def do_dump(self, arg):
        """Dump wordle state"""
        print(self.s.dump())

    def do_remove(self, arg):
        """Remove a word from consideration"""
        print(f"Removing {arg}")
        try:
            self.s.words.remove(arg)
        except ValueError:
            print(f"{arg} not in list")
        try:
            self.s.possible.remove(arg)
        except ValueError:
            # May already have been removed
            pass

    def default(self, line):
        words = line.split()
        if len(words) != 2:
            return super().default(line)
        try:
            self.s.process_response(words[0], words[1])
        except RuntimeError as e:
            print(f"Error: {e}")
            return
        self.s.update_possible_words()
        self.s.update_letter_freq()
        p = len(self.s.possible)
        print(f"{p} possible word{'s' if p > 1 else ''}")
        self.guess_num += 1


class PlayCmd(cmd.Cmd):
    """Command loop for 'play'"""

    intro = "Welcome to Wordle"

    def __init__(self, wordle, word=None):
        super().__init__()
        self.w = wordle
        self.guess_num = 1
        self.word = word if word else random.choice(self.w.word_list())
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
        "adlet",
        "alani",
        "altin",
        "ampyx",
        "arara",
        "artar",
        "bensh",
        "beode",
        "chold",
        "decap",
        "divel",
        "izote",
        "glaky",
        "glink",
        "guaka",
        "kusam",
        "nintu",
        "ninut",
        "nondu",
        "nunni",
        "rokee",
        "skeeg",
        "skewl",
        "taled",
        "tungo",
        "uninn",
        "unlie",
        "ungka",
        "unsin",
        "upbid",
        "vedro",
        "yabbi"
    ]

    guess_limit = 6

    @classmethod
    @functools.cache
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

    def play(self, word=None):
        """Play a game"""
        PlayCmd(self, word=word).cmdloop()


class Solver:

    # Values for letter_knowledge. Also weights for word selection.
    #
    # We know nothing about if/where the letter appears
    NO_KNOWLEDGE = 1
    # We know something about if/where the letter appears
    # but we don't know we have complete knowledge.
    SOME_KNOWLEDGE = .1
    # We know everywhere the letter appears
    COMPLETE_KNOWLEDGE = 0

    def __init__(self):
        self.words = Wordle.word_list()

        # Possible words given any processing
        self.possible = self.words

        # What letters are known in the solution
        self.known_letters = [None, None, None, None, None]

        # Letters we know are not to be given positions in the solution
        self.known_non_letters = [[], [], [], [], []]

        # What we know about the letters
        self.letters = {}
        for letter in string.ascii_lowercase:
            self.letters[letter] = {
                # Where does this letter appear in the word
                "appears_at": [],
                # Where this letter does not appear in the word
                "does_not_appear_at": [],
                # Is count exact (True) or a minimum (False)
                "exact_count": False,
                # Number of times this letter appears
                "count": 0,
                # Frequency the letters appears in possible words
                "freq": 0
            }
        # Create self.letters[*]["freq"]
        self.update_letter_freq()

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

    def update_possible_words(self):
        """Update self.possible"""
        # Create a list of filters to run against the complete word
        # list based on our state.
        filters = []
        for c, info in self.letters.items():
            for i in info["appears_at"]:
                filters.append(self.filter_index_eq(i, c))
            for i in info["does_not_appear_at"]:
                filters.append(self.filter_index_ne(i, c))
            if info["count"] == 0 and not info["exact_count"]:
                continue
            if info["exact_count"]:
                filters.append(self.filter_count_eq(c, info["count"]))
            else:
                filters.append(self.filter_count_ge(c, info["count"]))
        self.possible = [w for w in self.possible
                         if all([f(w) for f in filters])]

    def update_letter_freq(self):
        """Update self.letters[freq] based on self.possible"""
        for letter, info in self.letters.items():
            count = len([w for w in self.possible if letter in w])
            info["freq"] = count / len(self.possible)

    def update_weights(self):
        """Update self.possible values based on self.letters"""
        self.possible = dict(zip(
            self.words,
            [sum([self.letters[letter]["weight"] for letter in set(w)])
             for w in self.words]))

    def generate_guess(self, guess_num):
        """Generate a guess given what we know and guess number"""
        if len(self.possible) == 1:
            return self.possible[0]
        elif guess_num < Wordle.guess_limit:
            weights = dict(zip(
                self.words,
                [sum([self.letters[letter]["freq"] for letter in set(w)])
                 for w in self.words]))
            max_weight = max(weights.values())
            guess = random.choice([w for w in weights.keys()
                                   if weights[w] == max_weight])
            return(guess)
        else:
            # Last guess, take a stab...
            return random.choice(self.possible)

    def process_response(self, word, response):
        """Process a reponse to a word

        word is a five-letter word
        response is five characters: G, O, or W"""
        # Validate work and response and split into letters
        letters = list(word.lower())
        if len(letters) != 5:
            raise RuntimeError(f"Illegal length for word: {word}")
        if any([c not in string.ascii_lowercase for c in letters]):
            raise RuntimeError(f"Illegal characters in word: {word}")
        responses = list(response.upper())
        if len(responses) != 5:
            raise RuntimeError(f"Illegal length for response: {response}")
        if any([r not in "GOW" for r in responses]):
            raise RuntimeError(f"Illegal character in response: {response}")

        # Handle Green and Orange results telling us certain places
        # must or must not be certain letters
        for i, c in enumerate(letters):
            if responses[i] == "G":
                self.known_letters[i] = c
                self.letters[c]["appears_at"].append(i)
            else:
                # Both W and O means the letter isn't correct in the
                # position.
                self.known_non_letters[i].append(c)
                self.letters[c]["does_not_appear_at"].append(i)
        # Create dictionary with characters for keys and an array of results
        # as the value
        response_by_char = collections.defaultdict(list)
        for c, r in zip(letters, responses):
            response_by_char[c].append(r)
        # Walk each character in the guess and process how many times
        # it appears
        for c, r in response_by_char.items():
            green = r.count("G")
            orange = r.count("O")
            white = r.count("W")
            # We know we have at least one of the given letter for
            # each orange and green response
            self.letters[c]["count"] = max(self.letters[c]["count"],
                                           green + orange)
            # If we have a white response, then we know exactly
            # how many times it appears (may be zero).
            self.letters[c]["exact_count"] = white > 0

    def assist(self):
        """Assist in playing Wordle"""
        AssistCmd(self).cmdloop()

    def dump(self):
        """Return our state as a string"""
        s = "Known letters: "
        s += "".join([c if c else "-" for c in self.known_letters]) + "\n"
        s += "Letter knowledge:\n"
        for letter, info in self.letters.items():
            s += f"  {letter}: "
            s += f"Count: {'==' if info['exact_count'] else '>='}"
            s += f"{info['count']}"
            s += f" frequency: {info['freq']}\n"
        s += f"{len(self.possible)} possible words\n"
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

    parser_auto = subparsers.add_parser('auto', help=cmd_auto.__doc__)
    parser_auto.set_defaults(func=cmd_auto)
    parser_auto.add_argument("-w", "--word",
                             action="store", default=None,
                             help="specify word to guess")
    parser_auto.add_argument("-n", "--num_games",
                             action="store", default=100, type=int,
                             help="number of games to play")

    parser_play = subparsers.add_parser('play', help=cmd_play.__doc__)
    parser_play.set_defaults(func=cmd_play)
    parser_play.add_argument("-w", "--word",
                             action="store", default=None,
                             help="specify word to guess")

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
    w.play(args.word)
    return(0)


def cmd_process(w, args):
    """Process a guess and response"""
    s = Solver()
    s.process_response(args.word[0], args.result[0])
    s.update_possible_words()
    s.update_letter_freq()
    print("\n".join(list(s.possible)))
    return(0)


def cmd_auto(w, args):
    """Automatically play numerous games and report how we do"""
    results = []
    failures = []
    for game in range(args.num_games):
        print(f"Game {game}...")
        word = args.word if args.word else random.choice(w.word_list())
        s = Solver()
        for guess_num in range(w.guess_limit):
            guess = s.generate_guess(guess_num + 1)
            if args.debug:
                print(f"Guessing {guess}")
            success, response = w.generate_response(word, guess)
            if success:
                results.append(guess_num)
                break
            s.process_response(guess, response)
            s.update_possible_words()
            s.update_letter_freq()
            if args.debug:
                print(f"   ...{len(s.possible)} left.")
        else:
            results.append(w.guess_limit)
        if response == "GGGGG":
            print(f"   ...got {word} in {guess_num+1} guesses")
        else:
            print(f"   ...failed to get {word}.")
            failures.append(word)
    tally = {}
    for result in results:
        tally[result] = tally.get(result, 0) + 1
    for n in range(w.guess_limit):
        print(f"{n+1} guesses: {tally.get(n, 0)}")
    try:
        average = statistics.fmean([result+1 for result in results
                                    if result < w.guess_limit])
        print(f"Average: {average}")
    except statistics.StatisticsError:
        # All failures
        pass
    print(f"Failures: {tally.get(w.guess_limit,0)} : {' '.join(failures)}")


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
