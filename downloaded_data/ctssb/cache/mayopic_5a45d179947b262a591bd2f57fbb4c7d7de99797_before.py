import os, sys
import Image

class imageProcess:

	def __init__(self):
		self.fileName = ""
		self.newSize = 25
		
	def pixelate(self):
		orgImage = Image.open(self.fileName)
		orgSize = orgImage.size
		
		ratio = min (orgSize[0]/self.newSize, orgSize[1]/self.newSize)
		Size = orgSize[0]/ratio, orgSize[1]/ratio

		orgImage.thumbnail(Size)

		orgImage.save(self.fileName+".pixl", "PNG")

		newImage = Image.open(self.fileName+".pixl")
		newImage = newImage.resize(orgSize)
		newImage.save(self.fileName+".pixl", "PNG")
		
	def crop(self):
		orgImage = Image.open(self.fileName)
		orgSize = orgImage.size
		
		ratio = min (orgSize[0]/self.newSize, orgSize[1]/self.newSize)
		Size = orgSize[0]*5/ratio, orgSize[1]*5/ratio
		
		newImage = orgImage.crop((orgSize[0]/2-Size[0]/2, orgSize[1]/2-Size[1]/2, orgSize[0]/2+Size[0]/2, orgSize[1]/2+Size[1]/2))
		
		newImage = newImage.resize(orgSize)
		newImage.save(self.fileName+".crop", "PNG")
		newImage.save(self.fileName+".crop", "PNG")
		
	def incrementSize(self, increment):
		self.newSize+=1

'''		
if __name__ == "__main__":
	ip = imageProcess();
	ip.fileName = sys.argv[1]
	ip.newSize = int(sys.argv[2])
	ip.pixelate()
	ip.crop()
'''
