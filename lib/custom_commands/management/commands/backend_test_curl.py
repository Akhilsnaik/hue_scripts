#!/usr/bin/env python
import os
import sys
import logging
import datetime
import time
import subprocess

from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import ugettext_lazy as _t, ugettext as _

import desktop.conf
from desktop.conf import TIME_ZONE
from search.conf import SOLR_URL, SECURITY_ENABLED as SOLR_SECURITY_ENABLED
from liboozie.conf import OOZIE_URL, SECURITY_ENABLED as OOZIE_SECURITY_ENABLED
from hadoop import conf as hdfs_conf
from hadoop import cluster

from hue_curl import Curl

DEFAULT_LOG_DIR = 'logs'
log_dir = os.getenv("DESKTOP_LOG_DIR", DEFAULT_LOG_DIR)

current_milli_time = lambda: int(round(time.time() * 1000))

def get_service_info(service):
  service_info = {}
  if service.lower() == 'solr':
    service_info['url'] = SOLR_URL.get()
    service_info['security_enabled'] = SOLR_SECURITY_ENABLED.get()
  if service.lower() == 'oozie':
    service_info['url'] = OOZIE_URL.get()
    service_info['security_enabled'] = OOZIE_SECURITY_ENABLED.get()
  if service.lower() == 'httpfs':
    hdfs_config = hdfs_conf.HDFS_CLUSTERS['default']
    service_info['url'] = hdfs_config.WEBHDFS_URL.get()
    service_info['security_enabled'] = hdfs_config.SECURITY_ENABLED.get()
  if service.lower() == 'rm':
    yarn_cluster = cluster.get_cluster_conf_for_job_submission()
    service_info['url'] = yarn_cluster.RESOURCE_MANAGER_API_URL.get()
    service_info['security_enabled'] = yarn_cluster.SECURITY_ENABLED.get()
  if service.lower() == 'jhs':
    yarn_cluster = cluster.get_cluster_conf_for_job_submission()
    service_info['url'] = yarn_cluster.HISTORY_SERVER_API_URL.get()
    service_info['security_enabled'] = yarn_cluster.SECURITY_ENABLED.get()
  if service.lower() == 'sparkhs':
    yarn_cluster = cluster.get_cluster_conf_for_job_submission()
    service_info['url'] = yarn_cluster.SPARK_HISTORY_SERVER_URL.get()
    service_info['security_enabled'] = yarn_cluster.SPARK_HISTORY_SERVER_SECURITY_ENABLED.get()

  if 'url' not in service_info:
    logging.info("Hue does not have %s configured, cannot test %s" % (service, service))
  elif service_info['url'] is None:
    logging.info("Hue does not have %s configured, cannot test %s" % (service, service))

  if service_info['url'].endswith('/'):
    service_info['url'] = service_info['url'][:-1]

  return service_info


def add_service_test(available_services, options=None, service_name=None, testname=None, suburl=None, method='GET', teststring=None, test_options=None):
  if options['service'] == "all" or options['service'] == service_name.lower():
    if not service_name in available_services:
      service_info = get_service_info(service_name)
      url = service_info['url']
      security_enabled = service_info['security_enabled']
      available_services[service_name] = {}
      available_services[service_name]['url'] = url
      available_services[service_name]['security_enabled'] = security_enabled
    # Tests
    if not 'tests' in available_services[service_name]:
      available_services[service_name]['tests'] = {}
    if not testname in available_services[service_name]['tests']:
      str.replace("TIMEZONE", TIME_ZONE.get())
      str.replace("DOAS", options['username'])
      for test_option in test_options.keys():
        str.replace(test_option, test_options[test_option])
      available_services[service_name]['tests'][testname] = {}
      available_services[service_name]['tests'][testname]['url'] = '%s/%s' % (available_services[service_name]['url'], suburl)
      available_services[service_name]['tests'][testname]['method'] = method
      available_services[service_name]['tests'][testname]['test'] = teststring


