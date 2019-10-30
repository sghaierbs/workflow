# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import content_disposition, dispatch_rpc, request, \
    serialize_exception as _serialize_exception, Response
from odoo.addons.web.controllers import main
import logging
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
            action = self._call_kw(model, method, args, {})

        if isinstance(action, dict) and action.get('type') != '':
            return main.clean_action(action)
        return False