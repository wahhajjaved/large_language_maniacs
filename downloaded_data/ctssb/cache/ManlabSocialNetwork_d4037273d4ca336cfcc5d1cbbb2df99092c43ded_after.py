import sys
import scipy as sp
import numpy as np
import tensorflow as tf
import scipy.optimize
import numpy.random
import datetime

def debug_signal_handler(signal, frame):
    import pdb
    pdb.set_trace()
import signal
signal.signal(signal.SIGINT, debug_signal_handler)

single = True
filename = int(sys.argv[1])
if filename < 0:
	single = False
alpha = float(sys.argv[2]) #learning rate for optimizer

users = 7268
allusers = 7268
ts = 1321286400 #start timestamps
te = 1322150400 #end timestamps
uid = list() #from user index to user id
iddic = {} #from user id to user index
friend = {} #from user id to its followers' user id
rusc = list() #info part of rusc sets and records
nrusc = list() #info part of nrusc sets and records
rusc_id = list() #id part of rusc sets and records
nrusc_id = list() #id part of nrusc sets and records
rusc_dic = list() #from cascade id to index list of rusc info
nrusc_dic = list() #from cascade id to index list of nrusc info
begin_rusc = list()
end_rusc = list()
begin_nrusc = list()
end_nrusc = list()
depth = {} #from tweet id to depth
author = {} #from tweet id to user id
cascade_author = list()
timestamp = {} #from tweet id to timestamp
posts = {} #from user index to post times
q = list() #from cascade id to q function
tempq = list()
lc = list() #from cascade id to log-likelihood function value
cdic = {} #from cascade id to cascade index
clist = list() #from cascade index to cascade id
edgemap = {} #from relations to the index of edge
vdic = {} #from user index to the index of point parameter 
edic = {} #from the index of edge to the index of edge parameter
vlist = list() #from the index of point parameter to user index
vlist_tf = list()
elist = list() #from the index of edge parameter to the index of edge
vnum = 0
enum = 0
cnum = 0
rusc_num = 0
nrusc_num = 0
cas_num = 0
pos = 0
poslist = list()
total = 0
iters = 1 #iteration times in each M-steps
factor = -1

epsilon = 10.0 #when will EM stop
lbd = np.zeros(users) #parameter lambda which have calculated before
count = 0

def LnLc(beta, c): #ln fromulation of one cascades's likelihood on tau(do not include part of Q)
	#uc = cascade_author[c]
	#tempgamma = gamma[uc]
	#tmpphi = philist[uc]
	#s = tf.cast(tf.log(fakeq) + tf.log(lbd[vlist_tf[uc]]), dtype=tf.float64)
	#print tf.shape(s)

	br = begin_rusc[c]
	bn = begin_nrusc[c]
	er = end_rusc[c]
	en = end_nrusc[c]
	rc_id = tf.gather(rusc_id, rusc_dic[br:er], axis=0)
	nc_id = tf.gather(nrusc_id, nrusc_dic[bn:en], axis=0)

	beta_rc = tf.gather(beta, rc_id[:, 0], axis=0)
	beta_nc = tf.gather(beta, nc_id[:, 0], axis=0)
	#x_rc = tf.gather(x, rc_id[:, 0], axis=0)
	#phi_rc = tf.gather(q, rc_id[:, 1], axis=0)
	s = tf.reduce_sum(tf.concat([tf.log(beta_rc), tf.log(1-beta_nc)], 0))


	return s

def printInfo(obj, i, noreply):
	print str(i) + ' ' + str(obj) + ' ' + str(noreply)

def cond(obj, i, beta, gamma):
	return i < cas_num

def body(obj, i, beta, gamma):
	#if rusc_dic[i].get_shape()[0] == 0:
	uc = cascade_author[i]
	tempgamma = gamma[uc]
	if begin_rusc[i] == end_rusc[i]:
		llh = tf.exp(LnLc(beta, i)) + tempgamma
		obj -= tf.log(tmp)
	else:
		#obj += tf.reduce_sum(fakeq * tf.log(fakeq))
		obj -= LnLc(beta, i)
	i += 1
	#tf.py_func(printInfo, [obj, i, noreply], tf.float64)
	return obj, i, beta, gamma

