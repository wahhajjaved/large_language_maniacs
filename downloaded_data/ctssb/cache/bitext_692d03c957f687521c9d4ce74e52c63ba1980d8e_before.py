from util.trace import Trace
from util.elasticsearch import Elasticsearch
from util.csv_manager import CsvManager
import os.path
import sys
import unittest

class MainScript(object):
	"Builds the three elasticsearch indexes of the bitext prototype and the relations among them"

	# path of the files
	filedir = os.path.dirname(os.path.realpath(__file__))
	hotels_file = os.path.join(filedir,"./data/hotels.csv")
	comments_file = os.path.join(filedir,"./data/comments.csv")
	bitext_file = os.path.join(filedir,"./data/bitext_tuipilot.csv")
	# indexes
	hotels_index = "hotels"
	comments_index = "comments"
	bitext_index = "bitext"
	bitext_unique_index = "bitext_unique"
	bitext_unique_posneg_index = "bitext_unique_posneg"
	# elasticsearch instance
	elasticsearch = Elasticsearch("localhost", 9200)

	def __init__(self, test=False):
		"Inits the script"

		Trace.info("Starting" + (" ", " test")[test] +" script...")
		# change paths and indexes in case of test
		if test:
			# path of the files
			self.hotels_file = os.path.join(self.filedir,"./data/hotels_test.csv")
			self.comments_file = os.path.join(self.filedir,"./data/comments_test.csv")
			self.bitext_file = os.path.join(self.filedir,"./data/bitext_tuipilot_test.csv")
			# indexes
			self.hotels_index = "test_hotels"
			self.comments_index = "test_comments"
			self.bitext_index = "test_bitext"
			self.bitext_unique_index = "test_bitext_unique"
			self.bitext_unique_posneg_index = "test_bitext_unique_posneg"
		
		# hotels first
		self.build_hotels_index()
		# then comments
		self.build_comments_index()
		# then the rest
		self.build_bitext_indexes()

		Trace.info(("S", "Test s")[test] + "cript finished.")

	def build_hotels_index(self):
		Trace.info("Building hotels index...")
		# build the typemap
		hotels_keys = CsvManager.read_keys(self.hotels_file)
		hotels_typemap = dict(zip(hotels_keys[3:], [int]*len(hotels_keys[3:])))
		hotels_replace = [{"pos":0, "find":".", "replace":""}]
		# get the bulk of documents
		hotels = CsvManager.read(self.hotels_file, typemap=hotels_typemap, replace=hotels_replace)
		Trace.info(str(len(hotels)) + " hotels read")
		# bulk_upsert
		hotels_upserted = self.elasticsearch.upsert_bulk(self.hotels_index, "destinationCode", "hotelSequence", hotels)
		Trace.info(str(hotels_upserted) + " hotels upserted in " + self.hotels_index)

	def build_comments_index(self):
		Trace.info("Building comments index...")
		# build the typemap
		comments_typemap = {"averageWebScore": int}
		comments_replace = [{"pos":0, "find":".", "replace":""}, {"pos":1, "find":".", "replace":""}]
		# get the bulk of documents
		comments = CsvManager.read(self.comments_file, typemap=comments_typemap, replace=comments_replace)
		Trace.info(str(len(comments)) + " comments read")
		# bulk_upsert
		comments_upserted = self.elasticsearch.upsert_bulk(self.comments_index, "commentId", "hotelSequence", comments)
		Trace.info(str(comments_upserted) + " comments upserted in " + self.comments_index)
	
	def build_bitext_indexes(self):
		"Builds bitext, bitext_unique and bitext_unique_posneg indexes"
		Trace.info("Building bitext, bitext_unique and bitext_unique_posneg indexes...")
		# typemap and replace
		bitext_replace = [{"pos":10, "find":",", "replace":"."}]
		bitext_typemap = {"score": float}
		# get the bulk of bitexts
		bitexts = CsvManager.read(self.bitext_file, typemap=bitext_typemap, replace=bitext_replace)
		# iterate the bulk of bitexts and insert the element in each of the indexes
		for _id,bitext_item in enumerate(bitexts):
			# add info from hotels
			hotel = self.elasticsearch.read_document(self.hotels_index, "_all", bitext_item["hotelSequence"])
			if "found" in hotel and hotel["found"]:
				# add found hotel fields to bitext item
				bitext_item = dict(bitext_item.items() + hotel["_source"].items())
			# upsert element
			bitext_type = bitext_item["section"]
			del bitext_item["section"]
			self.elasticsearch.upsert_document(self.bitext_index, bitext_type, str(_id), bitext_item)
			# update bitext_unique_posneg index
			previous_average_score = 0
			previous_count = 0
			previous_categories = ""
			separator = ""
			bitext_unique_posneg_id = bitext_item["commentId"] + bitext_type
			bitext_unique_posneg_item = self.elasticsearch.read_document(self.bitext_unique_posneg_index, "_all", bitext_unique_posneg_id)
			if "found" in bitext_unique_posneg_item and bitext_unique_posneg_item["found"]:
				previous_count = bitext_unique_posneg_item["_source"]["count"]
				previous_average_score = bitext_unique_posneg_item["_source"]["averageScore"]
				previous_categories = bitext_unique_posneg_item["_source"]["category"]
				separator = ", "
			bitext_unique_posneg_upsert_doc = {
				"section": bitext_type,
				"averageScore": 1.0*(previous_average_score*previous_count + bitext_item["score"])/(previous_count + 1),
				"count": previous_count + 1,
				"category": previous_categories + separator + bitext_item["category"]
			}
			# upsert
			self.elasticsearch.upsert_document(self.bitext_unique_posneg_index, bitext_item["hotelSequence"], bitext_unique_posneg_id, bitext_unique_posneg_upsert_doc)
			# update bitext_unique index
			previous_average_score = 0
			previous_count = 0
			previous_categories = ""
			separator = ""
			bitext_unique_id = bitext_item["commentId"]
			bitext_unique_item = self.elasticsearch.read_document(self.bitext_unique_index, "_all", bitext_unique_id)
			if "found" in bitext_unique_item and bitext_unique_item["found"]:
				previous_count = bitext_unique_item["_source"]["count"]
				previous_average_score = bitext_unique_item["_source"]["averageScore"]
				previous_categories = bitext_unique_item["_source"]["category"]
				separator = ", "
			bitext_unique_upsert_doc = {
				"averageScore": 1.0*(previous_average_score*previous_count + bitext_item["score"])/(previous_count + 1),
				"count": previous_count + 1,
				"category": previous_categories + separator + bitext_item["category"]
			}
			# look for the comment in the comment index
			comment = self.elasticsearch.read_document(self.comments_index, "_all", bitext_unique_id)
			if "found" in comment and comment["found"]:
				# add found comment averageWebScore to bitext unique item
				bitext_unique_upsert_doc["averageWebScore"] = comment["_source"]["averageWebScore"]
			# upsert
			self.elasticsearch.upsert_document(self.bitext_unique_index, bitext_item["hotelSequence"], bitext_unique_id, bitext_unique_upsert_doc)




