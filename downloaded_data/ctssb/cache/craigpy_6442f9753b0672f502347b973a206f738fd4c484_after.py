class __Node__:    
    def __init__(self, char, term=False):
        self.value = char
        self.kids = {}
        self.isTerminal = term
        
    def __str__(self):
        return self.value
    
    def __contains__(self,word,index):  
        if index == len(word):
            return self.isTerminal
        char = word[index]
        if char not in self.kids:
            return False
        else:
            child = self.kids[char]
            return child.__contains__(word,index+1)
    
    def __insert__(self,word,index):
        if index == len(word):
            self.isTerminal = True
            return True
        char = word[index]
        if char in self.kids:
            child = self.kids[char]
        else:
            child = __Node__(char)
            self.kids[char] = child
        return child.__insert__(word,index+1)
        
    def __print_tree__(self, depth):
        print "-" * depth + self.value
        for child in self.kids.itervalues():
            child.__print__(depth+1)
    
    def __print_words__(self, word):
        if self.isTerminal:
            print word
        keys = self.kids.keys()
        keys.sort()
        for k in keys:
            self.kids[k].__print_words__(word + k)
    
class Trie:
    def __init__(self):
        self.count = 0
        self.head = __Node__("")
        
    def size(self):
        return self.count
    
    def contains(self, word):
        if word == "":
            return True
        return self.head.__contains__(word,0)
    
    def insert(self, word):
        if word == "":
            return False
        if self.contains(word):
            return False
        if self.head.__insert__(word,0):
            self.count = self.count + 1
            return True
        else:
            return False
    
    def print_tree(self):
        print "TRIE\n===="
        self.head.__print_tree__(-1)

    def print_words(self):
        print "WORDS\n====="
        self.head.__print_words__("")