def ObjF(param): #formulation of objective function (include barrier) (the smaller the better)
	beta = param[:enum]
	gamma = param[enum:]
	beta = tf.cos(beta) * tf.cos(beta)
	gamma = tf.cos(gamma) * tf.cos(gamma)
	#omega = tf.cos(omega) * tf.cos(omega)
	#pi = tf.cos(pi) * tf.cos(pi)
	#x = x * x
	#global total
	#total += 1
	it = tf.cast(0, dtype=tf.int32)
	#noreply = tf.cast(0, dtype=tf.float64)
	#it = tf.Variable(0)
	#noreply = tf.Variable(0.0)
	'''
	print 'Begin'
	print omega
	print x
	print pi
	'''
	#obj = factor * (tf.log(beta) + tf.log(1-beta) + tf.log(gamma) + tf.log(1-gamma)) #need to be fixxed
	obj = tf.cast(0, dtype=tf.float64)
	newobj, _, _, _ = tf.while_loop(cond, body, [obj, it, beta, gamma], parallel_iterations=80)
		
	#if total % 10000 == 0:
	#	print 'No.' + str(total) + ' times: ' + str(obj)
	return newobj

def SingleObj(data, u):
	global vnum, enum, cnum, rusc_num, nrusc_num
	n = len(data)
	#last = int(data[1].split('\t')[2])
	i = 0
	while i < n:
		temp = data[i].split('\t')
		number = int(temp[1]) + 1
		rusc_dic.append(list())
		nrusc_dic.append(list())
		clist.append(temp[0])
		cdic[temp[0]] = cnum
		q.append([0.2, 0.2, 0.2, 0.2, 0.2])
		#lc.append([0.0, 0.0, 0.0, 0.0, 0.0])
		#lc[temp[0]] = np.array(lc[temp[0]])
		#q[temp[0]] = np.array(q[temp[0]])
		casdic = {} #from tweet id to user id who replied it with which tweet id
		for j in range(i+1, i+number):
			tweet = data[j].split('\t')
			#print tweet
			author[tweet[0]] = tweet[1]
			timestamp[tweet[0]] = int(tweet[2])
			if not vdic.has_key(iddic[tweet[1]]):
				vdic[iddic[tweet[1]]] = vnum
				vnum += 1
				vlist.append(iddic[tweet[1]])
			if not casdic.has_key(tweet[0]):
				casdic[tweet[0]] = {}
			if tweet[3] == '-1':
				depth[tweet[0]] = 0
			else:
				depth[tweet[0]] = depth[tweet[3]] + 1
				casdic[tweet[3]][tweet[1]] = tweet[0]
		for item in casdic:
			#print item
			#print author[item]
			#print friend[author[item]]
			if not friend.has_key(author[item]):
				continue
			for f in friend[author[item]]:
				if not edic.has_key(edgemap[iddic[author[item]]][iddic[f]]):
					edic[edgemap[iddic[author[item]]][iddic[f]]] = enum
					enum += 1
					elist.append(edgemap[iddic[author[item]]][iddic[f]])
				if not vdic.has_key(iddic[f]):
					vdic[iddic[f]] = vnum
					vnum += 1
					vlist.append(iddic[f])
				info = list()
				info_id = list()
				if f in casdic[item]: #this person retweeted it
					info_id.append(edic[edgemap[iddic[author[item]]][iddic[f]]])
					info.append(timestamp[casdic[item][f]] - timestamp[item])
					info.append(depth[item])
					info_id.append(vdic[iddic[f]])
					rusc.append(info)
					rusc_id.append(info_id)
					rusc_dic[cdic[temp[0]]].append(rusc_num)
					rusc_num += 1
				else: #this person did not retweet it
					info_id.append(edic[edgemap[iddic[author[item]]][iddic[f]]])
					info.append(te - timestamp[item])
					info.append(depth[item])
					info_id.append(vdic[iddic[f]])
					nrusc.append(info)
					nrusc_id.append(info_id)
					nrusc_dic[cdic[temp[0]]].append(nrusc_num)
					nrusc_num += 1
		cnum += 1
		i += number		


