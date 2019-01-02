from fitparse import FitFile
from fitparse.utils import fit_from_datetime, fit_to_datetime

from fitparse.encoder import FitFileEncoder, DataMessageCreator
from fitparse.profile import FIELD_TYPES

import sys, getopt
import math


def smoothfitfile( inputfitfile, outputfitfile, smooth_width):
    "This removes noise from gps coordinates"

    f = open(outputfitfile,'wb')
    fitfile = FitFile(inputfitfile)
    print("input fit file: %s" % (inputfitfile, ))

    # Get all messages
    messages = list(fitfile.get_messages(name=None, with_definitions=True))
    print("original file: \"%s\" ; contains %d messages" % (inputfitfile, len(messages), ))
    print("smoothed file: \"%s\"" % (outputfitfile.name, ))

    class positionmessage(object):
        def __init__(self, ts, lat, lon):
            self.ts = ts
            self.lat = lat
            self.lon = lon
            self.smooth_lat = lat
            self.smooth_lon = lon
            self.dist = 0
            self.cumul = 0
            self.speed = 0

    altitude = None
    positionmessages = []

    ############################################################
    # first we create a table containing all position messages
    ############################################################
    for message in messages:

        # Go through all the data entries in this record
        if message.name=='record' and message.type == 'data':
            ts = None
            lat_sc = None
            lon_sc = None
            hr = None
            alt = None
            dist = 0

            # Go through all the data entries in this record
            for message_data in message:
                if (message_data.name=='position_lat') and (message_data.value is not None):
                    lat_sc = message_data.value
                if (message_data.name=='position_long') and (message_data.value is not None):
                    lon_sc = message_data.value
                if message_data.name=='timestamp':
                    ts = message_data.value
                if (message_data.name=='altitude') and (altitude is None):
                    altitude = message_data.value

            if (lat_sc is not None) and (lon_sc is not None) and (ts is not None):
                positionmessages.append(positionmessage(ts, lat_sc, lon_sc))

    print("Nb valid position messages: %d" % (len(positionmessages)))

    ############################################################
    # moving average
    ############################################################
    # TODO : add ts data to add weight to close data
    
    for i, message in enumerate(positionmessages):
        t = 0
        s_lat = 0
        s_lon = 0
        for j in range( max(1, i-smooth_width), i):
            s_lat += positionmessages[j].lat
            s_lon += positionmessages[j].lon
            t += 1
        for j in range( i, min(i+smooth_width, len(positionmessages))):
            s_lat += positionmessages[j].lat
            s_lon += positionmessages[j].lon
            t += 1
        # note: message i is added twice

        positionmessages[i].smooth_lat = s_lat / t
        positionmessages[i].smooth_lon = s_lon / t
        #print("%d, %d, %f" % (i, t, positionmessages[i].smooth_lat, ))

    #then estimate speed and distance
    prev_lat = None
    prev_lon = None
    prev_ts = None
    lat = None
    lon = None
    ts = None
    cumul = 0
    dist = 0
    speed = 0
    for message in positionmessages:
        lat = message.smooth_lat
        lon = message.smooth_lat
        ts = message.ts
        if prev_lat is not None:
            message.dist = dist_sc(lat, lon, prev_lat, prev_lon)
            cumul += message.dist
            message.cumul += cumul
            message.speed = message.dist / (ts - prev_ts).total_seconds() #m/s ??

        prev_lat = lat
        prev_lon = lon
        prev_ts = ts


    #then replace data in original messages
    sm_lat = None
    sm_lon = None
    sm_cumul = 0
    sm_dist = 0
    sm_speed = 0
    prev_lap_cumul = prev_sess_cumul = 0
    prev_lap_ts = prev_sess_ts = positionmessages[0].ts
    lap_start_lat = sess_start_lat = positionmessages[0].smooth_lat
    lap_start_lon = sess_start_lon = positionmessages[0].smooth_lon
    lap_max_speed = sess_max_speed = 0

    for message in messages:
        if message.name=='record' and message.type == 'data':
            ts = None
            raw_lat = None
            raw_lon = None
            for message_data in message:
                 if message_data.name=='timestamp':
                     ts = message_data.value
                 if message_data.name=='position_lat':
                     raw_lat = message_data.value
                 if message_data.name=='position_long':
                     raw_lon = message_data.value

            smooth_one = [m for m in positionmessages if m.ts==ts]

            if len(smooth_one)==1:
                sm_lat = smooth_one[0].smooth_lat
                sm_lon = smooth_one[0].smooth_lon
                sm_cumul = smooth_one[0].cumul
                sm_dist = smooth_one[0].dist
                sm_speed = smooth_one[0].speed
            else:
                sm_lat = None
                sm_lon = None

            if sm_speed > lap_max_speed:
                lap_max_speed = sm_speed
            if sm_speed > sess_max_speed:
                sess_max_speed = sm_speed

            for message_data in message:
                 if message_data.name=='position_lat':
                     message_data.value = sm_lat
                 if message_data.name=='position_long':
                     message_data.value = sm_lon
                 if message_data.name=='altitude':
                     message_data.value = altitude
                 if message_data.name=='enhanced_altitude':
                     message_data.value = altitude
                 if message_data.name=='distance':
                     message_data.value = sm_cumul
                 if message_data.name=='speed':
                     message_data.value = sm_speed
                 if message_data.name=='enhanced_speed':
                     message_data.value = sm_speed

        if message.name=='lap' and message.type == 'data':
            
            for message_data in message:
                 if message_data.name=='avg_speed':
                     message_data.value = (sm_cumul - prev_lap_cumul) / (ts - prev_lap_ts).total_seconds()
                 if message_data.name=='end_position_lat':
                     message_data.value = sm_lat
                 if message_data.name=='end_position_long':
                     message_data.value = sm_lon
                 if message_data.name=='start_position_lat':
                     message_data.value = lap_start_lat
                 if message_data.name=='start_position_long':
                     message_data.value = lap_start_lon
                 if message_data.name=='enhanced_avg_speed':
                     message_data.value = (sm_cumul - prev_lap_cumul) / (ts - prev_lap_ts)  .total_seconds()                   
                 if message_data.name=='enhanced_max_speed':
                     message_data.value = lap_max_speed
                 if message_data.name=='max_speed':
                     message_data.value = lap_max_speed
                 if message_data.name=='total_ascent':
                     message_data.value = 0
                 if message_data.name=='total_descent':
                     message_data.value = 0
                 if message_data.name=='total_distance':
                     message_data.value = (sm_cumul - prev_lap_cumul)
                 # TODO : bounding box not considered (fields 27 to 32...)

            prev_lap_cumul = sm_cumul
            prev_lap_ts = ts
            lap_max_speed = 0
            lap_start_lat = sm_lat
            lap_start_lon = sm_lon

        if message.name=='session' and message.type == 'data':
            
            for message_data in message:
                 if message_data.name=='avg_speed':
                     message_data.value = (sm_cumul - prev_sess_cumul) / (ts - prev_sess_ts).total_seconds()
                 if message_data.name=='end_position_lat':
                     message_data.value = sm_lat
                 if message_data.name=='end_position_long':
                     message_data.value = sm_lon
                 if message_data.name=='start_position_lat':
                     message_data.value = sess_start_lat
                 if message_data.name=='start_position_long':
                     message_data.value = sess_start_lon
                 if message_data.name=='enhanced_avg_speed':
                     message_data.value = (sm_cumul - prev_sess_cumul) / (ts - prev_sess_ts).total_seconds()
                 if message_data.name=='enhanced_max_speed':
                     message_data.value = lap_max_speed
                 if message_data.name=='max_speed':
                     message_data.value = lap_max_speed
                 if message_data.name=='total_ascent':
                     message_data.value = 0
                 if message_data.name=='total_descent':
                     message_data.value = 0
                 if message_data.name=='total_distance':
                     message_data.value = (sm_cumul - prev_sess_cumul)
                 # TODO : bounding box not considered (fields 27 to 32 ?) = nec & swc


            prev_sess_cumul = sm_cumul
            prev_sess_ts = ts
            sess_max_speed = 0
            sess_start_lat = sm_lat
            sess_start_lon = sm_lon


    #then write fit file
    with FitFileEncoder(outputfitfile, fitfile.protocol_version, fitfile.profile_version) as fwrite:
        for message in messages:
            fwrite.write(message)
        fwrite.finish()

    f.close()
    return

def main(argv):
    CLIhelp =  'smooth_trace.py -i <inputfile> -o <outputfile=inputfile.smooth.fit> --nb=<smoothingpoints=10>\n'
    fitfilename = None
    outfilename = None
    nb=10

    try:
        opts, args = getopt.getopt(argv,"hi:o:",["ifile=","ofile=","nb="])
    except getopt.GetoptError:
        print(CLIhelp)
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print(CLIhelp)
            sys.exit()
        elif opt in ("-i", "--ifile"):
            fitfilename = arg
        elif opt in ("-o", "--ofile"):
            outfilename = arg
        elif opt in ("--nb"):
            nb = int(arg)

    if (fitfilename is None):
        print(CLIhelp)
        sys.exit()

    if (outfilename is None):
        outfilename = fitfilename+'.smooth.fit' 

    smoothfitfile(fitfilename, outfilename, nb)



if __name__ == "__main__":
   main(sys.argv[1:])

