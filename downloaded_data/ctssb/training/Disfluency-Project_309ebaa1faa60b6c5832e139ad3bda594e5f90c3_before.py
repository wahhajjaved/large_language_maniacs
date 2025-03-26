import os
def readData(dir_name):
    sentList = []
    sent = []
    label = set()
    for file in os.listdir(dir_name):
        with open(dir_name+'/'+file, 'r') as reader:
            for line in reader:
                content = line.strip()
                if content == '':
                    sentList.append(sent)
                    sent = []
                else:
                    tokens=content.split()
                    label.add(tokens[6])
                    sent.append([tokens[2],tokens[3], tokens[6]])
        if len(sent) > 0:
            sentList.append(sent)
            sent = []

    return sentList

def preProcess(sents):
    newSents=[]
    for sent in sents:
        sent1=[]
        sent2=[]
        for t in sent:
            if not t[0].endswith('-') and not t[0]=='SILENCE' and not t[0]=='TRACE' and not t[1]==None:
                sent1.append(t)
        for (i,t) in enumerate(sent1):
            if t[2]=='+':
                if i==0 or not sent1[i-1][2]=='+':
                    if i==len(sent1)-1 or not sent1[i+1][2]=='+':
                        sent2.append([t[0], t[1], 'BE_IP'])
                    else:
                        sent2.append([t[0],t[1],'BE'])
                elif i==len(sent1)-1 or not sent1[i+1][2]=='+':
                    sent2.append([t[0], t[1], 'IP'])
                else:
                    sent2.append([t[0], t[1], 'IE'])
            elif t[2]=='-':
                sent2.append([t[0], t[1], 'OR'])
            else:
                assert(t[2]=='None')
                sent2.append([t[0], t[1], 'O'])
        newSents.append(sent2)
    return newSents

def writeSents(sents,file):
    with open(file,'w') as writer:
        for sent in sents:
            for seq in list(zip(*sent)):
                writer.write('\t'.join(seq)+'\n')
            writer.write('\n')

trainSents=preProcess(readData('train'))
valSents=preProcess(readData('val'))
testSents=preProcess(readData('test'))
writeSents(trainSents,'train.txt')
writeSents(valSents,'val.txt')
writeSents(testSents,'test.txt')




