# -*- coding: utf8 -*-
from odoo import models, tools, fields, api, _
from odoo import SUPERUSER_ID
from odoo.osv import expression
from odoo.osv.orm import setup_modifiers
from odoo.tools.safe_eval import safe_eval
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import ValidationError, UserError, Warning
from datetime import datetime, date, time, timedelta
from lxml import etree
import random
import string
import logging
_logger = logging.getLogger(__name__)

CONDITION_CODE_TEMP = """# Available locals:
#  - time, date, datetime, timedelta: Python libraries.
#  - env: Odoo Environement.
#  - model: Model of the record on which the action is triggered.
#  - obj: Record on which the action is triggered if there is one, otherwise None.
#  - user, Current user object.
#  - workflow: Workflow engine.
#  - syslog : syslog(message), function to log debug information to Odoo logging file or console.
#  - warning: warning(message), Warning Exception to use with raise.


result = True"""

PYTHON_CODE_TEMP = """# Available locals:
#  - time, date, datetime, timedelta: Python libraries.
#  - env: Odoo Environement.
#  - model: Model of the record on which the action is triggered.
#  - obj: Record on which the action is triggered if there is one, otherwise None.
#  - user, Current user object.
#  - workflow: Workflow engine.
#  - syslog : syslog(message), function to log debug information to Odoo logging file or console.
#  - warning: warning(message), Warning Exception to use with raise.
# To return an action, assign: action = {...}
"""

MODEL_DOMAIN = """[
        ('state', '=', 'base'),
        ('transient', '=', False),
        '!',
        '|',
        '|',
        '|',
        '|',
        '|',
        '|',
        '|',
        ('model', '=ilike', 'res.%'),
        ('model', '=ilike', 'ir.%'),
        ('model', '=ilike', 'odoo.workflow%'),
        ('model', '=ilike', 'bus.%'),
        ('model', '=ilike', 'base.%'),
        ('model', '=ilike', 'base_%'),
        ('model', '=', 'base'),
        ('model', '=', '_unknown'),
    ]"""


class OdooWorkflow(models.Model):
    _name = 'workflow.workflow'
    _description = 'Odoo Workflow'

    
    
    name = fields.Char('Name')
    model_id = fields.Many2one('ir.model', string='Model', required=True, domain=MODEL_DOMAIN)
    state_ids = fields.One2many('workflow.state', 'workflow_id', string='States')
    action_ids = fields.One2many('workflow.action', 'workflow_id', string='Actions')



    _sql_constraints = [
        ('uniq_name', 'unique(name)', _("Workflow name must be unique.")),
        ('uniq_model', 'unique(model_id)', _("Model must be unique.")),
    ]

    @api.multi
    def btn_reload_workflow(self):
        from odoo.addons import workflow
        return workflow.update_workflow(self)


    @api.onchange('model_id')
    def _onchange_ir_model(self):
        # insert workflow.state in state_ids
        if self.model_id:
            field_names = self.env[self.model_id.model].fields_get(allfields=['state'])
            selection_tuples = field_names['state']['selection'] if 'state' in field_names else False
            cmd = [(2,id) for id in self.state_ids.ids]
            if selection_tuples and len(selection_tuples):
                flow_start = True
                for element in selection_tuples:
                    cmd.append((0, 0, {'technical_name': element[0], 'name': element[1],'flow_start':flow_start}))
                    if flow_start:
                        flow_start = False
            self.update({'state_ids': cmd})

            cmd = [(2,id) for id in self.action_ids.ids]
            for el in self.model_id.view_ids.filtered(lambda r:r.type == 'form' and r.mode == 'primary'):
                arch = etree.XML(el.arch_db)
                buttons = arch.xpath("//form/header/button")
                for element in buttons:
                    cmd.append((0, 0, 
                        {
                            'name': element.get('name'),
                            'type': element.get('type'),
                            'description':element.get('string')}))
            self.update({'action_ids': cmd})


    def get_out_transitions(self, state):
        '''
            from a given state (workflow.state) get all the possible transition to other states (workflow.state)
        '''
        pass 



    def get_required_validations(self):
        '''
            get the list of users that needs to validate the document 
            in order to move it from one state to another.
        '''
        pass

    @api.model
    def create(self, vals):
        return super(OdooWorkflow, self).create(vals)

    @api.multi
    def write(self, vals):
        return super(OdooWorkflow, self).write(vals)


class WorkflowActions(models.Model):
    _name = 'workflow.action'


    name = fields.Char('Name')
    type = fields.Char('Type')
    description = fields.Char('Description')
    workflow_id = fields.Many2one('workflow.workflow', string='Workflow', ondelete='cascade')




class WorkflowTransition(models.Model):
    _name = 'workflow.transition'


    name = fields.Char('Name')
    action_id = fields.Many2one('workflow.action', string='Action', ondelete='cascade')
    state_from = fields.Many2one('workflow.state', string='State from')
    state_to = fields.Many2one('workflow.state', string='State to')
    workflow_id = fields.Many2one('workflow.workflow', string='Workflow')
    # user_ids = fields.Many2many('res.users', string='User')
    user_validation_ids = fields.One2many('user.validation', 'validation_transition_id')


    @api.onchange('action_id','state_from')
    def _onchange_action_id(self):
        for rec in self:
            if rec.action_id:
                rec.update({'name':rec.action_id.description})
            
            if isinstance(rec.id, int) and rec.state_from and rec.state_from.workflow_id:
                rec.workflow_id = rec.node_id.workflow_id.id
            elif self._context.get('default_workflow_id', False):
                rec.workflow_id = self._context.get('default_workflow_id', False)



class WorkflowValidation(models.Model):
    _name = 'user.validation'
    _order = 'sequence asc'

    sequence = fields.Integer(string='Sequence', default=1)
    name = fields.Char(string='Name')
    validation_transition_id = fields.Many2one('workflow.transition')
    type = fields.Selection([('group','By Role'),('user','By User')], default='group', required=True)
    user_id = fields.Many2one('res.users', string='User')
    group_id = fields.Many2one('res.groups', string='Role')


    @api.onchange('type','group_id','user_id')
    def _onchange_name(self):
        name = 'Role %s'%self.group_id.name if self.type == 'group' else 'User %s'%self.user_id.name
        self.update({'name':name})



class WorkflowStates(models.Model):
    _name = 'workflow.state'


    name = fields.Char('Name')
    technical_name = fields.Char('Technical name')
    workflow_id = fields.Many2one('workflow.workflow', string='Workflow', ondelete='cascade')
    flow_start = fields.Boolean(string='Workflow start', default=False)
    flow_end = fields.Boolean(string='Workflow end', default=False)
    is_visible = fields.Boolean('Is Visible')

    out_transition_ids = fields.One2many('workflow.transition', 'state_from', string='Out Transition links')
    in_transition_ids = fields.One2many('workflow.transition', 'state_to', string='In Transition links')



    @api.multi
    def unlink(self):
        return super(WorkflowStates, self).unlink()

    @api.multi
    def write(self, vals):
        return super(WorkflowStates, self).write(vals)
