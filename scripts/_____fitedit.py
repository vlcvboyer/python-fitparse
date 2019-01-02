from fitparse import FitFile
from fitparse.utils import fit_from_datetime, fit_to_datetime

#from fitparse import FitFileEncoder
from fitparse.encoder import FitFileEncoder, DataMessageCreator
from fitparse.profile import FIELD_TYPES

import json
import sys, getopt
import pytz, datetime, time
from   datetime import datetime, date
import calendar
import math

from dateutil.parser import parse

def verbosefitmessage( message, f ):
    text = ''
    if hasattr(message, 'type'):
        text = message.type.upper() + '   '
    else:
        text = 'UNKNOWN' + '   '
    if hasattr(message, 'name'):
        text = text + 'name=' + message.name + '   '
#        if hasattr(message, 'def_mesg'):
#            text = text + '  ' + 'def_mesg=' + ("%s" % message.def_mesg)
    if hasattr(message, 'mesg_num'):
        text = text + 'mesg_num=' + ("%d" % message.mesg_num) + '   '
    if hasattr(message, 'mesg_type'):
        text = text + 'mesg_type=' + ("%s" % message.mesg_type) + '   '
    print("%s" % text, file=f)
    if message.type == 'definition':
        print("-> ", end="", file=f), print(dict([attr, getattr(message, attr)] for attr in dir(message) if not attr.startswith('_')), file=f)

    # Go through all the data entries in this record
    #if message.name=='record' and message.type == 'data':
    if message.type == 'data':

        # Go through all the data entries in this record
        print('-> ', end='', file=f)
        for message_data in message:

            # Print the records name and value (and units if it has any)
            if message_data.units:
                units = message_data.units
            else:
                units = ''
            print("%s: %s %s ; " % (message_data.name, message_data.value, units, ), end='', file=f)
        print('', file=f)    
    print('', file=f)    

    return

def verbosefitfile( filename, f ):
    "This prints all info contained in a fit file"

    fitfile = FitFile(filename)
    print("file: %s" % (filename, ), file=f)

    "This prints all info contained in a fit object"

    # Get all messages
    for message in fitfile.get_messages(name=None, with_definitions=True):
        verbosefitmessage( message, f )

    return

def fit2csv( filename, f ):
    "This put some vlues in csv file"

    fitfile = FitFile(filename)
    print("file: %s" % (filename, ), file=f)

    # Get all messages
    lat_prev = None
    lon_prev = None
    cumul = 0
    for message in fitfile.get_messages(name=None, with_definitions=True):
        # Go through all the data entries in this record
        if message.name=='record' and message.type == 'data':
            ts = ''
            lat = None
            lon = None
            hr = ''
            alt = ''
            dist = 0

            # Go through all the data entries in this record
            for message_data in message:
                if (message_data.name=='position_lat') and (message_data.value is not None):
                    lat = message_data.value * 180.0 / 2**31
                if (message_data.name=='position_long') and (message_data.value is not None):
                    lon = message_data.value * 180.0 / 2**31
                if message_data.name=='timestamp':
                    ts = message_data.value
                if message_data.name=='altitude':
                    alt = message_data.value
                if message_data.name=='heart_rate':
                    hr = message_data.value

            # calcul distance
            if (lat_prev is not None) and (lon_prev is not None) and (lat is not None) and (lon is not None):
                angle = math.sin(math.radians(lat_prev))*math.sin(math.radians(lat))
                angle = angle + math.cos(math.radians(lat_prev))*math.cos(math.radians(lat))*math.cos(math.radians(lon - lon_prev))
                if angle > 1:
                    angle = 1
                if angle < -1:
                    angle = -1
                dist = math.acos(angle)*6378137.0
                cumul = cumul + dist
            if (lat is not None):
                lat_prev = lat
            if (lon is not None):
                lon_prev = lon

            print("%s, %s, %s, %s, %s, %s, %s" % (ts, lat, lon, alt, hr, dist, cumul, ), file=f)

    return


def sc2lat(sc):
    return sc * 180.0 / 2**31

def sc2lon(sc):
    return sc * 180.0 / 2**31

