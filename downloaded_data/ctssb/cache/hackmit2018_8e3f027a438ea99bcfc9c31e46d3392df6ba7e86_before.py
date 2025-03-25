308395613

import numpy as np
from scipy.io import wavfile
import pickle
import re
from generate_data_structs import phonemes_for

# For this method, we want to split the input text
def ispunc(word):
	for char in word:
		if char.isalnum():
			return False
	return True

def generate_audio_out(input_text, phoneme_clips):
	words = re.findall(r"[\w']+|[.,!?;]", input_text)
	clips = []

	for word in words:
		if not ispunc(word):
			clips.append(generate_audio_for_word(word, phoneme_clips))
		clips.append(np.zeros(10))
	return stitch_audio(clips)

def generate_audio_for_word(word, phoneme_clips):
	# get the phonemes
	phonemes = phonemes_for(word)
	# convert each phoneme to audio clip
	audio_clips = [phoneme_clips[pho] for pho in phonemes]
	# stitch together and return
	return stitch_audio(audio_clips)

def stitch_audio(audio_clips):
	"""
	Stitches together a list of audio clips, each of which is a numpy array of waveform values

	Implementation: naively concatenate together the clips
	"""
	np.concatenate(audio_clips)

def generate_audio_wav(input_text, phoneme_clips):
	wavfile.write("media/output.wav", 44000, generate_audio_out(input_text, phoneme_clips))

if __name__ == "__main__":
	print("This program lets you make NAME HERE pronounce anything!")

	with open("phoneme_dict.p", 'rb')as p:
		phoneme_clips = pickle.load(p)
	again = 'y'

	while (again.lower() == 'y'):
		input_text = input("Enter text you want to generate speech for: ")

		generate_audio_wav(input_text, phoneme_clips)

		again = input("Audio generated! Generate more? (Y/N): ")
