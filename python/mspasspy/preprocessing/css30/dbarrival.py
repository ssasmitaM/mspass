#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct 24 06:31:28 2020

@author: Gary Pavlis, Dept. of Earth and Atmos Sci, Indiana University
"""
from mspasspy.ccore.utility import (MsPASSError,
                            ErrorSeverity)
import pandas as pd
from obspy import UTCDateTime
def load_css30_arrivals(db,filename,attribute_names=['evid',
                'source_lat',
                'source_lon',
                'source_depth',
                'source_time',
                'mb',
                'ms',
                'sta',
                'phase',
                'iphase',
                'delta',
                'seaz',
                'esaz',
                'residual',
                'time',
                'deltim']):
    """
    Loads an ascii table of arrival time data extracted from an 
    antelope (css3.0) database.   The default format of the table 
    is that produced by a shell script linked to this function that
    has the (current) name of dbexport_to_mongodb.csh (that name is
    likely to change before a release).  The names are locked to 
    css3.0 attribute names that form the argument list to a 
    program called dbselect.   Users of other database can easily 
    simulate this in sql by listing the same attributes in the same 
    order.  The names used here are translations of concept to mspass.
    Note not all of these attributes would always be required and 
    alternative implementation may want to change that list - hence 
    attribute_name is a defaulted parameter.
    
    :param db: is a MongoDB database handle.  It can be as basic as 
      the return of client('dbname') but it can also be an instance 
      of the mspass Database class.  There is no default
    :param filename:  is the string defining a file containing the expected
      text file with columns in the order defined by attribute_names.
    :param attribute_names:  is the list of MongoDB attribute keys to assign 
      to each column of data.   
     
    :return:  MongoDB InsertManyResult object.  This can be used, for 
      example, to get the number of rows inserted in arrival from 
      len(r.insertedIds) where r is the symbol given the return.
    """
    # I can find no documentation saying anything about what exceptions 
    # this function will throw.  For now assume it will be run interactively 
    # and errors will be handled by user when the error is automatically 
    # printed by the interpreter. 

    #
    # panda reader used is for clean white space delimited text.  That works 
    # for these attributes ONLY because all never nave spaces.  Note this
    # reader would be dangerous if using an attribute like a comment attribute
    # that has spaces in the string associated with it's value.  It is always 
    # safe here because sta,phase, and iphase never have spaces
    df=pd.read_table(filename,delim_whitespace=True,header=None,
                     names=attribute_names)
    df.reset_index(inplace=True)
    data_dict=df.to_dict("records")
    col=db.arrival
    ret=col.insert_many(data_dict)
    # ret is an special object returned by mongodb - basically a list of 
    # object ids.  We return it for convenience
    return ret
def load_css30_sources(db,srcdict,collection='source',
                       attribute_names=['evid',
                                        'latitude',
                                        'longitude',
                                        'depth',
                                        'time']):
    """
    Companion to extract_unique_css30_sources to load output of that 
    function into a MongoDB database.   The algorithm is cautious and 
    first scans the existing source collection for any matching evids.  
    If it finds any it prints them and does nothing but issue an error
    message. That was done because this function is only expected to be
    done interactively for preprocessing.  
    
    :param db:  MongoDB database handle
    :param srcdict:  dict output of extract_unique_css30_sources
    :param collection:  optional alternative collection to save (default 
    is source)
    :param attribute_names: list of keys to copy from srcdict to database.  
      Note currently no aliases are allowed and we don't test that these
      are found.  We assume the list is consistent with what is 
      posted by extract_unique_css30_events
    """
    dbh=db[collection]
    # first scan for matches in any of the evids
    need_to_fix=dict()
    for evid in srcdict:
        query={'evid' : evid}
        n=dbh.count_documents(query)
        if n>0:
            rec=dbh.find_one(query)
            need_to_fix[evid]=rec
    if(len(need_to_fix)>0):
        print('The following records in collection ',collection,' have matching data for one or more evids')
        print('You must fix the mismatch problem before you can load these data')
        for k in need_to_fix:
            print(k,need_to_fix[k])
        return None
    # could have an else here but control comes here unless the we hit 
    # the retun condition above
    count=0
    for evid in srcdict:
        rec=srcdict[evid]
        srcoid=dbh.insert_one(rec).inserted_id
        #get object id from retval and update this record to set source_id to 
        # the object_id of this record
        dbh.update_one(
                {'_id' : srcoid},
                { '$set' : {'source_id' : str(srcoid)}})
        count += 1
    return count
def set_source_id_from_evid(db,collection='arrival'):
    dbarr=db[collection]
    dbsrc=db['source']
    alldocs=dbarr.find({})
    number_arrivals=0
    number_set=0
    evid_set=dict()
    not_set=dict()
    for doc in alldocs:
        if 'evid' in doc:
            evid=doc['evid']
            query={'evid' : evid}
            n=dbsrc.count_documents(query)
            if n==0:
                if evid in not_set:
                    nset=not_set[evid]
                    nset+=1
                    not_set[evid]=nset
                else:
                    not_set[evid]=1
            else:
                srcrec=dbsrc.find_one(query)
                source_id=srcrec['source_id']
                arroid=doc['_id']
                dbarr.update_one(
                        {'_id' : arroid},
                        {'$set' : {'source_id' : source_id}}
                )
                number_set += 1
                if evid in evid_set:
                    nset=evid_set[evid]
                    nset+=1
                    evid_set[evid]=nset
                else:
                    evid_set[evid]=1
        number_arrivals += 1
    return [number_arrivals,number_set,evid_set,not_set]
def extract_unique_css30_sources(filename,attribute_names=['evid',
                'source_lat',
                'source_lon',
                'source_depth',
                'source_time',
                'mb',
                'ms',
                'sta',
                'phase',
                'iphase',
                'delta',
                'seaz',
                'esaz',
                'residual',
                'time',
                'deltim']):
    """
    Utility function to scan the same table used by load_css30_arrivals to 
    create a dict of unique sources keyed by the parent css30 database 
    key evid.   This will only work if evid is set correctly for 
    each row in the input table.  The algorithm used is a bit ugly 
    and exploits the unique key insertion of a python dict container 
    that also behaves like a C++ std::map container.   That is, if new 
    data is inserted with a matching key to something already in the container
    the new data silently replaces the old data.   This is a clean way to 
    create a unique set of data keyed by evid, BUT as noted it will create
    extraneous results if evid value are not consistent with the arrivals 
    (That shouldn't happen if the parent css3.0 database was properly formed).
    
    :param filename: text file to scan created form datascope shell command ending 
      with dbselect to produce attributes in the order listedfor attribute_names
      (the default anyway)
    :param attribute_name: is a list of keys to assign to each column of 
      data in the input file. Default is for output of a particular shell 
      script ending a unix chain with dbselect with attributes in the order
      listed.   If the dbselect line changes this attribute will need to be
      changed too.
    :return:  dict keyed by evid of source coordinate data.
    """
    df=pd.read_table(filename,delim_whitespace=True,header=None,
                     names=attribute_names)
    df.reset_index(inplace=True)
    recs=df.to_dict("records")
    sources=dict()
    for d in recs:
        evid=d['evid']
        lat=d['source_lat']
        lon=d['source_lon']
        depth=d['source_depth']
        time=d['source_time']
        #this depends upon container replacing content when keys match 
        # inefficient but should work
        sources[evid]={'evid' : evid,
               'latitude' : lat, 
               'longitude': lon,
               'depth' : depth,
               'time' : time}
    return sources
def parse_snetsta(fname,verbose=False):
    """
    Parses the raw text file in an antelope db.snetsta file.  It returns a dict with their sta attribute
    as the key (their sta is not necessarily the seed sta).  Each entry points to a dict with keys net and fsta.  
    We use fsta as that is the field BRTT defines for the seed sta field in snetsta.   
    
    :param fname: is the snetsta file to be parsed.
    :param verbose: if True the function will print all stations for which fsta does not match sta
    """
    with open(fname,'r') as fp:
        staindex={}
        for lines in fp.readlines():
            x=lines.split()  # depend that default is whitespace
            net=x[0]
            fsta=x[1]
            sta=x[2]
            staindex[sta]={"fsta":fsta,"net":net}
            if verbose and fsta!=sta:
                print('Warning:  station in net=',net,' uses altered sta code=',sta,' for sta=',fsta)
        return staindex
def make_css30_composite_sta(sta,net):
    """
    Small helper for below but of potential general use.  Creates a 
    composite station code using antelope rules for mixing sta and net 
    passed as args.  Returns the composite name. (eg. AAK_II or XYZTXX)
    """
    n=len(sta)
    if n<=3:
        s=sta+'_'+net
    else:
        # Note sta can sometimes be more than 4 characters and the 
        # result of this would make an invalid station code for datascope.
        # Since we only preserve this as a separate attribute it it is 
        # better to preserve the pieces this way until proven otherwise.
        s=sta+net
    return s
def set_netcode_snetsta(db,staindex,collection='arrival'):
    """
    Takes the dict staindex that defines how snetsta defines seed codes for 
    antelope tables and updates a specified collection to add net code and, 
    when necessary, repair station name used by antelope to deal with 
    multiple sites have the same station code (sta) but different network 
    codes.  
    
    Antelope uses the css3.0 schema which was invented before anyone conceived 
    the need for handling the quantity of data seen today assembled from 
    multiple sources.  As a result the schema has a fundamental flaw 
    wherein a channel is defined in css3.0 by two codes we refer to in 
    mspass as "sta" and "chan" (these happen to be the same as those used by 
    antelope).   When the SEED standard was defined the committee drafting the
    standard had the wisdom to realize sta and chan were not sufficient to 
    describe data assembled from multiple sources when station codes were 
    chosen independently by network operators.  Hence, they adopted the idea of
    adding a network (net) and location (loc) code to tag all data.   Hence 
    all seed and miniseed (seed contains metadata as well as data.  A subset 
    of seed called miniseed is the norm today which has only data bunched in 
    packets with each packet keyed by net:sta:loc:chan:startime:endtime).  
    
    All that background is included for users to understand the background to 
    this function.  BRTT, the developers of Antelope, recognized the limitations
    of css3.0 early on but realized the depth of the problem long after their 
    code base was deeply locked into css3.0.  Rather than fix the problem 
    right they chose to use a kludge solution that has created a weakness in 
    antelope ever since.  To handle duplicate stations they created a composite
    net:sta key with names like AAK_II and composite channel names (for loc 
    codes) like BHZ_00.   Things might have been better had they made all 
    sta keys this composite, but because users are locked into sta codes 
    for a variety of reason they elected to retain sta and use the composite 
    ONLY IF a duplicate sta was present.   That method works fine for 
    largely static data in fixed network operations (their primary 
    customers) but is a huge mess for research data sets bringing in data 
    from multiple sources.  Hence, for mspass we need to get rid of anything 
    remotely linked to snetsta and schanloc as cleanly as possible.  This 
    function is aimed at fixing snetsta problems.
    
    The function works off an index passed as staindex created by a 
    companions function called "parse_snetsta".   This function scans 
    the collection it is pointed at (default is arrival, but any collection 
    containing "sta" as an attribute can be handled) and looks for matching
    entries for the "fsta" field in snetsta.  When it finds a match it
    adds the net code it finds in the index, corrects the sta code 
    (expanded in a moment), and sets a new attribute "css30_sta".   
    The function handles composite names defined for sta by a simple algorithm 
    that duplicates the way antelope handles duplicate station codes.  
    If the station code is 3 characters or less the name is created in the 
    form sta_net (e.g. sta='AAK' and net='II' will yield AAK_II).  If 
    the sta code is 4 characters long the css30_sta is of the simple 
    concatenation ofthe two strings (e.g. sta='HELL' and net='XX' yields
    'HELLXX').   If the code found is longer than 4 characters it is
    assumed to be already a composite created with the same rules.  In that 
    case the name is split to pieces and compared to the index fsta and net
    values.  If they match the composite is used unaltered for the css30_sta name and 
    the fsta and net values are added as sta and net in the update of the 
    document to which they are linked.
    
    The function also tests documents it processes for an existing net code.
    If it finds one it tests for the existence of css30_sta.   If that 
    attribute is already defined it skips updating that document.  If css30_sta
    is not defined it is the only field updated. This was done as a way to 
    use a scan of the site collection as an alternative to setting net and 
    then using this to set css30_sta as an alias for sta for some operations.
    
    :param db: is a mongodb database handle.  It can either be the plain result 
      of a client('dbname') definition or a mspass.Database class instance.
    :param staindex:  is a dict returned by parse_snetsta.  The key of this index is a sta name it function
      expects to find in an arrivals document.  the dict value is a dict with two keys: fsta and net.  
      net is the seed network code and fsta is the expected seed station code.  Updates replace the sta
      field in arrivals with the fsta values and put the original sta value in arrival_sta.
    :param collection:  MongoDB collection to scan to apply snetsta correction.  
      (default is arrival)

    :return:  tuple with these contentss:
        0 - number of documents scanned
        1 - number update
        2 - set of stations names with no match in the snetsta index.
          (these will often need additonal attention through another
          mechanism)
    :rtype:  tuple
    """
    col=db[collection]
    print(col.count_documents({}))
    updaterec={}
    nprocessed=0
    nset=0
    sta_not_found=set()
    # not quite sure how mongo handles this with a large collection.  We may need to define
    # chunks to be processed.
    dbcursor=col.find({})
    for doc in dbcursor:
        doc_needs_update=True
        nprocessed += 1
        id=doc['_id']
        dbsta=doc['sta']
        if dbsta in staindex:
            updaterec.clear()
            xref=staindex[dbsta]
            net=xref['net']
            sta=xref['fsta']
            if 'net' in doc:
                if 'css30_sta' in doc:
                    # We use this case to detect previously processed data
                    # so we simply skip them
                    doc_needs_update=False
                else:
                    # Assume if we land here something else set net and 
                    # we just need to set css30_sta
                    sta=doc['sta']
                    net=doc['net']
                    css30sta=make_css30_composite_sta(sta,net)
                    updaterec['css30_sta']=css30sta
                    doc_needs_update=True
            else:
                if(len(dbsta)<=3):
                    updaterec['css30_sta']=dbsta+"_"+net
                elif(len(dbsta)==4):
                    updaterec['css30_sta']=dbsta+net
                else:
                    # We use this name directly in this case.   We don't 
                    # force the antelope method to allow flexibility
                    # it is possible a user creates an snetsta entry by hand
                    # and this will handle that correctly.
                    updaterec['css30_sta']=dbsta 
                updaterec['net']=net
                updaterec['sta']=sta
                doc_needs_update=True 
        else:
            sta_not_found.add(dbsta)
            doc_needs_update=False  # do not do this here as we have nothing to change
        if doc_needs_update:
            # for testing just print these
            #print(updaterec)
            col.update_one(
                    {'_id' : id},
                    { '$set' : updaterec}
                )
            nset += 1
    return tuple([nprocessed,nset,sta_not_found])
def set_netcode_from_site(db,collection='arrival',time_key=None,stations_to_ignore=None):
    """
    This function scans a MongoDB collection that is assumed to contain 
    a "sta" for station code to be cross referenced with metadata stored in
    the site collection.   (The default collection is arrival, but this could
    be used for any table for which sta needs to be regularized to a seed 
    net:sta pair.)  The entire objective of the function is to add missing 
    seed net codes.   The algorithm used here is the most basic possible and 
    looks only for a match of sta and and option time matched with 
    a site's operation interval defined by a starttime to endtime time interval.
    I returns two lists of problem children that have to be handled 
    separately:  (1) a set container of station names that have no matching 
    value in the current site collection, and (2) a set container with 
    a tuple of [net, sta, startime, endtime] values of net:sta combinations 
    that are ambiguous.  They are defined as ambiguous if a common sta 
    code appears in two or more networks.   Both cases need to be handled 
    by subsequent processing. The first, requires scrounging for the 
    station metadata.  A good foundation for that is obspy's get_stations 
    function.  The ambiguous station code problem requires rules and special 
    handling.   That will be deal with in tools planned for the near future
    but which do not exist at the time this function was finalized.  
    The key idea in both cases is to use the output of this function to 
    guide additional processing with two different workflows aimed at 
    building a clean database to initiate processing. 

    :param db: is a MongoDB database handle.  It can be as basic as 
      the return of client('dbname') but it can also be an instance 
      of the mspass Database class.  There is no default.
    :param collection:  MongoDB collection to be updated.  Processing 
      keys on the data with key="sta" and (optional) value of time_key arg.
      (Default is arrival)
    :param time_key: is a document key in collection containing a time 
      used to match any site's operational starttime to endtime time window.
      Default is None which turns off that selection.  Ambiguous keys may 
      be reduce in large datasets by using a time key.  
    :param stations_to_ignore: is expected to be a set container listing 
      any station codes to be ignored in processing.   This can be used to 
      reduce processing overhead or handle sites where net is null and 
      not needed at all.   Default is None which turns this option off. 
    :return:  Summary of results in the form of a 4 element tuple.  
    :rtype:  tuple with the following contents:
        0 - number of documents processed
        1 - number of documents updated in this run
        2 - set container of tuples with content (net,sta,starttime,endtime) 
            of all documents matching the reference sta code but having 
            different net codes or time spans.   These data are stored in a 
            set container to easily sort out the unique combinations.   
        3 - set container of station codes that found in collection that 
            had no matching entry in the site collection.
    """

    dbh=db[collection]
    dbsite=db['site']
    ambiguous_sta=set()
    not_found_set=set()
    # This is kind of an ugly way to handle null ignore list but is functional
    if stations_to_ignore == None:
        stations_to_ignore=set()
    query={}
    updaterec={}
    nprocessed=0
    nupdates=0
    dbcursor=dbh.find({})
    for doc in dbcursor:
        nprocessed += 1
        id=doc['_id']
        if not ('sta' in doc):
            print('set_netcode_from_site (WARNING):  document with id=',id,
                  ' has no sta attribute -skipped')
            continue
        sta=doc['sta']
        if sta in stations_to_ignore:
            continue
        if 'net' in doc:
            # silently skip records for which net is already defined for efficiency
            continue
        query.clear()
        query['sta']={ '$eq' : sta }
        if time_key != None:
            if time_key in doc:
                time=doc[time_key]
            # site has starttime and endtime defined so no need to test for
            # their presence.  
                query['starttime']={"$lt" : time}
                query['endtime']={"$gt" : time}
            else:
                # for now just log this as an error
                print("Time key=",time_key," not found in document for sta=",sta)
        found=dbsite.find(query)
        nfound=found.count()
        if nfound == 1:
            x=found.next()
            updaterec.clear()
            net=x['net']
            updaterec['net']=net
            dbh.update_one(
                    {'_id' : id},
                    { '$set' : updaterec}
                )
            nupdates += 1
        elif nfound > 1 :
            # this dependence on set uniqueness approach may be 
            # a bit inefficient for large collections.  Perhaps should
            # test before add 
            for x in found:
                net=x['net']
                st=x['starttime']
                et=x['endtime']
                val=tuple([net,sta,st,et])
                ambiguous_sta.add(val)
        else:
            not_found_set.add(sta)
    return [nprocessed,nupdates,ambiguous_sta,not_found_set]
def set_netcode_time_interval(db,sta=None,net=None,collection='arrival',
                    starttime=None,endtime=None,time_filter_key='time'):
    """
    Forces setting net code for data with a given station code within a 
    specified time interval.  
    
    Arrivals measured with Antelope using Datascope to manage the catalog
    data has a disconnect with seed's required net:sta to specify a unique 
    seismic observatory (what we call site). The css3.0 schema does not 
    include the net attribute.  This collides with modern stationxml 
    files used to deliver instrument metadata because they are always 
    indexed by net:sta.   This function is one a collection of functions 
    to set the net field in a collection (normally arrival but could 
    be other collections with ambiguous sta keys).  This particular function
    is intended as a last resort to more or less force setting net to a
    single value for all documents matching the sta key.   There is an 
    optional time range that can be used to fix ambiguous entries like 
    some TA stations that were adopted and nothing changed but the net 
    code on a particular day.   
    
    :param db:   Database handle (can be a raw top level MongoDB database pointer 
      or a mspass Database class
    :param sta: station name to use as key to set net
    :param net: net code to which all data matching sta will be set 
      (a warning is issued if this field in the retrieved docs is already set)
    :param collection:  MongoDB collection to be updated (default is arrival)
    :param starttime:  starting time period of (optional) time filter.   
      (default turns this off) Must be UTCDateTime
    :param endtime:  end of time period for (optional) time selection.
      (default is off) Note a MsPASSError will be thrown if endtime is not 
      defined by starttime is or vice versa.  Must be a UTCDateTime object
    :return: number of documents updated.
    """
        
    basemessage='set_netcode_time_interval:  '
    if(sta==None or net==None):
        print(basemessage + 'you must specify sta and net as required parameters')
    dbarr=db[collection]
    query={'sta' : sta}
    if starttime==None or endtime==None:
        if starttime != None:
            raise MsPASSError(basemessage+"usage error - starttime defined but endtime was left null")
        elif endtime!=None:
            raise MsPASSError(basemessage+"usage error - endtime defined but starttime was left null")
    else:
        if not isinstance(starttime,UTCDateTime):
            raise MsPASSError(basemessage+'usage error - starttime must be specified as an obspy UTCDateTime object')
        if not isinstance(endtime,UTCDateTime):
            raise MsPASSError(basemessage+'usage error - endtime must be specified as an obspy UTCDateTime object')
        tse=starttime.timestamp
        tee=endtime.timestamp
        query[time_filter_key]={"$gte" : tse,"$lte" : tee}
    n=dbarr.count_documents(query)
    if n==0:
        print(basemessage+'the following query returned no documents in collection'+collection)
        print(query)
    else:
        count=0
        curs=dbarr.find(query)
        for doc in curs:
            if 'net' in doc:
                print(basemessage+'WARNING found document with net code set to ',doc['net'])
                # this check is required for robustness when time filter is off
                if time_filter_key in doc:
                    print('Problem document time=',UTCDateTime(doc[time_filter_key]))
                print('Setting net in this document to requested net code=',net)
            oid=doc['_id']
            updaterec={'net':net}
            dbarr.update_one(
                    {'_id' : oid},
                    {'$set' : updaterec}
            
            )
            count+=1
    return count
def find_null_net_stations(db,collection="arrival"):
    """
    Return a set container of sta fields for documents with a null net 
    code (key=net).  Scans collection defined by collection argument.
    """
    dbcol=db[collection]
    net_not_defined=set()
    curs=dbcol.find()
    for doc in curs:
        if not 'net' in doc:
            sta=doc['sta']
            net_not_defined.add(sta)
    return net_not_defined
def find_duplicate_sta(db,collection='site'):
    """
    Scans collection requested (site is default be can be run on channel)
    for combinations of net:sta where the sta is not unique.   This can 
    cause problem in associating data from css3.0 databases that do not 
    have a net code for station names.   Returns a dict with sta names 
    as key and a set container with net codes associated with that sta.  
    The algorithm used here is a large memory algorithm but considered
    acceptable since the total number of instruments in a data set is 
    not currently expected to be a limiting factor. If the collection 
    were huge it would be better to use a well crafted incantation to 
    mongodb.  
    
    
    :param db: mspass Database handle or just a plain MongoDB database 
      handle.  (mspass Database is a child of MongoDBs top level database 
      handle)  
    :param collection:  string defining the collection name to scan 
      (default is site)
    :return: dict of stations with nonunique sta codes as the key.  The 
      value returned in each field is a set container with net codes that use that 
      sta code.
    """
    dbcol=db[collection]
    allsta={}
    curs=dbcol.find()   # we do a brute force scan through the collection
    for rec in curs:
        if "net" in rec:
            net=rec["net"]
            sta=rec["sta"]
            if sta in allsta:
                val=allsta[sta]
                # note this works only because the set container behaves 
                # like std::set and adds of duplicates do nothing
                val.add(net)
                allsta[sta]=val
            else:
                stmp=set()
                stmp.add(net)
                allsta[sta]=stmp
        else:
            sta=rec["sta"]
            print("find_duplicate_sta (WARNING):  ",collection,
                  " collection has an undefined net code for station",
                  sta)
            print("This is the full document from this collection")
            print(rec)
    # Now we have allsta with all unique station names.  We just look 
    # for ones where the size of the set is not 1
    trouble_sta={}
    for x in allsta:
        s=allsta[x]
        if len(s)>1:
            trouble_sta[x]=s
    return trouble_sta
def check_for_ambiguous_sta(db,stalist,
                            collection='arrival',
                            verbose=False,
                            verbose_attributes=None):
    """
    Scans db.collection for any station in the list of station codes 
    defined by the list container stalist.  By default it reports only 
    the count of the number of hits for each sta.   If verbose is set it
    prints a summary of every record it finds - warning this can get huge
    so always run verbose=false first to find the scope of the problem.
    
    :param db:  Mongodb database pointer - can also be a mspass Database class
      object.
    :param stalist:  required list of station names to be checked
    :param verbose: turn on verbose mode (see overview paragraph)
    :param verbose_attributes:  list container of database attributes to 
      be printed in verbose mode.  Note is default is None and the 
      function will exit immediately with an error message if verbose is 
      enable and this list is not defined.   The current version blindly 
      assumes every document found will contain these attributes.   It will 
      abort if an attribute is not defined.  
    """
    if(verbose and (verbose_attributes==None)):
        print('check_for_ambiguous_sta:  usage error')
        print('if verbose mode is turned on you need to supply python list of db attributes to print')
        return None
    if verbose:
        to_print=[]
        for key in verbose_attributes:
            to_print.append(key)
        print(to_print)
    else:
        print('station count')
    dbhandle=db[collection]
    need_checking=[]
    for sta in stalist:
        query={ "sta" : sta }
        nsta=dbhandle.count_documents(query)
        if(verbose and nsta>0):
            curs=dbhandle.find(query)
            for rec in curs:
                to_print=[]
                for key in verbose_attributes:
                    to_print.append(rec[key])
                print(to_print)
        else:
            print(sta,nsta)
            if(nsta>0):
                need_checking.append(tuple([sta,nsta]))
    return need_checking
        