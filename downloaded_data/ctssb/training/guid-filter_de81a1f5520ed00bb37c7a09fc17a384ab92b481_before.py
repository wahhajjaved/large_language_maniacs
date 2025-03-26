from transformations import vowel_expand, drop_vowel, l33t, words_with_ck, repeat_to_single
from process import wordlist
import itertools
ALPHABET = '23456789abcdefghijkmnpqrstuvwxyz'
BLACKLIST = wordlist.words


def main():
    blacklist = set(generate_blacklist(BLACKLIST, min_length=2, max_length=5))
    combinations = get_combinations(2)
    bad_guids = generate_guids(blacklist, combinations=combinations, length=5)


def generate_blacklist(blacklist, min_length, max_length):
    result = [w for w in blacklist if min_length < len(w) <= max_length]
    print('Generating blacklist...')
    n = 1
    total = len(blacklist)
    for word in blacklist:
        print('Processing word {0}/{1}'.format(n, total))
        n += 1
        if len(word) <= max_length:
            result += vowel_expand(word, 3)
            result += words_with_ck(word)
            result += l33t(word)
        result += drop_vowel(word)
        result += repeat_to_single(word)
    return result


def get_combinations(length, alphabet=ALPHABET):
    combinations = {}
    for x in range(length):
        combinations[x + 1] = list(itertools.product(alphabet, repeat=(x+1)))
    return combinations


def generate_guids(words, combinations=None, length=5, alphabet=ALPHABET):
    guids = set()

    if not combinations:
        combinations = get_combinations(2, alphabet)

    if not isinstance(words, list):
        words = [words]

    for word in words:
        if len(word) == length:
            guids.add(words)
        else:
            positions = n_positions(word, length)
            n_random = length - len(word)
            for c in combinations[n_random]:
                for i in range(0, positions):
                    word_list = create_word_list(word, i)
                    available_indices = [i for i, x in enumerate(word_list) if not x]
                    for idx in available_indices:
                        index = available_indices.index(idx)
                        word_list[idx] = c[index]
                    result = ''.join(word_list)
                    if len(result) > length:
                        raise Exception
                    guids.add(result)
    return guids


def create_word_list(word, index):
    word_list = [None] * 5

    for letter in word:
        word_list[index] = letter
        index += 1
    return word_list


def n_positions(word, length):
    return length - len(word) + 1


if __name__ == '__main__':
    main()

