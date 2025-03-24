import B64
import DQXDbTools


#Find hits for gene patterns (or similar searches)
def response(returndata):
    databaseName=None
    if 'database' in returndata:
        databaseName = returndata['database']
    db = DQXDbTools.OpenDatabase(DQXDbTools.ParseCredentialInfo(returndata), databaseName)
    cur = db.cursor()
    mypattern=DQXDbTools.ToSafeIdentifier(returndata['pattern'])

    names=[]
    chroms=[]
    starts=[]
    ends=[]
    ids=[]
    descrs=[]

    #Detect to see if the pattern is actually a chromosome position
    if (":" in mypattern) and (len(mypattern)>4) and (mypattern[0:3]=="chr"):
        chromostr,posstr=mypattern.split(':')
        if len(chromostr)>0:
            pos=int(posstr)
            names.append(mypattern)
            chroms.append(chromostr)
            starts.append(pos)
            ends.append(pos)

    else:

        maxcount=6#the maximum number of hits we are going to report
        if 'count' in returndata:
            maxcount=int(returndata['count'])
        reportAll=False
        if 'reportall' in returndata:
            reportAll=True
        foundmap={}

        #Note: we do this 2 times, first with pattern in start position, and second with pattern in any position if the first did not fill up the max match count
        for trynr in range(0,2):
            patternstr="{0}%".format(mypattern)
            if trynr==1:
                patternstr="%{0}%".format(mypattern)
            statement='SELECT fname, chromid, fstart, fstop,fid,fnames,descr FROM {tablename} WHERE ((ftype="gene") or (ftype="pseudogene")) and ((fname LIKE "{pattern}") or (fnames LIKE "{pattern}") or (descr LIKE "{pattern}") or (fid="{mypattern}") or (fid LIKE "{pattern}")) LIMIT {maxcount}'.format(
                tablename=DQXDbTools.ToSafeIdentifier(returndata['table']),
                pattern=patternstr,
                mypattern=mypattern,
                maxcount=maxcount
            )
            cur.execute(statement)
            for row in cur.fetchall() :
                if len(names)<maxcount:
                    chromnrstr=row[1]
                    name=row[0]
                    ident=name
                    if reportAll:
                        ident+='_'+chromnrstr+' '+str(row[3])+' '+str(row[4])
                    if ident not in foundmap:
                        names.append(name)
                        chroms.append(chromnrstr)
                        starts.append(row[2])
                        ends.append(row[3])
                        ids.append(row[4])
                        descrs.append(str(row[0])+';'+str(row[5])+';'+str(row[6]))
                        foundmap[ident]=1
            if len(names)>=maxcount:
                trynr=99

        if (len(names)==0) and ('alttablename' in returndata):
            statement='SELECT {idfield}, {chromnrfield}, {posfield} FROM {tablename} WHERE ({idfield} LIKE "{pattern}%") LIMIT {maxcount}'.format(
                tablename=DQXDbTools.ToSafeIdentifier(returndata['alttablename']),
                idfield=DQXDbTools.ToSafeIdentifier(returndata['altidfield']),
                chromnrfield=DQXDbTools.ToSafeIdentifier(returndata['altchromnrfield']),
                posfield=DQXDbTools.ToSafeIdentifier(returndata['altposfield']),
                pattern=mypattern,
                maxcount=maxcount
            )
            cur.execute(statement)
            for row in cur.fetchall() :
                if (len(names)<maxcount):
                    chromnrstr=row[1]
                    names.append(row[0])
                    chroms.append(returndata['altpositionchromprefix']+str(chromnrstr))
                    pos=row[2]
                    starts.append(pos)
                    ends.append(pos)
                    descrs.append('')

    valcoder=B64.ValueListCoder()
    returndata['Hits']=valcoder.EncodeStrings(names)
    returndata['Chroms']=valcoder.EncodeStrings(chroms)
    returndata['Starts']=valcoder.EncodeIntegers(starts)
    returndata['Ends']=valcoder.EncodeIntegers(ends)
    returndata['IDs']=valcoder.EncodeStrings(ids)
    returndata['Descrs']=valcoder.EncodeStrings(descrs)

    #TODO: pass 'hasmore' flag if list is limited, and make client interpret this

    return returndata