def dist_sc(lat1_sc, lon1_sc, lat2_sc, lon2_sc):
    if (lat1_sc is not None) and (lon1_sc is not None) and (lat2_sc is not None) and (lon2_sc is not None):
        lat1 = lat1_sc * 180.0 / 2**31
        lon1 = lon1_sc * 180.0 / 2**31
        lat2 = lat2_sc * 180.0 / 2**31
        lon2 = lon2_sc * 180.0 / 2**31
        angle = math.sin(math.radians(lat1))*math.sin(math.radians(lat2))
        angle = angle + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.cos(math.radians(lon2 - lon1))
        return math.acos(-1 if angle < -1 else +1 if angle > 1 else angle)*6378137.0
    return None



def smoothfitfile( filename, fit_f, smooth_width):
    "This removes noise from gps coordinates"

    fitfile = FitFile(filename)
    print("file: %s" % (filename, ))

    # Get all messages
    messages = list(fitfile.get_messages(name=None, with_definitions=True))
    print("original file: %s ; contain %d messages" % (filename, len(messages), ))
    print(" => fixed file: %s" % (fit_f.name, ))

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

    print("nb valid position messages: %d" % (len(positionmessages)))

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
#                 if message_data.name=='total_elapsed_time':
#                     message_data.value = (ts - prev_lap_ts)
#                 if message_data.name=='total_timer_time':
#                     message_data.value = (ts - prev_lap_ts)
# TODO : bounding box not considered (fields 27 to 32 ?)


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
#                 if message_data.name=='total_elapsed_time':
#                     message_data.value = (ts - prev_sess_ts).total_seconds()
#                 if message_data.name=='total_timer_time':
#                     message_data.value = (ts - prev_sess_ts).total_seconds()
# TODO : bounding box not considered (fields 27 to 32 ?) = nec & swc


            prev_sess_cumul = sm_cumul
            prev_sess_ts = ts
            sess_max_speed = 0
            sess_start_lat = sm_lat
            sess_start_lon = sm_lon


    #then write fit file
    with FitFileEncoder(fit_f, fitfile.protocol_version, fitfile.profile_version) as fwrite:
        for message in messages:
            fwrite.write(message)
        fwrite.finish()

    return

def redatefitfile( filename, fit_f, newdate):
    "This changes initial date of activity"

    fitfile = FitFile(filename)
    print("file: %s" % (filename, ))

    # Get all messages
    messages = list(fitfile.get_messages(name=None, with_definitions=True))
    print("original file: %s ; contain %d messages" % (filename, len(messages), ))
    print(" => fixed file: %s" % (fit_f.name, ))

    ############################################################
    # first we find initial timestamp
    ############################################################
    initial_ts = None
    for message in messages:
        if message.type == 'data' :
            for message_data in message:
                # Go through all the data entries in this record
                if message_data.name=='timestamp' and initial_ts is None:
                    initial_ts = message_data.value
                    break
        if initial_ts is not None:
            break

    offset_ts = newdate.timestamp() - initial_ts.timestamp()

    for message in messages:
        if message.type == 'data':
            for message_data in message:

                if message_data.name=='unknown_253':
                    message_ts = fit_to_datetime(message_data.value).timestamp()
                    newmessagedate = datetime.utcfromtimestamp(message_ts + offset_ts)
                    message_data.value = fit_from_datetime(newmessagedate)
                    message_data.raw_value = fit_from_datetime(newmessagedate)

                if message_data.name=='timestamp' or message_data.name=='time_created' or message_data.name=='start_time' or message_data.name=='local_timestamp':
                    message_ts = message_data.value.timestamp()
                    newmessagedate = datetime.utcfromtimestamp(message_ts + offset_ts)
                    message_data.value = newmessagedate
                    message_data.raw_value = fit_from_datetime(newmessagedate)

#                if message_data.name=='timestamp' or message_data.name=='time_created' or message_data.name=='unknown_253':
#                    print("%s raw value %d ; value %s ; offset_ts %s ; newmessagedate %s ; newmessagedate.timestamp %d" % (
#                            message_data.name, message_data.raw_value, message_data.value, offset_ts, newmessagedate, fit_from_datetime(newmessagedate), ))
                    
                    # TODO message_data.value += newdate - initial_ts

    #then write fit file
    with FitFileEncoder(fit_f, fitfile.protocol_version, fitfile.profile_version) as fwrite:
        for message in messages:
            fwrite.write(message)
        fwrite.finish()

    return

def chgsportfitfile( filename, fit_f, sport, sub_sport):
    "This changes sport defined in fit file"

