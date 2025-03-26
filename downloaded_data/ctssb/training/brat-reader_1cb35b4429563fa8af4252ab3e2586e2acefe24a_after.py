class Attribution(dict):

	def __init__(self, parc_corenlp_document, *args, **kwargs): 
		# This class is basically a dictionary, but it keeps a special
		# Reference, as an attribute, to the document in which the textual
		# attribution arises.
		super(Attribution, self).__init__(*args, **kwargs)
		self.document = parc_corenlp_document

	def get_sentence_ids(self):
		all_span_tokens = self['cue'] + self['source'] + self['content']
		sentence_ids = {t['sentence_id'] for t in all_span_tokens}
		return sentence_ids

	def __eq__(self, other):
		"""
		See the docstring for corenlp_xml_reader.Sentence.__eq__().
		"""
		return id(self) == id(other)

	def __ne__(self, other):
		return not self.__eq__(other)
