# The parse tree is made up of several trees and dictionaries mapped together. While it may look complicated, the
# overall structure is relatively simple. When the parse begins, it looks at the first character, and checks the tree.
# If the character maps to a list, then the parser knows it has reached a leaf and can check HIRAGANA_INDEX of the list
# to get the hiragana character, or KATAKANA_INDEX for the katakana character. If it maps to another dictionary, the
# parser knows it has to look at the next character to determine what the final character(s) should be.

# Note: Some characters can only be represented by katakana, and are invalid in hiragana. The parser can check the 
# HAS_HIRAGANA index for a boolean that indicates if the character has a hiragana equivalent.

HAS_HIRAGANA   = 0
HIRAGANA_INDEX = 1
KATAKANA_INDEX = 2

parse_tree ={
                # Top level vowels. These always map one-to-one if they are the first character.
                'a': [True, 'あ', 'ア'],
                'i': [True, 'い', 'イ'],
                'u': [True, 'う', 'ウ'],
                'e': [True, 'え', 'エ'],
                'o': [True, 'お', 'オ'],

                'k': {
                        'a': [True, 'か', 'カ'],
                        'i': [True, 'き', 'キ'],
                        'u': [True, 'く', 'ク'],
                        'e': [True, 'け', 'ケ'],
                        'o': [True, 'こ', 'コ'],

                        'y': {
                                'a': [True, 'きゃ', 'キャ'],
                                'u': [True, 'きゅ', 'キュ'],
                                'o': [True, 'きょ', 'キョ'],
                            }
                     },
                'n': {
                        'a': [True, 'な', 'ナ'],
                        'i': [True, 'に', 'ニ'],
                        'u': [True, 'ぬ', 'ヌ'],
                        'e': [True, 'ね', 'ネ'],
                        'o': [True, 'の', 'ノ'],

                        'y': {
                                'a': [True, 'にゃ', 'ニャ'],
                                'u': [True, 'にゅ', 'ニュ'],
                                'o': [True, 'にょ', 'ニョ'],
                             }
                     },
                's': {
                        'a': [True, 'さ', 'サ'],
                        'u': [True, 'す', 'ス'],
                        'e': [True, 'せ', 'セ'],
                        'o': [True, 'そ', 'ソ'],

                        'h': {
                                'a': [True, 'しゃ', 'シャ'],
                                'i': [True, 'し', 'シ'],
                                'u': [True, 'しゅ', 'シュ'],
                                'o': [True, 'しょ', 'ショ'],
                             }
                     },
                'z': {
                        'a': [True, 'ざ', 'ザ'],
                        'i': [True, 'じ', 'ジ'],
                        'u': [True, 'ず', 'ズ'],
                        'e': [True, 'ぜ', 'ゼ'],
                        'o': [True, 'ぞ', 'ゾ'],
                     },
                'j': {
                        'a': [True, 'じゃ', 'ジャ'],
                        'i': [True, 'じ', 'ジ'],
                        'u': [True, 'じゅ', 'ジュ'],
                        'o': [True, 'じょ', 'ジョ'],
                     },
                't': {
                        'a': [True, 'た', 'タ'],
                        'e': [True, 'て', 'テ'],
                        'o': [True, 'と', 'ト'],

                        's': {
                                'u': [True, 'つ', 'ツ'],
                             }
                     },
                'd': {
                        'a': [True, 'だ', 'ダ'],
                        'i': [True, 'ぢ', 'ヂ'],
                        'u': [True, 'づ', 'ヅ'],
                        'e': [True, 'で', 'デ'],
                        'o': [True, 'ど', 'ド'],
                     },
                'c': {
                        'h': {
                                'a': [True, 'ちゃ', 'チャ'],
                                'i': [True, 'ち', 'チ'],
                                'u': [True, 'ちゅ', 'チュ'],
                                'o': [True, 'ちょ', 'チョ'],
                             }
                     },
                'h': {
                        'a': [True, 'は', 'ハ'],
                        'i': [True, 'ひ', 'ヒ'],
                        'u': [True, 'ふ', 'フ'],
                        'e': [True, 'へ', 'ヘ'],
                        'o': [True, 'ほ', 'ホ'],

                        'y': {
                                'a': [True, 'ひゃ', 'ヒャ'],
                                'u': [True, 'ひゅ', 'ヒュ'],
                                'o': [True, 'ひょ', 'ヒョ'],
                             }
                     },
                'b': {
                        'a': [True, 'ば', 'バ'],
                        'i': [True, 'び', 'ビ'],
                        'u': [True, 'ぶ', 'ブ'],
                        'e': [True, 'べ', 'ベ'],
                        'o': [True, 'ぼ', 'ボ'],

                        'y': {
                                'a': [True, 'びゃ', 'ビャ'],
                                'u': [True, 'びゅ', 'ビュ'],
                                'o': [True, 'びょ', 'ビョ'],
                             }
                     },
                'p': {
                        'a': [True, 'ぱ', 'パ'],
                        'i': [True, 'ぴ', 'ピ'],
                        'u': [True, 'ぷ', 'プ'],
                        'e': [True, 'ぺ', 'ペ'],
                        'o': [True, 'ぽ', 'ポ'],

                        'y': {
                                'a': [True, 'ぴゃ', 'ピャ'],
                                'u': [True, 'ぴゅ', 'ピュ'],
                                'o': [True, 'ぴょ', 'ピョ'],
                             }
                     },
                'f': {
                        'u': [True, 'ふ', 'フ'],
                     },
                'm': {
                        'a': [True, 'ま', 'マ'],
                        'i': [True, 'み', 'ミ'],
                        'u': [True, 'む', 'ム'],
                        'e': [True, 'め', 'メ'],
                        'o': [True, 'も', 'モ'],

                        'y': {
                                'a': [True, 'みゃ', 'ミャ'],
                                'u': [True, 'みゅ', 'ミュ'],
                                'o': [True, 'みょ', 'ミョ'],
                             }
                     },
                'y': {
                        'a': [True, 'や', 'ヤ'],
                        'u': [True, 'ゆ', 'ユ'],
                        'o': [True, 'よ', 'ヨ'],
                     },
                'r': {
                        'a': [True, 'ら', 'ラ'],
                        'i': [True, 'り', 'リ'],
                        'u': [True, 'る', 'ル'],
                        'e': [True, 'れ', 'レ'],
                        'o': [True, 'ろ', 'ロ'],

                        'y': {
                                'a': [True, 'りゃ', 'リャ'],
                                'u': [True, 'りゅ', 'リュ'],
                                'o': [True, 'りょ', 'リョ'],
                             }
                     },
                'w': {
                        'a': [True, 'わ', 'ワ'],
                        'o': [True, 'を', 'ヲ'],
                     },
                'g': {
                        'a': [True, 'が', 'ガ'],
                        'i': [True, 'ぎ', 'ギ'],
                        'u': [True, 'ぐ', 'グ'],
                        'e': [True, 'げ', 'ゲ'],
                        'o': [True, 'ご', 'ゴ'],

                        'y': {
                                'a': [True, 'ぎゃ', 'ギャ'],
                                'u': [True, 'ぎゅ', 'ギュ'],
                                'o': [True, 'ぎょ', 'ギョ'],
                             }
                     },
        }

