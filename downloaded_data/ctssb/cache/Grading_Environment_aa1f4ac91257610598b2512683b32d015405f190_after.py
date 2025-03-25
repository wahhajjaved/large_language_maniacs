import os
from shutil import copytree
from FileManipulation import makeDirectory

#Checks to see if a folder has the java code
#Makes sure that it does not include Test.java because student may place
#Test code in a different folder than where the actual code is at
def doesFolderContainCode(folder):
    try:
        print(folder)
        for file in os.listdir(os.fsencode(folder)):
            filename = os.fsdecode(file)
            if filename.endswith(".java"):
                if not filename.endswith("Test.java"):
                    return True
        return False
    except OSError as e:
        return False

#Gets a student directory and places all the code into folderWhereSrcShouldBe
def placeFilesInCorrectLoc(studentFolder, folderWhereSrcShouldBe):
    inCorrectPlace = doesFolderContainCode("./" + studentFolder + "/" + folderWhereSrcShouldBe)
    if inCorrectPlace:
        return True

    for root, dirs, files in os.walk("./" + studentFolder):
        if doesFolderContainCode(root):
            copytree(root, './' + studentFolder + "/" + folderWhereSrcShouldBe)
            return True
    return False