#TODO : check
   # 'session_trigger': FieldType(
   #      name='session_trigger',
   #      base_type=BASE_TYPES[0x00],  # enum
   #      values={
   #          0: 'activity_end',
   #          1: 'manual',  # User changed sport.
   #          2: 'auto_multi_sport',  # Auto multi-sport feature is enabled and user pressed lap button to advance session.
   #          3: 'fitness_equipment',  # Auto sport change caused by user linking to fitness equipment.


    fitfile = FitFile(filename)
    print("file: %s" % (filename, ))

    # Get all messages
    messages = list(fitfile.get_messages(name=None, with_definitions=True))
    print("original file: %s ; contain %d messages" % (filename, len(messages), ))
    print(" => fixed file: %s" % (fit_f.name, ))

    raw_sport = list(FIELD_TYPES['sport'].values.keys())[list(FIELD_TYPES['sport'].values.values()).index(sport)]
    raw_sub_sport = list(FIELD_TYPES['sub_sport'].values.keys())[list(FIELD_TYPES['sub_sport'].values.values()).index(sub_sport)]

    for message in messages:
        if message.type == 'data':
            for message_data in message:

                if message_data.name=='sport':
                    message_data.value = sport
                    message_data.raw_value = raw_sport

                if message_data.name=='sub_sport':
                    message_data.value = sub_sport
                    message_data.raw_value = raw_sub_sport

                if message.name == "sport" and message_data.name=="name":
                    message_data.value = sport

    #then write fit file
    with FitFileEncoder(fit_f, fitfile.protocol_version, fitfile.profile_version) as fwrite:
        for message in messages:
#            ts = None
#            if message.type == 'data':
#                for message_data in message:
#                    if message_data.name=='timestamp':
#                        ts = message_data.value
#            if ts is None:
#                print("message \"%s\" without timestamp" % (message.name,))
#            else:
#                print("message \"%s\" timestamp : %s" % (message.name, ts,))
            fwrite.write(message)
        fwrite.finish()

    return


def lapfitfile( filename, log_f):

    fitfile = FitFile(filename)
    print("file: %s" % (filename, ))

    # Get all messages
    messages = list(fitfile.get_messages(name=None, with_definitions=True))

    for message in messages:
        if (message.type == 'data' and message.name!='record' and message.name!='file_id' and message.name!='file_creator' and message.name!='event'
            and message.name!='hrv' and message.name!='hr'
            and message.name!='device_settings' and message.name!='device_info' and message.name!='user_profile' and message.name!='sport' and message.name!='zones_target'
            and message.name!='unknown_13' and message.name!='unknown_22' and message.name!='unknown_79' and message.name!='unknown_104'
            and message.name!='unknown_141' and message.name!='unknown_140' and message.name!='unknown_147' and message.name!='unknown_216'):
            verbosefitmessage( message, log_f )

    return


def fixfitfile( filename, csv_f, fit_f, log_f, fig_f):
    "This removes noise from gps coordinates"

    fitfile = FitFile(filename)
    print("file: %s" % (filename, ), file=log_f)

    # Get all messages
    messages = list(fitfile.get_messages(name=None, with_definitions=True))
    print("original file: %s ; contain %d messages" % (filename, len(messages), ))
    print(" => fixed file: %s ; %s ; %s ; %s" % (fit_f.name, csv_f.name, log_f.name, fig_f.name, ))

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

    print("nb valid position messages: %d" % (len(positionmessages)))

    ############################################################
    # moving average
    ############################################################
    # TODO : add ts data to add weight to close data
    smooth_width = 10
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
    print("ts; lat; lon; smoothlat; smoothlon; dist; cumul; speed; lat; lon", file=csv_f)

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

            if len(smooth_one)==1:
                print("%s; %f; %f; %f; %f; %f; %f; %f; %f; %f" % (str(ts), raw_lat, raw_lon, sm_lat, sm_lon,
                    sm_dist, sm_cumul, sm_speed, sc2lat(sm_lat), sc2lon(sm_lon), ), file=csv_f)

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
#                 if message_data.name=='total_elapsed_time':
#                     message_data.value = (ts - prev_lap_ts)
#                 if message_data.name=='total_timer_time':
#                     message_data.value = (ts - prev_lap_ts)
# TODO : bounding box not considered (fields 27 to 32 ?)


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
#                 if message_data.name=='total_elapsed_time':
#                     message_data.value = (ts - prev_sess_ts).total_seconds()
#                 if message_data.name=='total_timer_time':
#                     message_data.value = (ts - prev_sess_ts).total_seconds()
# TODO : bounding box not considered (fields 27 to 32 ?) = nec & swc


            prev_sess_cumul = sm_cumul
            prev_sess_ts = ts
            sess_max_speed = 0
            sess_start_lat = sm_lat
            sess_start_lon = sm_lon



    #then write fit file
    i=0
    with FitFileEncoder(fit_f, fitfile.protocol_version, fitfile.profile_version) as fwrite:
        for message in messages:
            i += 1
            print("message %d", (i,))
            verbosefitmessage( message, log_f )
            if (message.type == 'data' and message.name!='record' and message.name!='file_id' and message.name!='file_creator' and message.name!='event'
                and message.name!='device_settings' and message.name!='device_info' and message.name!='user_profile' and message.name!='sport' and message.name!='zones_target'
                and message.name!='unknown_13' and message.name!='unknown_22' and message.name!='unknown_79'
                and message.name!='unknown_141' and message.name!='unknown_140' and message.name!='unknown_147' and message.name!='unknown_216'):
                verbosefitmessage( message, fig_f )
            fwrite.write(message)
        fwrite.finish()

    return


