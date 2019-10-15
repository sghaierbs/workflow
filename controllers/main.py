# -*- coding: utf-8 -*-

import babel.messages.pofile
import base64
import datetime
import functools
import glob
import hashlib
import imghdr
import io
import itertools
import jinja2
import json
import logging
import operator
import os
import re
import sys
import tempfile
import time
import zlib

import werkzeug
import werkzeug.utils
import werkzeug.wrappers
import werkzeug.wsgi
from collections import OrderedDict
from werkzeug.urls import url_decode, iri_to_uri
from xml.etree import ElementTree
import unicodedata


import odoo
import odoo.modules.registry
from odoo.api import call_kw, Environment
from odoo.modules import get_resource_path
from odoo.tools import crop_image, topological_sort, html_escape, pycompat
from odoo.tools.translate import _
from odoo.tools.misc import str2bool, xlwt, file_open
from odoo.tools.safe_eval import safe_eval
from odoo import http
from odoo.http import content_disposition, dispatch_rpc, request, \
    serialize_exception as _serialize_exception, Response
from odoo.exceptions import AccessError, UserError
from odoo.models import check_method_name
from odoo.service import db

from odoo.addons.web.controllers import main

_logger = logging.getLogger(__name__)


class CustomDataSet(main.DataSet):

  
    @http.route('/web/dataset/call_button', type='json', auth="user")
    def call_button(self, model, method, args, domain_id=None, context_id=None):
        
        # check if the current model inherit from workflow.model
        parents = request.env[model]._inherit
        parents = [parents] if isinstance(parents, str) else (parents or [])
        if 'workflow.model' in parents: 
            workflow = request.env['workflow.workflow'].search([('model_id','=',model)])
            if workflow:
                action = request.env[model].trigger_transition(model, method, args, {})
            else:
                print('#### cannot find the associated workflow object')
        else:
            action = self._call_kw(model, method, args, {})

        if isinstance(action, dict) and action.get('type') != '':
            return main.clean_action(action)
        return False