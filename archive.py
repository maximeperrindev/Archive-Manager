import configparser
import requests
import urllib
import zipfile
import logging
import logging.config
import os
import hashlib
import tarfile
from datetime import datetime, timedelta
from webdav3.client import Client
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


def send_success_mail(receiver):
    try:
        today = datetime.today().strftime('%H:%M')
        conservation = server_conf["CONSERVATION_TIME"]
        msg = MIMEMultipart()
        msg['From'] = 'Archive Manager'
        msg['To'] = receiver
        msg['Subject'] = 'Notification : Archiving completed'
        message = "Hello, \n The archiving of the file was completed at "+ today+". \n The operation was successful and will be repeated in "+ conservation +" days. \n See you soon"
        msg.attach(MIMEText(message))
        mailserver = smtplib.SMTP('smtp.gmail.com', 587)
        mailserver.ehlo()
        mailserver.starttls()
        mailserver.ehlo()
        mailserver.login(mail_conf['USERNAME'], mail_conf['PASSWORD'])
        mailserver.sendmail(receiver, receiver, msg.as_string())
        mailserver.quit()
        print("Mail sent to "+receiver)
    except:
        print("Error while sending mail to "+ receiver)

def send_error_mail(receiver):
    try:
        today = datetime.today().strftime('%H:%M')
        conservation = server_conf["CONSERVATION_TIME"]
        msg = MIMEMultipart()
        msg['From'] = 'Archive Manager'
        msg['To'] = receiver
        with open("archive.log", "rb") as fil:
            part = MIMEApplication(
                fil.read(),
                Name= os.path.basename('archive.log')
            )
        # After the file is closed
        part['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename('archive.log')
        msg['Subject'] = 'Notification : Error while archiving'
        message = "Hello, \n The archiving of the file failed at "+ today+". \n The operation was unsuccessful and will be repeated in "+ conservation +" days. \n You can check the log report in attachment. \n See you soon"
        msg.attach(MIMEText(message))
        msg.attach(part)
        mailserver = smtplib.SMTP('smtp.gmail.com', 587)
        mailserver.ehlo()
        mailserver.starttls()
        mailserver.ehlo()
        mailserver.login(mail_conf['USERNAME'], mail_conf['PASSWORD'])
        mailserver.sendmail(receiver, receiver, msg.as_string())
        mailserver.quit()
        print("Mail sent to "+receiver)
    except:
        print("Error while sending mail to "+ receiver)
def make_tarfile(output_filename, source_dir):
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))

def hash_file(filename):
   """"This function returns the SHA-1 hash
   of the file passed into it"""

   # make a hash object
   h = hashlib.sha1()

   # open file for reading in binary mode
   with open(filename,'rb') as file:

       # loop till the end of the file
       chunk = 0
       while chunk != b'':
           # read only 1024 bytes at a time
           chunk = file.read(1024)
           h.update(chunk)

   # return the hex representation of digest
   return h.hexdigest()

def hash_zip(zipfile):
    sha1 = hashlib.sha1()
    blocksize = 1024**2  #1M chunks
    while True:
        block = zipfile.read(blocksize)
        if not block:
            break
        sha1.update(block)
    return sha1.hexdigest()

def dowloadFileFromUrl(url):
    file_name = url.split('/')[-1]
    u = urllib.request.urlopen(url)
    f = open(file_name, 'wb')
    meta = u.info()
    file_size = int(u.info()["Content-Length"])
    print("Downloading: %s Bytes: %s" % (file_name, file_size))

    file_size_dl = 0
    block_sz = 8192
    prct = 0.0
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break
        file_size_dl += len(buffer)
        f.write(buffer)
        prct = (file_size_dl, file_size_dl * 100. / file_size)
        progress = r"%10d  [%3.2f%%]" % prct
        print(progress)

    if prct[1] == 100.00:
        logger.info(file_name+ "("+ str(file_size)+" bytes) "+ "downloaded with success")
    else:
        logger.error("Can't download " + file_name+" (", str(file_size)+ " bytes)")
    f.close()
    return file_name

