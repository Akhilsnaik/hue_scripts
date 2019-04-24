#!/usr/bin/env python
import os
import time
import uuid

from importlib import import_module

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import ugettext_lazy as _t, ugettext as _
from datetime import date, timedelta
from django.db.utils import DatabaseError
import desktop.conf
from desktop.models import Directory, Document2
from django.contrib.auth.models import User
from desktop.auth.backend import find_or_create_user, rewrite_user, ensure_has_a_group
from useradmin.models import get_profile, get_default_user_group, UserProfile
from notebook.connectors.base import get_api, Notebook
import logging
import logging.handlers


import desktop.conf

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
  """
  Handler for moving orphaned docs
  """

  try:
    from optparse import make_option
    option_list = BaseCommand.option_list + (
      make_option("--keep-days", help=_t("Number of days of history data to keep."),
          action="store",
          type=int,
          default=30),
    )

  except AttributeError, e:
    baseoption_test = 'BaseCommand' in str(e) and 'option_list' in str(e)
    if baseoption_test:
      def add_arguments(self, parser):
        parser.add_argument("--keep-days", help=_t("Number of days of history data to keep."),
          action="store",
          type=int,
          default=30)
    else:
      LOG.exception(str(e))
      sys.exit(1)

  def handle(self, *args, **options):

    LOG.warn("HUE_CONF_DIR: %s" % os.environ['HUE_CONF_DIR'])
    LOG.info("DB Engine: %s" % desktop.conf.DATABASE.ENGINE.get())
    LOG.info("DB Name: %s" % desktop.conf.DATABASE.NAME.get())
    LOG.info("DB User: %s" % desktop.conf.DATABASE.USER.get())
    LOG.info("DB Host: %s" % desktop.conf.DATABASE.HOST.get())
    LOG.info("DB Port: %s" % str(desktop.conf.DATABASE.PORT.get()))
    LOG.info("Removing any orphaned docs")

    start = time.time()

    totalUsers = User.objects.filter().values_list("id", flat=True)
    totalDocs = Document2.objects.exclude(owner_id__in=totalUsers)
    docstorage_id = "docstorage" + str(uuid.uuid4())
    docstorage_id = docstorage_id[:30]
    LOG.info("Creating new owner for all orphaned docs: %s" % docstorage_id)
    docstorage = find_or_create_user(docstorage_id)
    docstorage = rewrite_user(docstorage)
    userprofile = get_profile(docstorage)
    userprofile.first_login = False
    userprofile.save()
    ensure_has_a_group(docstorage)
    new_home_dir = Document2.objects.create_user_directories(docstorage)

    for doc in totalDocs:
      if not doc.type == "directory":
        name = doc.name
        new_dir_name = "recover-" + str(doc.owner_id)
        new_sub_dir = Directory.objects.create(name=new_dir_name, owner=docstorage, parent_directory=new_home_dir)
        doc2 = doc.copy(name=name, owner=docstorage)
        doc2.parent_directory = new_sub_dir
        doc2.save()
        LOG.info("Migrating orphaned workflow: %s : %s : %s : %s : to user: %s" % (doc2.name, doc2.type, doc2.owner_id, doc2.parent_directory, docstorage_id))
        LOG.info("Deleting original orphaned workflow: %s : %s : %s : %s" % (doc.name, doc.type, doc.owner_id, doc.parent_directory))
        doc.delete()

    for doc in totalDocs:
      if doc.type == "directory":
        LOG.info("Deleting orphaned directory: %s : %s : %s" % (doc.name, doc.type, doc.owner_id))
        doc.delete()


    end = time.time()
    elapsed = (end - start)
    LOG.info("Total time elapsed (seconds): %.2f" % elapsed)



