#!/usr/bin/env python3
"""Given a Wordle guess and response, print all possible matches."""
import argparse
import cmd
import collections
import copy
import functools
import itertools
import os
import random
import re
import statistics
import string
import sys

import wordfreq
from wordfreq import zipf_frequency


class Colors:
    black = "\033[30m"
    red = "\033[31m"
    green = "\033[32m"
    yellow = "\033[33m"
    blue = "\033[34m"
    magenta = "\033[35m"
    cyan = "\033[36m"
    white = "\033[37m"
    reset = "\033[0m"


class WordleError(RuntimeError):
    """Base class for module errors."""
    pass


class InvalidSolverStateError(WordleError):
    """Guess caused solver to go into invalid state."""
    pass


class InvalidWordError(WordleError):
    """Provided word illegal (wrong length or invalid characters)."""
    pass


class InvalidResponseError(WordleError):
    """Provided response illegal (wrong length or invalid characters)."""
    pass


class AssistCmd(cmd.Cmd):
    """Command loop for 'assist'"""

    intro = "Welcome to Wordle assist. Enter 'help' for help."
    prompt = "> "

    def __init__(self, solver):
        super().__init__()
        self.s = solver
        self.guess_num = 1
        self.last_guess = None

    def do_list(self, arg):
        """List all possible words"""
        print("\n".join(
            [f"{s} {zipf_frequency(s, 'en')}" for s in self.s.possible]))

    def do_guess(self, arg):
        """Print a guess"""
        self.last_guess = self.s.generate_guess(self.guess_num)
        print(self.last_guess)

    def do_quit(self, arg):
        """Quit"""
        return True

    def do_EOF(self, arg):
        """Handle end of file by quitting"""
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
        try:
            if len(words) == 1 and self.last_guess:
                self.s.handle_response(self.last_guess, words[0])
            elif len(words) == 2:
                self.s.handle_response(words[0], words[1])
            else:
                return super().default(line)
        except InvalidSolverStateError as e:
            print(f"Invalid response: {e}")
            return
        except WordleError as e:
            print(f"Error: {e}")
            return
        p = len(self.s.possible)
        if p < 10:
            print(f"{p} possible word{'s' if p > 1 else ''} : " +
                  " ".join(self.s.possible))
        else:
            print(f"{p} possible words")
        self.guess_num += 1


class PlayCmd(cmd.Cmd):
    """Command loop for 'play'"""

    intro = "Welcome to Wordle"

    def __init__(self, wordle, word=None):
        super().__init__()
        self.w = wordle
        self.guess_num = 1
        if word:
            if len(word) != 5:
                raise InvalidWordError(f"Length of {word} != 5")
            self.word = word
        else:
            self.word = random.choice(self.w.word_list())
        self.prompt = f"Your guess ({self.guess_num}/{self.w.guess_limit})? "

    def do_quit(self, arg):
        """Quit"""
        return True

    def do_EOF(self, arg):
        """Handle end of file by quitting"""
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
        print(f"{self.w.colorize_reponse(response, guess)} " +
              f"({self.w.colorize_reponse(response)})")
        if self.guess_num > self.w.guess_limit:
            print("Sorry, you have run out of guesses."
                  f" The word was {self.word}")
            return True
        self.prompt = f"Your guess ({self.guess_num}/{self.w.guess_limit})? "