def combinefitfile(fitfilenames, f):
    #this combine multiple fitfiles into one multisport activity

    fitfilenameslist = fitfilenames.split(",")
    print(fitfilenameslist)

    with FitFile(fitfilenameslist[0]) as firstfitfile:
        print("protocol version : %f ; profile version : %f" % (firstfitfile.protocol_version, firstfitfile.profile_version))

        with FitFileEncoder(f, firstfitfile.protocol_version, firstfitfile.profile_version) as fwrite:

            firstfitfile = True
            i = 1  # file count
            sessioncount = 0
            totaltimertime = 0
            for fitfilename in fitfilenameslist:
                lastfitfile = (i == len(fitfilenameslist))
                print("processing file \"%s\"" % (fitfilename,))
                if firstfitfile:
                    print("First file !")
                if lastfitfile:
                    print("Last file !")

                with FitFile(fitfilename) as fitfile:
                    messages = fitfile.messages

                    firstrecordfound = False
                    firstactivityfound = False
                    for message in messages:

                        if message.name=='record':
                            firstrecordfound = True

                        if message.name=='activity':
                            firstactivityfound = True

                        if message.name=='session' and message.type == 'data':
                            sessioncount += 1
                            for message_data in message:
                                 if message_data.name=='total_timer_time':
                                     totaltimertime += message_data.value

                        if message.name=='activity' and message.type == 'data':
                            firstactivityfound = True
                            for message_data in message:
                                 if message_data.name=='num_sessions':
                                     message_data.value = sessioncount
                                 if message_data.name=='total_timer_time':
                                     message_data.value = totaltimertime

                        #first file: write all messages from begining
                        #all files: write all messages from (definition or data) message name="record" to definition message name="activity" (excluded)
                        #last file: write all messages from definition message "name=activity" (included)

                        if (firstfitfile or firstrecordfound) and (lastfitfile or not firstactivityfound):
                            fwrite.write(message)

                firstfitfile = False
                i += 1

            fwrite.finish()







def write_fitfile_copy(fitfilename, f):
    #this copy fit file to another one (in order to validate fit file encoder)
    with FitFile(fitfilename) as fitfile:
        messages = fitfile.messages

    # pour mémoire:
    #def __init__(self, fileish, protocol_version=1.0, profile_version=20.33, data_processor=None):
    print("protocol version : %f ; profile version : %f" % (fitfile.protocol_version, fitfile.profile_version))


    with FitFileEncoder(f, fitfile.protocol_version, fitfile.profile_version) as fwrite:
        for m in messages:
            fwrite.write(m)
        fwrite.finish()




def write_fitfile_copy_original(fitfilename, f):
    #this copy fit file to another one (in order to validate fit file encoder)
    with FitFile(fitfilename) as fitfile:
        messages = fitfile.messages

    with FitFileEncoder(f) as fwrite:
        for m in messages:
            # current encoder can do just basic fields
            m.fields = [field for field in m.fields if field.field_def or FitFileEncoder._is_ts_field(field)]
            # need to unset raw_value
            for field_data in m.fields:
                field_data.raw_value = None
            fwrite.write(m)
        fwrite.finish()

