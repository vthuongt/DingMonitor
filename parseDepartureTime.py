import numpy as np
import os
import pandas as pd
import requests
import time
from datetime import datetime
import ipdb
import sys
import socket

from getSunrise import getSunTimes

if socket.gethostname() =='raspi001':
    from picamera import PiCamera

def initCam():
    if socket.gethostname() == 'raspi001':

        cam = PiCamera()
        cam.resolution = (640,480)

        cam.start_preview()
        return cam
    else:
        return None


from IPython.core import ultratb
sys.excepthook = ultratb.FormattedTB(mode='Verbose',
     color_scheme='Linux', call_pdb=1)

from lxml import etree
import logging
logging.basicConfig(filename='parse.log', filemode='w', level=logging.WARNING)
logging.disabled = True



def takeAndSavePhoto(watchingTrainID,cam):
    # TODO implement raspi stuff
    if cam: # not None
        fname = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'_ID'+str(watchingTrainID)+'.jpg'
        cam.capture('./fotos/test/'+fname)




    print('click!_'+ datetime.now().strftime('%Y-%m-%d_%H:%M:%S')+'_ID'+str(watchingTrainID))

def parse_xml(url, verbose=False):
    response = requests.get(url)
    response.raise_for_status()

    logging.debug('get url: '+ url)
    # tree = ElementTree.fromstring(content)
    try:
        tree = etree.fromstring(response.content) #.decode('utf-8'))
        logging.debug('successfully received XML')
    except etree.XMLSyntaxError as e:
        print('Error %s occured while trying to parse xml: %s' % (e, response.content))
        raise

    # tree = etree.fromstring('')

    if verbose:
        print(etree.tostring(tree, pretty_print=True, encoding="unicode"))
        # writes xml response to file
    xml_object = etree.tostring(tree,
                                pretty_print=True,
                                xml_declaration=True,
                                encoding='UTF-8')

    # TODO can xml be logged via logging module?
    with open("xmlfile.xml", "wb") as writer:
        writer.write(xml_object)
    logging.debug(xml_object.decode("utf-8"))



    curStop = tree.find(".//itdMapItemList").tail


    dmMonitor = []
    for el in tree.iter('itdDeparture'):
        if verbose:
            print('processing node:')
            print(etree.tostring(el, pretty_print=True, encoding="unicode"))

        itdServingLine = el.find("itdServingLine")
        key = itdServingLine.get('key')
        direction = itdServingLine.get("direction")
        linie = itdServingLine.get("number")
        if itdServingLine.get("motType") == '5':
            typ = 'Bus'
        elif itdServingLine.get("motType") == '4':
            typ = 'Tram'
        else:
            raise ValueError('Unkown motType '+itdServingLine.get("motType")+' occured')

        realtime = itdServingLine.get("realtime")

        departure = int(el.get("countdown")) - 1
        platform = el.get("platformName")

        itdNoTrain = itdServingLine.find("itdNoTrain") # sicher? nicht itdServingLine?
        delay = itdNoTrain.get("delay")

        itdRouteDescText = itdServingLine.find("itdRouteDescText")
        routeText = itdRouteDescText.text

        if verbose:
            print(key, direction, linie, typ, realtime)
            print(departure, platform)
            print(delay)
            print(routeText)
        if linie.startswith('N') or linie == 'E' or int(realtime) == 1 and int(linie) <= 16:
            arr =(key, linie, direction, int(departure), typ, routeText)
            dmMonitor.append(arr)


    dmMonitor.sort(key=lambda x: x[2])
    if verbose:
        print('Abfahrt von %s:' % curStop)
        [print('%s Linie %s (ID%s) - nach %s - Abfahrt: %d min - über: %s' %
               (typ, linie, key, direction, departure, routeText))
         for key, linie, direction, departure, typ, routeText in dmMonitor]

    logging.debug('Abfahrt von %s:' % curStop)
    [logging.debug('%s Linie %s (ID%s) - nach %s - Abfahrt: %d min - über: %s' %
           (typ, linie, key, direction, departure, routeText))
     for key, linie, direction, departure, typ, routeText in dmMonitor]


    return dmMonitor

def get_haltepunkt(name='Hauptbahnhof'):
    prefix = '900'
    if isinstance(name, int):
        return prefix + str(name)

    if name == 'Hauptbahnhof':
        return prefix+'1008'
    elif name == 'Römerplatz':
        return prefix+ '1360'
    elif name == 'Saarlandstraße':
        return prefix+ '1380'
    else:
        return None

# TODO retry when failed to get sessionID
# catch request errors?
def get_sessionID(name='Hauptbahnhof'):
    haltepunkt = get_haltepunkt(name)
    if not haltepunkt:
        print('Unknown stop name %s' % name)
        return

    receivedID = False


    while not receivedID:
        response = requests.get('https://www.ding.eu/ding3/XSLT_DM_REQUEST?sessionID=0&type_dm=stopID&name_dm='+haltepunkt+'&useRealtime=1&excludedMeans=0&excludedMeans=6&excludedMeans=10&outputFormat=XML')
        response.raise_for_status()

        try:
            tree = etree.fromstring(response.content)
            receivedID = True
        except etree.XMLSyntaxError as e:
            print('Error %s occured while trying to get session ID: %s' %(e, response.content))
            print('retrying to get sessionID')
            time.sleep(2)


    return tree.get('sessionID')