###############################################
################ UNIT TESTS ###################
###############################################
class MainScriptTests(unittest.TestCase):
    "Main script unit tests"

    def test_script(self):
    	MainScript(test = True)
    	elasticsearch = Elasticsearch("localhost", 9200)
    	# test hotels index
    	hotel148611 = elasticsearch.read_document("test_hotels", "BAI", "148611")
    	self.assertTrue(hotel148611["found"])
    	self.assertEquals(hotel148611["_source"]["mailsEnviados"], 11)
    	# test comments index
    	comment330952 = elasticsearch.read_document("test_comments", "148611", "330952")
    	self.assertTrue(comment330952["found"])
    	self.assertEquals(comment330952["_source"]["averageWebScore"], 4)
    	# test bitext index
    	count_bitext = elasticsearch.count("test_bitext")
    	self.assertEquals(count_bitext, 9)
    	last_bitext = elasticsearch.read_document("test_bitext", "POS", "9")
    	self.assertEquals(last_bitext["_source"]["score"], 2.0)
    	self.assertEquals(last_bitext["_source"]["mailsEnviados"], 37)
    	# test bitext_unique_posneg index
    	bitext330956POS = elasticsearch.read_document("test_bitext_unique_posneg", "69559", "330956POS")
    	self.assertTrue(bitext330956POS["found"])
    	self.assertEquals(bitext330956POS["_source"]["averageScore"], 2.0)
    	# test bitext_unique index
    	bitext330956 = elasticsearch.read_document("test_bitext_unique_posneg", "69559", "330956")
    	self.assertTrue(bitext330956["found"])
    	self.assertEquals(bitext330956["_source"]["averageScore"], 2.0)

    def tearDown(self):
    	# delete indexes
    	elasticsearch = Elasticsearch("localhost", 9200)
    	elasticsearch.remove_index("test_hotels")
    	elasticsearch.remove_index("test_comments")
    	elasticsearch.remove_index("test_bitext")
    	elasticsearch.remove_index("test_bitext_unique_posneg")
    	elasticsearch.remove_index("test_bitext_unique")

if __name__ == '__main__':
	unittest.main()
	#if len(sys.argv)>1 and sys.argv[1] == "test":
	#	Trace.info("test")
	#	unittest.main()
	#else:
	#	Trace.info("main")
    #	MainScript()