#Get lambda value
starttime = datetime.datetime.now()
print 'Preparatory work begins...'
prefix = '../../cascading_generation_model/722911_twolevel_neighbor_cascades/'
suffix = '.detail'
fr = open(prefix+'lambda_Poisson'+suffix, 'r')
lbdlist = fr.readlines()
for i in range(users):
	temp = lbdlist[i].split('\t')
	uid.append(temp[0])
	iddic[temp[0]] = i
	lbd[i] = float(temp[1])
fr.close()

#Get post times
fr = open(prefix+'tweettimes'+suffix, 'r')
post = fr.readlines()
for i in range(len(post)):
	temp = post[i].split('\t')
	if not iddic.has_key(temp[0]):
		iddic[temp[0]] = allusers
		uid.append(temp[0])
		allusers += 1
	posts[iddic[temp[0]]] = int(temp[1])
fr.close()

#Give initial value and construct relation
print 'Construct relation network and give initial value...'

beta = list() #parameter pi (based on edges), row is sender while col is receiver
fr = open(prefix+'relations'+suffix, 'r')
relation = fr.readlines()
n = len(relation)
i = 0
while i < n:
	temp = relation[i].split('\t')
	number = int(temp[1]) + 1
	friend[temp[0]] = list()
	if not iddic.has_key(temp[0]):
			iddic[temp[0]] = allusers
			uid.append(temp[0])
			allusers += 1
	for j in range(i+1, i+number):
		fd = relation[j].split('\t')
		if not iddic.has_key(fd[1]):
			iddic[fd[1]] = allusers
			uid.append(fd[1])
			allusers += 1
		if not edgemap.has_key(iddic[temp[0]]):
			edgemap[iddic[temp[0]]] = {}
		edgemap[iddic[temp[0]]][iddic[fd[1]]] = pos
		pos += 1
		if iddic[temp[0]] >= users or int(fd[2]) == 0:
			beta.append(10 ** -5)
		else:
			beta.append(min(1-10**-5, int(fd[2]) * 1.0 / posts[iddic[temp[0]]]))
		#x.append(1.0)
		friend[temp[0]].append(fd[1])
	i += number
fr.close()
beta = np.array(beta)
#pi = np.arccos(np.sqrt(pi))

#omega = np.arccos(np.sqrt(omega))
#Read personal cascade file
print 'Read behavior log...'
for i in range(users):
	if single and i != filename:
		continue
	fr = open(prefix+'single_user_post/'+str(i)+'_'+uid[i]+suffix, 'r')
	singlefile = fr.readlines()
	SingleObj(singlefile, i)
	fr.close()

gamma = np.zeros(vnum) + 0.3
beta = np.arccos(np.sqrt(beta))
gamma = np.arccos(np.sqrt(gamma))
print 'There are ' + str(vnum) + ' point parameters and ' + str(enum) + ' edge parameters to be learned...'
#Conduct EM algorithm
#QMatrix(q)
for c in clist:
	cascade_author.append(vdic[iddic[author[c]]])
print 'EM algorithm begins...'
#print min(omega)
#print max(omega)
#print pi
cnt = 0
lastObj = np.exp(100)
param = np.append(beta, gamma)
cas_num = len(q)
#lc = np.array(lc)
#q = np.array(q)
#lc = tf.convert_to_tensor(np.array(lc.values()), dtype=tf.float64)
#q = tf.convert_to_tensor(np.array(q), dtype=tf.float64)

temp_rusc = list()
temp_pos = 0
for l in rusc_dic:
	begin_rusc.append(temp_pos)
	temp_pos += len(l)
	end_rusc.append(temp_pos)
	temp_rusc.extend(l)

temp_nrusc = list()
temp_pos = 0
for l in nrusc_dic:
	begin_nrusc.append(temp_pos)
	temp_pos += len(l)
	end_nrusc.append(temp_pos)
	temp_nrusc.extend(l)