class Command(BaseCommand):
  """
  Handler for renaming duplicate User objects
  """

  try:
    from optparse import make_option
    option_list = BaseCommand.option_list + (
      make_option("--service", help=_t("Comma separated services to test, all, httpfs, solr, oozie, rm, jhs, sparkhs."),
                  action="store", default='all', dest='service'),
      make_option("--testname", help=_t("Test for a given service, must only include one service name."),
                  action="store", default=None, dest='testname'),
      make_option("--testoptions", help=_t("Comma separated list of options for test. IE: oozie_job=0000778-190820133637006-oozie-oozi-C,getlogs=true"),
                  action="store", default=None, dest='testoptions'),
      make_option("--showcurl", help=_t("Show curl commands."),
                  action="store_true", default=False, dest='showcurl'),
      make_option("--response", help=_t("Show entire REST response."),
                  action="store_true", default=False, dest='entireresponse'),
      make_option("--username", help=_t("User to doAs."),
                  action="store", default="admin", dest='username'),
      make_option("--verbose", help=_t("Verbose."),
                  action="store_true", default=False, dest='verbose'),
    )

  except AttributeError, e:
    baseoption_test = 'BaseCommand' in str(e) and 'option_list' in str(e)
    if baseoption_test:
      def add_arguments(self, parser):
        parser.add_argument("--service", help=_t("Comma separated services to test, all, httpfs, solr, oozie, rm, jhs, sparkhs."),
                    action="store", default='all', dest='service'),
        parser.add_argument("--testname", help=_t("Test for a given service, must only include one service name."),
                    action="store", default=None, dest='testname'),
        parser.add_argument("--testoptions", help=_t("Comma separated list of options for test. IE: oozie_job=0000778-190820133637006-oozie-oozi-C,getlogs=true"),
                    action="store", default=None, dest='testoptions'),
        parser.add_argument("--showcurl", help=_t("Show curl commands."),
                    action="store_true", default=False, dest='showcurl'),
        parser.add_argument("--response", help=_t("Show entire REST response."),
                    action="store_true", default=False, dest='entireresponse'),
        parser.add_argument("--username", help=_t("User to doAs."),
                    action="store", default="admin", dest='username'),
        parser.add_argument("--verbose", help=_t("Verbose."),
                    action="store_true", default=False, dest='verbose')
    else:
      logging.exception(str(e))
      sys.exit(1)

  def handle(self, *args, **options):
    test_options = {}
    test_options['TIME_ZONE'] = TIME_ZONE.get()
    test_options['DOAS'] = options['username']
    test_options['NOW'] = current_milli_time()
    test_options['NOWLESSMIN'] = test_options['NOW'] - 60000
    if options['testoptions'] is not None:
      test_options = {}
      for test_option in options['testoptions'].split(','):
        option, option_value = test_option.split('=')
        test_options[option.upper()] = option_value

    test_services = options['service'].split(',')
    supported_services = ['all', 'httpfs', 'solr', 'oozie', 'rm', 'jhs', 'sparkhs']
    allowed_tests = {}
    allowed_tests['httpfs'] = []
    allowed_tests['httpfs']['USERHOME'] = None

    allowed_tests = {}
    allowed_tests['jhs'] = []
    allowed_tests['jhs']['FINISHED'] = None

    allowed_tests = {}
    allowed_tests['oozie'] = []
    allowed_tests['oozie']['STATUS'] = None
    allowed_tests['oozie']['JOBLOG'] = "oozie_id=0000001-190820133637006-oozie-oozi-C"

    allowed_tests = {}
    allowed_tests['rm'] = []
    allowed_tests['rm']['CLUSTERINFO'] = None

    allowed_tests = {}
    allowed_tests['solr'] = []
    allowed_tests['solr']['JMX'] = None

    if options['testname'] is not None:
      if len(supported_services) > 1 or "all" in supported_services:
        logging.exception("When using --testname you must only submit one service name and you must not use all")
        sys.exit(1)

      if options['testname'] not in allowed_tests[options['service'].lower()]:
        logging.exception("--testname %s not found in allowed_tests for service %s" % (options['testname'], options['service']))
        logging.exception("Allowed tests for service %s: %s" % (options['service'], allowed_tests[options['service'].lower()]))


    if not any(elem in test_services for elem in supported_services):
      logging.exception("Your service list does not contain a supported service: %s" % options['service'])
      logging.exception("Supported services: all, httpfs, solr, oozie, rm, jhs, sparkhs")
      logging.exception("Format: httpfs,solr,oozie")
      sys.exit(1)

    if not all(elem in supported_services for elem in test_services):
      logging.exception("Your service list contains an unsupported service: %s" % options['service'])
      logging.exception("Supported services: all, httpfs, solr, oozie, rm, jhs, sparkhs")
      logging.exception("Format: httpfs,solr,oozie")
      sys.exit(1)

    if options['service'] == 'sparkhs':
      logging.exception("Spark History Server not supported yet")
      sys.exit(1)

    logging.info("%s" % str(NOW))
    logging.info("Running REST API Tests on Services: %s" % options['service'])
    curl = Curl(verbose=options['verbose'])

    available_services = {}

    #Add Solr
    add_service_test(available_services, options=options, service_name="Solr", testname="JMX",
                     suburl='jmx', method='GET', teststring='solr.solrxml.location', test_options=test_options)

    #Add Oozie
    add_service_test(available_services, options=options, service_name="Oozie", testname="STATUS",
                     suburl='v1/admin/status?timezone=TIME_ZONE&user.name=hue&doAs=DOAS', method='GET',
                     teststring='{"systemMode":"NORMAL"}', test_options=test_options)

    add_service_test(available_services, options=options, service_name="Oozie", testname="JOBLOG",
                     suburl='v2/job/OOZIE_ID?timezone=TIME_ZONE&show=log&user.name=hue&logfilter=&doAs=DOAS', method='GET',
                     teststring='{"systemMode":"NORMAL"}', test_options=test_options)

    #Add HTTPFS
    add_service_test(available_services, options=options, service_name="Httpfs", testname="USERHOME",
                     suburl='user/DOAS?op=GETFILESTATUS&user.name=hue&DOAS=%s', method='GET',
                     teststring='"type":"DIRECTORY"', test_options=test_options)

    #Add RM
    add_service_test(available_services, options=options, service_name="RM", testname="CLUSTERINFO",
                     suburl='ws/v1/cluster/info', method='GET', teststring='"clusterInfo"', test_options=test_options)

    #Add JHS
    add_service_test(available_services, options=options, service_name="JHS", testname="FINISHED",
                     suburl='ws/v1/history/mapreduce/jobs?finishedTimeBegin=NOWLESSMIN&finishedTimeEnd=NOW', method='GET',
                     teststring='"{"jobs":"', test_options=test_options)

    for service in available_services:
      for service_test in available_services[service]['tests']:
        logging.info("Running %s %s Test:" % (service, service_test))
        response = curl.do_curl_available_services(available_services[service]['tests'][service_test])
        if available_services[service]['tests'][service_test]['test'] in response:
          logging.info("TEST: %s %s: Passed: %s found in response" % (service, service_test, available_services[service]['tests'][service_test]['test']))
        if options['entireresponse']:
          logging.info("TEST: %s %s: Response: %s" % (service, service_test, response))

    log_file = log_dir + '/backend_test_curl.log'
    print ""
    print "Tests completed, view logs here: %s" % log_file
    print "Report:"
    cmd = 'grep -A1000 "%s" %s | grep "TEST:" | sed "s/.*INFO.*TEST:/  TEST:/g"' % (str(NOW), log_file)
    grep_process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    grep_response = grep_process.communicate()[0]
    print "%s" % grep_response
    print ""
    print "OS Repro Commands are:"
    cmd = 'grep -A1000 "%s" %s | grep "OSRUN:" | sed "s/.*INFO.*OSRUN:/  /g"' % (str(NOW), log_file)
    grep_process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    grep_response = grep_process.communicate()[0]
    print "%s" % grep_response