TSU_CONSONANTS = ['k', 's', 'z', 'j', 't', 'd', 'c', 'h', 'b', 'f', 'm', 'y', 'r', 'w', 'g']

HIRAGANA = False
KATAKANA = True


def convert_to_kana(romaji: str, kana: bool = HIRAGANA) -> str:
    output_str = ''
    index = 0
    while index != len(romaji):
        temp = parse_tree

        # Special case conditions for adding a small つ on double consonants
        if index <= len(romaji)-2 and romaji[index] == romaji[index+1] and romaji[index] in TSU_CONSONANTS:
            if kana is KATAKANA:
                output_str += 'ッ'
            else:
                output_str += 'っ'
            index += 1
            continue

        # Unfortunately, special logic is also needed to handle singular ん and double-consonant n-types.
        if romaji[index] == 'n':
            if index+1 == len(romaji) or romaji[index+1] == 'n' or romaji[index+1] in TSU_CONSONANTS:
                if kana is KATAKANA:
                    output_str += 'ン'
                else:
                    output_str += 'ん'
                index += 1
                continue

        while type(temp) != list:
            temp = temp[romaji[index]]
            index += 1

        if kana is KATAKANA:
            output_str += temp[KATAKANA_INDEX]
        else:
            if temp[HAS_HIRAGANA]:
                output_str += temp[HIRAGANA_INDEX]
            else:
                raise ValueError("Invalid romaji to hiragana conversion. Romaji: " + romaji)
    return output_str


if __name__ == '__main__':
    romaji = input('Please input some romaji [q to quit]: ').lower()
    while romaji is not 'q':
        print(convert_to_kana(romaji))
        print(convert_to_kana(romaji, kana=KATAKANA))
        romaji = input('Please input some romaji [q to quit]: ').lower()