class Wordle:

    guess_limit = 6

    def __init__(self, debug=False, threshold=3.0):
        self.debug = debug
        self.threshold = threshold

    @functools.cache
    def word_list(self):
        """Load and return a list of words"""
        # Remove comments from additional-words.txt and non-words.txt
        comment_regex = re.compile(r"^#")

        words = [w for w in
                 itertools.takewhile(
                     lambda w: zipf_frequency(w, "en") >= self.threshold,
                     wordfreq.iter_wordlist("en"))
                 if (len(w) == 5 and
                     all([c in string.ascii_lowercase for c in w]))]
        if self.debug:
            print(f"Read {len(words)} words from wordfreq")

        try:
            # Words to add
            add_words_path = os.path.join(os.path.dirname(__file__),
                                          'additional-words.txt')
            with open(add_words_path) as f:
                add_words = [s.strip() for s in f.readlines()]
        except FileNotFoundError:
            raise WordleError("additional-words.txt not found")
        add_words = list(itertools.filterfalse(comment_regex.search,
                                               add_words))
        if self.debug:
            print(f"Read {len(add_words)} additional words"
                  f" from {add_words_path}")
        for w in add_words:
            if w not in words:
                words.append(w)

        try:
            # Words that NYT Wordle doesn't accept
            non_words_path = os.path.join(os.path.dirname(__file__),
                                          'non-words.txt')
            with open(non_words_path) as f:
                non_words = [s.strip() for s in f.readlines()]
        except FileNotFoundError:
            raise WordleError("non-words.txt not found")
        non_words = list(itertools.filterfalse(comment_regex.search,
                                               non_words))
        if self.debug:
            print(f"Read {len(non_words)} non-words from {non_words_path}")

        if self.debug:
            print(f"Returning {len(words)} words")
        return words

    @staticmethod
    def generate_response(word, guess):
        """Given a word and a guess, generate a response string"""
        letters = list(word)
        response = ["-", "-", "-", "-", "-"]
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
                response[i] = "Y"
                letters[letters.index(l)] = None
        success = response.count("G") == 5
        return (success, "".join(response))

    @staticmethod
    def colorize_reponse(response, word=None):
        """Given a word and a five-character response, colorize the word

        If word is None, then colorize the response itself"""
        word = word if word else response
        s = ""
        for letter, resp in zip(list(word), list(response)):
            if resp == "G":
                s += f"{Colors.green}{letter}{Colors.reset}"
            elif resp == "Y":
                s += f"{Colors.yellow}{letter}{Colors.reset}"
            else:
                s += letter
        return s

    def play(self, word=None):
        """Play a game"""
        PlayCmd(self, word=word).cmdloop()

    def solver(self):
        """Return a Solver instance"""
        return Solver(self, debug=self.debug)

    def word_freq(self, word):
        """Return word frequency as logrythmic value

        Currently a wrapper around wordfreq.zipf_frequency()"""
        return zipf_frequency(word, "en")