## SUCCESS VARIABLE
success = False
## GET CONFIG
config = configparser.ConfigParser()
config.read('conf.ini')
file_conf = config['FILE']
server_conf = config['SERVER']
mail_conf = config['MAIL']
## INSTANCE LOG FILE
logger = logging.getLogger("archive")   # > set up a new name for a new logger

logger.setLevel(logging.DEBUG)  # here is the missing line

log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler = logging.FileHandler("archive.log")
log_handler.setLevel(logging.DEBUG)
log_handler.setFormatter(log_format)
logger.addHandler(log_handler)


## LOG STARTUP
logger.info("Starting script...")

## DOWNLOAD FILE FROM SERVER
r = requests.get(file_conf['URL'], allow_redirects=True)
if r.status_code != 404:
    print('Resource found ! Downloading...')
    file_name = dowloadFileFromUrl(file_conf['URL'])
else:
    logger.error(file_conf['URL'], " not found (HTTP ERROR 404)")

## UNZIP DOWLOADED ZIP AND EXTRACT TO /resources
with zipfile.ZipFile(file_name, 'r') as zip_ref:
   listOfFileNames = zip_ref.namelist()
   nbDownload = 0
   same = False
   for fileName in listOfFileNames:
       print(fileName)
       if fileName == file_conf['SQLFILE']:
           # Extract a single file from zip
            hash = hash_zip(zip_ref.open(fileName))
            if os.path.isfile("./resources/"+file_conf['SQLFILE']):
                if hash == hash_file("./resources/"+file_conf['SQLFILE']):
                    same = True
                    logger.error(file_conf['SQLFILE']+ " same as yesterday (hash: "+hash+")")
                else:
                    zip_ref.extract(fileName, "./resources")
                    nbDownload+=1
            else:
                zip_ref.extract(fileName, "./resources")
                nbDownload+=1
if nbDownload == 0:
    logger.error(file_conf['SQLFILE']+ " not extracted ! Aborting...")
else:
    logger.info(file_conf['SQLFILE']+ ' extracted with success in /resources/'+fileName)

## CONNECTION TO A REMOTE SERVER (WEBDAV)
options = {
'webdav_hostname': server_conf['URL'],
'webdav_login':    server_conf['USERNAME'],
'webdav_password': server_conf['PASSWORD']
}
try:
    logger.info("Connecting to remote server...")
    client = Client(options)
    client.verify = False # To not check SSL certificates (Default = True)
    client.mkdir('archive')
    logger.info("Connected !")
    ## CHECK CONSERVATION TIME FOR .tgz FILES
    expiration = datetime.today() - timedelta(days=int(server_conf['CONSERVATION_TIME']))
    try:
        logger.info('Checking for expired files...')
        files = client.list("archive", get_info=True)
        for file in files:
            if file['content_type'] == 'application/x-gzip':
                date_str = file['path'].split('/')[3].split('.')[0]
                date_file = datetime.strptime(date_str, '%Y%d%m')
                if date_file < expiration:
                    path = file["path"].split('/')[0] + "/"+file["path"].split('/')[1]
                    print(path)
                    client.clean(path)
                    logger.info(date_str+".tgz too old ! Deleting...")
        logger.info('Folder is up to date !')
        success = True
    except:
        logger.error("Error while checking for expired files")

    ## CREATE .tgz FILE AND UPLOAD
    if not same:
        ## CREATE AAAADDMM.tgz FILE
        today = datetime.today().strftime('%Y%d%m')
        new_filename = today+".tgz"
        make_tarfile("./resources/"+new_filename, "./resources/"+file_conf['SQLFILE'])
        logger.info(new_filename+" file created in ./resources")
        print(new_filename+" file created in ./resources")

        ## UPLOAD .tgz ON SERVER
        try:
            client.upload_sync(remote_path="archive/"+new_filename, local_path="./resources/"+new_filename)
            logger.info("Uploaded !")
            success = True
        except:
            success = False
            logger.error("Error while uploading data to server")
except:
    logger.error("Error while connecting to server : " + server_conf['URL'])

## SENDING MAILS
mail_list = mail_conf['MAIL_LIST'].split(' ')
if success:
    for mail in mail_list:
        send_success_mail(mail)

else:
    for mail in mail_list:
        send_error_mail(mail)