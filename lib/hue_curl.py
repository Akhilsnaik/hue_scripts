import os
import sys
import logging
import datetime
import time
import subprocess

from cm_environment import check_security
from hue_shared import which

#logging.basicConfig()
#logging = logging.getLogger(__name__)

class Curl(object):

  def __init__(self, verbose=False):
    self.curl = which('curl')
    if self.curl is None:
      logging.exception("curl is required, please install and rerun")
      sys.exit(1)

    # We will change to handle certs later
    self.basecmd = self.curl + ' -k'
    logging.info("Checking security status")
    self.security_enabled = check_security()
    self.verbose = verbose

    if self.security_enabled:
      self.basecmd = self.basecmd + ' --negotiate -u :'

    if self.verbose:
      self.basecmd = self.basecmd + ' -v'
    else:
      self.basecmd = self.basecmd + ' -s'

  def do_curl(self, url, method='GET', follow=False, args=None):

    cmd = self.basecmd + ' -X ' + method
    if follow:
      cmd = cmd + ' -L'

    if args is not None:
      cmd = cmd + ' ' + args

    cmd = cmd + ' \'' + url + '\''
    logging.info("OSRUN: %s" % cmd)
    curl_process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    curl_response = curl_process.communicate()[0]
    curl_ret = curl_process.returncode
    if curl_ret > 0:
      logging.exception("Curl failed to run succesfully: %s" % curl_response)
    return curl_response


  def do_curl_available_services(self, service_test):
    url = service_test['url']
    method = service_test['method']
    response = self.do_curl(url, method=method)
    return response