class Solver:

    def __init__(self, wordle, debug=False):
        self.debug = debug
        self.wordle = wordle

        self.words = wordle.word_list()

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

    def backup_state(self):
        """Return a dictionary suitable for restore_state()"""
        backup = {}
        backup["possible"] = copy.copy(self.possible)
        backup["known_letters"] = copy.copy(self.known_letters)
        backup["letters"] = copy.deepcopy(self.letters)
        return backup

    def restore_state(self, backup):
        """Restore a backup created by backup_state()"""
        self.possible = copy.copy(backup["possible"])
        self.known_letters = copy.copy(backup["known_letters"])
        self.letters = copy.deepcopy(backup["letters"])

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
        if len(self.possible) == 0:
            raise InvalidSolverStateError("No possible words.")
        if len(self.possible) > 1:
            # Check for any letters we can infer from the fact they
            # appear at a given index in all possible words.
            for i in range(5):
                if self.known_letters[i]:
                    continue
                c = self.possible[0][i]
                if all([w[i] == c for w in self.possible]):
                    if self.debug:
                        print(f"Only possible letter at index {i} is {c}")
                    info = self.letters[c]
                    info["appears_at"].append(i)
                    info["count"] = max(info["count"], len(info["appears_at"]))
                    self.known_letters[i] = c

    def update_letter_freq(self):
        """Update self.letters[freq] based on self.possible"""
        for letter, info in self.letters.items():
            count = len([w for w in self.possible
                         if w.count(letter) > info["count"]])
            info["freq"] = count / len(self.possible)
        if self.debug:
            max_letters = sorted(self.letters.keys(),
                                 key=lambda l: self.letters[l]["freq"],
                                 reverse=True)[:5]
            s = [f"{c} ({self.letters[c]['freq']:.2f})" for c in max_letters]
            print(f"Top letters: {' '.join(s)}")

    def word_weight(self, word):
        """Given a word, return its weight in terms of being a guess"""
        weight = 0.0
        # Determine if word can help determine count of letters
        # Use set() to only consider each letter once
        for letter in set(word):
            info = self.letters[letter]
            if (not info["exact_count"] and
                    word.count(letter) > info["count"]):
                weight += info["freq"]
        # Determine if word can help figure out location of letters
        # TODO: Avoid words with more than count+1 letters?
        for i, letter in enumerate(word):
            info = self.letters[letter]
            if (i not in info["appears_at"] and
                    i not in info["does_not_appear_at"]):
                # This letters in this location will tell us something
                weight += info["freq"]
        return weight

    def generate_guess(self, guess_num):
        """Generate a guess given what we know and guess number"""
        if len(self.possible) == 1:
            if self.debug:
                print("Down to only one possible solution.")
            return self.possible[0]
        elif Wordle.guess_limit - guess_num >= len(self.possible):
            # We have at least as many guesses as possible words, so we know
            # we will solve so guess based on word frequency.
            guess = max(self.possible, key=lambda w: self.wordle.word_freq(w))
            if self.debug:
                print(f"Guessing {guess} based on frequency.")
            return guess
        elif guess_num < Wordle.guess_limit:
            weights = {w: self.word_weight(w) for w in self.words}
            max_weight = max(weights.values())
            # If max_weight is zero for some reason, then we're to
            # the point of guessing possible words.
            if max_weight == 0:
                if self.debug:
                    print("No word weighted. Guessing.")
                return random.choice(self.possible)
            max_words = [w for w in weights.keys()
                         if weights[w] == max_weight]
            if self.debug:
                print(f"Choosing from: {' '.join(max_words)}"
                      f" with weight {max_weight}")
            guess = random.choice(max_words)
            return(guess)
        else:
            guess = max(self.possible, key=lambda w: self.wordle.word_freq(w))
            if self.debug:
                print(f"Last guess, {guess} is most common.")
            return guess

    def handle_response(self, word, response):
        """Handle a reponse to a word

        word is a five-letter word
        response is five characters: G, Y, or -"""
        backup = self.backup_state()
        try:
            self.process_response(word, response)
            self.update_possible_words()
            self.update_letter_freq()
        except InvalidSolverStateError as e:
            self.restore_state(backup)
            raise e
        except WordleError as e:
            raise e

    def process_response(self, word, response):
        """Process a reponse to a word

        word is a five-letter word
        response is five characters: G, Y, or -"""
        # Validate work and response and split into letters
        letters = list(word.lower())
        if len(letters) != 5:
            raise InvalidWordError(f"Illegal length for word: {word}")
        if any([c not in string.ascii_lowercase for c in letters]):
            raise InvalidWordError(f"Illegal characters in word: {word}")
        responses = list(response.upper())
        if len(responses) != 5:
            raise InvalidResponseError(
                f"Illegal length for response: {response}")
        if any([r not in "GY-" for r in responses]):
            raise InvalidResponseError(
                f"Illegal character in response: {response}")

        # Handle Green and Yellow results telling us certain places
        # must or must not be certain letters
        for i, c in enumerate(letters):
            if responses[i] == "G":
                if self.known_letters[i]:
                    if self.known_letters[i] != c:
                        raise InvalidSolverStateError(
                            "Conflicting response: "
                            f" characyer at {i} already =="
                            f" {self.known_letters[i]}")
                    # Letter already known
                    continue
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
            yellow = r.count("Y")
            grey = r.count("-")
            # We know we have at least one of the given letter for
            # each yellow and green response
            self.letters[c]["count"] = max(self.letters[c]["count"],
                                           green + yellow)
            # If we have a grey response, then we know exactly
            # how many times it appears (may be zero).
            self.letters[c]["exact_count"] = grey > 0

    def assist(self):
        """Assist in playing Wordle"""
        AssistCmd(self).cmdloop()

    def dump(self):
        """Return our state as a string"""
        s = "Known letters: "
        s += "".join([c if c else "-" for c in self.known_letters]) + "\n"
        s += "Eliminated letters: "
        s += " ".join([c for c in self.letters.keys()
                       if (self.letters[c]["count"] == 0 and
                           self.letters[c]["exact_count"])]) + "\n"
        s += "Letter knowledge:\n"
        for letter, info in self.letters.items():
            if info["count"] == 0 and info["exact_count"]:
                continue
            if info["freq"] == 0:
                continue
            s += f"  {letter}: "
            s += f"Count: {'==' if info['exact_count'] else '>='}"
            s += f"{info['count']}"
            if not info["exact_count"]:
                s += f" frequency: {info['freq']}"
            s += "\n"
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

    parser.add_argument("-t", "--threshold",
                        action="store", type=float, default=3.0,
                        help="zipf_frequency() threshold for words to include")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")

    subparsers = parser.add_subparsers(help='sub-command help')

    parser_auto = subparsers.add_parser('auto', help=cmd_auto.__doc__)
    parser_auto.set_defaults(func=cmd_auto)
    parser_auto.add_argument("-a", "--all",
                             action="store_true", default=False,
                             help="Try each word in dictionary")
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
    s = w.solver()
    s.handle_response(args.word[0], args.result[0])
    print("\n".join(list(s.possible)))
    return(0)