def main(argv):
    CLIhelp =  'fitedit.py -i <inputfile> -o <outputfile> -c <command>\n'
    CLIhelp += '   commands :\n'
    CLIhelp += '       log (exhaustive messages output)\n'
    CLIhelp += '       csv (export records to csv)\n'
    CLIhelp += '       lap (export laps and session messages)\n'
    CLIhelp += '       smooth --nb=10\n'
    CLIhelp += '       redate --date="2018-08-28 15h56m06s"\n'
    CLIhelp += '       sport --sport="swimming" --sub_sport="open_water"\n'
    CLIhelp += '       combine (combine several unitary activities into single multisport activity)\n'
    CLIhelp += '       \n'
    CLIhelp += '   example:\n'
    CLIhelp += '       python fitedit.py -i 1-swim.fit -o 1-swim.fix.fit -c sport --sport="swimming" --sub_sport="open_water"\n'
    CLIhelp += '       python fitedit.py -i 2-trans.fit -o 2-trans.fix.fit -c sport --sport="transition" --sub_sport="swim_to_bike_transition"\n'
    CLIhelp += '       python fitedit.py -i 3-bike.fit -o 3-bike.fix.fit -c sport --sport="cycling" --sub_sport="road"\n'
    CLIhelp += '       python fitedit.py -i 4-trans.fit -o 4-trans.fix.fit -c sport --sport="transition" --sub_sport="bike_to_run_transition"\n'
    CLIhelp += '       python fitedit.py -i 5-run.fit -o 5-run.fix.fit -c sport --sport="running" --sub_sport="street"\n'
    CLIhelp += '       python fitedit.py -i 1-nat.fix.fit -o 1-nat.fix2.fit -c smooth --nb=7\n'
    CLIhelp += '       python fitedit.py -i 1-nat.fix2.fit,2-trans.fix.fit,3-bike.fix.fit,4-trans.fix.fit,5-run.fix.fit -o tri.fit -c combine\n'
    CLIhelp += '       python fitedit.py -i tri.fit -o tri.fix.fit -c redate --date=2018-08-29 10h59m03s"\n'
    CLIhelp += '       \n'


    fitfilename = None
    outfilename = None
    command = None
    newdate = datetime.now().astimezone(pytz.utc)
    sport="generic"
    sub_sport = "generic"
    nb=10

    try:
        opts, args = getopt.getopt(argv,"hi:o:c:",["ifile=","ofile=","command=","date=", "sport=", "sub_sport=", "nb="])
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
        elif opt in ("-c", "--command"):
            command = arg
        elif opt in ("--date"):
            newdate = parse(arg).astimezone(pytz.utc)
        elif opt in ("--sport"):
            sport = arg
        elif opt in ("--sub_sport"):
            sub_sport = arg
        elif opt in ("--nb"):
            nb = int(arg)

    if (fitfilename is None):
        print(CLIhelp)
        sys.exit()

    if (outfilename is None):
        outfilename = fitfilename+'.out' 



    if   command == 'log':
        f = open(outfilename,'w')
        verbosefitfile(fitfilename, f)
        f.close()
    elif command == 'csv':
        f = open(outfilename,'w')
        fit2csv(fitfilename,f)
        f.close()
    elif command == 'lap':
        f = open(outfilename,'w')
        lapfitfile(fitfilename,f)
        f.close()
    elif command == 'smooth':
        f = open(outfilename,'wb')
        smoothfitfile(fitfilename, f, nb)
        f.close()
    elif command == 'redate':
        f = open(outfilename,'wb')
        print("date demandee : %s UTC\n" % newdate)
        redatefitfile(fitfilename, f, newdate)
        f.close()
    elif command == 'sport':
        f = open(outfilename,'wb')
        print("sport: %s ; sub_sport: %s\n" % (sport, sub_sport,))
        chgsportfitfile(fitfilename, f, sport, sub_sport)
        f.close()
    elif command == 'combine':
        f = open(outfilename,'wb')
        combinefitfile(fitfilename, f)
        f.close()





if __name__ == "__main__":
   main(sys.argv[1:])



#TODO:
#  developper data id etc.
#  autofix lap swimming activities
#  add speed when not in records ? (multisport activities does not show speed...)