def generateURL(haltepunkt='Saarlandstraße', limit=10, outputformat='XML'):
    # get sessionID, where the haltepunkt is set
    # then use this id in url
    sessID = get_sessionID(haltepunkt)

    url = 'https://www.ding.eu/ding3/XSLT_DM_REQUEST?useRealtime=1&sessionID=' + sessID + '&requestID=1&dmLineSelectionAll=1&limit=' + \
          str(limit) + '&outputFormat=' +outputformat
    # global DingSessions
    # DingSessions[haltepunkt]= {'isValid':True, 'sessionID':sessID, 'url':url}

    return {'isValid':True, 'sessionID':sessID, 'url':url}

def printETA(stop_name='Saarlandstraße', richtung='Science Park II'):

    try:
        abfahrtMonitor = generateURL(stop_name)
        abfahrtListe = parse_xml(abfahrtMonitor['url'])
    except etree.XMLSyntaxError as e:
        print(e)
        raise
    df = pd.DataFrame(abfahrtListe, columns=['ID', 'linie', 'richtung', 'abfahrt', 'typ', 'route'])
    df = df.loc[df['richtung']==richtung]
    print(df)

def getETA(stop_name='Saarlandstraße', richtung='Science Park II'):
    # global DingSessions
    # if stop_name not in DingSessions or not DingSessions[stop_name]['isValid']:
    #     abfahrtMonitor = generateURL(stop_name)
    # # else:
    #     abfahrtMonitor = DingSessions[stop_name]

    receivedETA = False

    while not receivedETA:
        try:
            abfahrtMonitor = generateURL(stop_name)

            abfahrtListe = parse_xml(abfahrtMonitor['url'])
            receivedETA = True
        except etree.XMLSyntaxError as e:
            print('retry to receive ETA for %s in direction of %s' % (stop_name, richtung))
            time.sleep(2)

    if not abfahrtListe:
        return None # no estimated time of arrival

    df = pd.DataFrame(abfahrtListe, columns=['ID', 'linie', 'richtung', 'abfahrt', 'typ', 'route'])
    logging.debug('read dmMonitor into DataFrame:'+ df.to_string())
    df = df.loc[df['richtung']==richtung]
    logging.debug('filter for direction %s: %s' % (richtung, df.to_string()))

    # can be empty after filtering
    if df.empty:
        return None

    logging.debug('return: '+str(df.iloc[0][['abfahrt','ID']].to_dict()))
    return df.iloc[0][['abfahrt','ID']].to_dict()


def checkStationTrain(name, id):
    stats = getETA(name)
    msg = None
    if not stats:
        msg =  '%s: no ETA while checking for ID %s' % (name, id)
        ret_status = -1
        print(msg)
    else:
        if stats['ID'] != id:
            msg = '%s: next train with different ID arriving in %s min. (expected: %s, received %s)' \
                   % (name,  stats['abfahrt'], id, stats['ID'])
            ret_status = 0
            print(msg)
        else:
            msg =  '%s: train %s coming in %s' % (name, id, stats['abfahrt'])
            ret_status = +1
            print(msg)
    return ret_status, msg


def trainIsComing():
    sld = getETA('Saarlandstraße')

    if not sld:
        print("Saarlandstraße: no ETA while checking for Coming")
    else:
        if  sld['abfahrt'] < 0: # can be 0, -1 and >=0
            watchingTrainID = sld['ID']
            print('train is coming, watching train ID '+ str(watchingTrainID))
            return True, sld['abfahrt'], sld['ID']
        else:
            print('Saarlandstraße in %s min' % (sld['abfahrt'],))
            return False, sld['abfahrt'], sld['ID']

    return False, None, None

def trainHasArrived(watchingTrainID):
    rmp = getETA('Römerplatz')

    if not rmp:
        print("Römerplatz: no ETA while checking for Arrival")
    else:
        if rmp['ID'] != watchingTrainID:
            print('train has arrived: old ID %s -> %s' % (str(watchingTrainID), rmp['ID']))
            return True
        else:
            pass
            # msg = 'train (ID: %s) has not arrived yet' % str(watchingTrainID)

    return False



def main():
    take_photo_every = 5
    check_departure_every = 30
    delay_saarlandstr_roemerplatz = 10

    camera = initCam()

    while True:


        try:
            isComing, abfahrt, id = trainIsComing()
            if isComing:
                time.sleep(delay_saarlandstr_roemerplatz)
                while not trainHasArrived(id):
                    t_start = time.time()
                    takeAndSavePhoto(id,camera)

                    checkStationTrain('Saarlandstraße', id)
                    checkStationTrain('Römerplatz', id)

                    t_end = time.time()
                    if t_end - t_start < take_photo_every: #otherwise spend enough time in take foto!
                        time.sleep(take_photo_every- (t_end-t_start))

            elif abfahrt:
                time.sleep(60*(abfahrt/2))
            elif abfahrt == 0:
                time.sleep(1)
            else:#abfahrt is none
                time.sleep(check_departure_every)
        except requests.exceptions.RequestException as e:
            logging.error('%s' % e)
            print('%s' % e)
            time.sleep(60)


    ipdb.set_trace()



if __name__ == '__main__':
    main()