def play_game(w, word, debug=False):
    """Try to solve word.

    Return True, number of guesses if succesful. False otherwise.
    """
    s = w.solver()
    for guess_num in range(w.guess_limit):
        guess = s.generate_guess(guess_num + 1)
        if debug:
            print(f"Guessing {guess}")
        success, response = w.generate_response(word, guess)
        if success:
            return True, guess_num+1
        if debug:
            print(f"   ...response: {w.colorize_reponse(response)}")
        s.handle_response(guess, response)
        if debug:
            if len(s.possible) < 10:
                print(f"   ...{len(s.possible)} left: {' '.join(s.possible)}")
            else:
                print(f"   ...{len(s.possible)} left.")
    return False, 0


def cmd_auto(w, args):
    """Automatically play numerous games and report how we do"""
    results = []
    failures = []
    if args.all:
        words = w.word_list()
    elif args.word:
        words = itertools.repeat(args.word, args.num_games)
    else:
        words = random.choices(w.word_list(), k=args.num_games)
    for game, word in enumerate(words):
        print(f"Game {game+1}:{word}")
        result, guess_num = play_game(w, word, args.debug)
        if result:
            print(f"{Colors.green}   ...got {word} in {guess_num} guesses"
                  f"{Colors.reset}")
            results.append(guess_num)
        else:
            print(f"{Colors.red}   ...failed to get {word}.{Colors.reset}")
            failures.append(word)
    tally = collections.Counter(results)
    for n in range(w.guess_limit):
        print(f"{n+1} guesses: {tally.get(n+1, 0)}")
    try:
        average = statistics.fmean([result+1 for result in results
                                    if result < w.guess_limit])
        print(f"Average: {average}")
    except statistics.StatisticsError:
        # All failures
        pass
    print(f"Failures: {len(failures)} : {' '.join(failures)}")


def cmd_assist(w, args):
    """Assst with playing Wordle"""
    s = w.solver()
    s.assist()
    return(0)


def main(argv=None):
    parser = make_argparser()
    args = parser.parse_args(argv if argv else sys.argv[1:])
    w = Wordle(debug=args.debug, threshold=args.threshold)
    return args.func(w, args)


if __name__ == "__main__":
    sys.exit(main())