#rusc_dic = np.array(rusc_dic.values())
#nrusc_dic = np.array(nrusc_dic.values())
cascade_author = tf.constant(cascade_author, dtype=tf.int32)
rusc = tf.constant(rusc, dtype=tf.float64)
nrusc = tf.constant(nrusc, dtype=tf.float64)
rusc_id = tf.constant(rusc_id, dtype=tf.int32)
nrusc_id = tf.constant(nrusc_id, dtype=tf.int32)
rusc_dic = tf.constant(temp_rusc, dtype=tf.int32)
nrusc_dic = tf.constant(temp_nrusc, dtype=tf.int32)
begin_rusc = tf.constant(begin_rusc, dtype=tf.int32)
begin_nrusc = tf.constant(begin_nrusc, dtype=tf.int32)
end_rusc = tf.constant(end_rusc, dtype=tf.int32)
end_nrusc = tf.constant(end_nrusc, dtype=tf.int32)
#for key in rusc_dic:
#	rusc_dic[key] = tf.constant(rusc_dic[key], dtype=tf.int64)
#	nrusc_dic[key] = tf.constant(nrusc_dic[key], dtype=tf.int64)
print 'Graph construction completed.'
p = tf.Variable(param, name='p')
if alpha > 0:
	alpha = tf.Variable(alpha, dtype=tf.float64)
	optimizer = tf.train.GradientDescentOptimizer(alpha)
else:
	alpha = tf.Variable(alpha, dtype=tf.float64)
	optimizer = tf.train.AdamOptimizer(learning_rate=-alpha)
#optimizer = tf.train.AdamOptimizer(alpha)d
target = ObjF(p)
train = optimizer.minimize(target)
init = tf.global_variables_initializer()
print 'Ready to calculate.'

if single:
	prefix = prefix + 'single_user_parameter/'
	suffix = '_' + str(filename) + suffix

def Output(beta, gamma):
	print 'Output data files...'
	beta = np.cos(beta) * np.cos(beta)
	gamma = np.cos(gamma) * np.cos(gamma)
	fw = open(prefix+'gamma'+suffix, 'w')
	for i in range(vnum):
		fw.write(uid[vlist[i]])
		fw.write('\t')
		fw.write(str(gamma[i]))
		fw.write('\n')
	fw.close()

	fw = open(prefix+'beta'+suffix, 'w')
	for item in edgemap:
		for fd in edgemap[item]:
			if not edgemap[item][fd] in edic:
				continue
			fw.write(uid[item])
			fw.write('\t')
			fw.write(uid[fd])
			fw.write('\t')
			fw.write(str(beta[edic[edgemap[item][fd]]]))
			fw.write('\n')
	fw.close()

with tf.Session() as session:
	session.run(init)
	#qf = EStep(omega, pi, x, theta1, theta2, theta3, theta4)
	#total = begin_rusc.get_shape()[0]
	#same = 0
	#for i in range(total):
	#	if session.run(begin_rusc[i]) == session.run(end_rusc[i]):
	#		same += 1
	#print same
	obj = session.run(target)
	print 'Initial value: ' + str(obj)
	while cnt < 100:
	#param = Joint(omega, pi, x, theta1, theta2, theta3, theta4)
	#start = datetime.datetime.now()
	#obj = ObjF(param)
	#end = datetime.datetime.now()
	#print (end - start).seconds
		#out_qf = session.run(qf)
		#print 'EStep ' + str(cnt+1) + ' finished...'
		for step in range(iters):
			session.run(train)
			newp = session.run(p)
			obj = session.run(target)
		#print 'MStep ' + str(cnt+1) + ' finished...'
		print 'Objective function value: ' + str(obj)
		if str(obj) == 'nan':
			break
		#print str(it) + ' ' + str(noreply)
		#print omega[:10]
		if abs(lastObj) - obj < epsilon:
			if abs(lastObj) - obj > 0:
				beta = newp[:enum]
				gamma = newp[enum:]
			break
		beta = newp[:enum]
		gamma = newp[enum:]
		#Output(np.cos(omega) * np.cos(omega), np.cos(pi) * np.cos(pi), x)
		Output(beta, gamma)
		lastObj = obj	
		cnt += 1
		print 'Iteration ' + str(cnt) + ' finished...'
#omega = np.cos(omega) * np.cos(omega)
#pi = np.cos(pi) * np.cos(pi)

#Output parameters
Output(beta, gamma)

endtime = datetime.datetime.now()
print 'Time consumed: ' + str(endtime - starttime) + ' (' + str(alpha) + ')'
