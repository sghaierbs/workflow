# -*- coding: utf8 -*-
from odoo import models, fields, api
from odoo import SUPERUSER_ID
from odoo.osv.orm import setup_modifiers
from odoo.tools.safe_eval import safe_eval as eval
from odoo.exceptions import ValidationError, UserError, Warning
from datetime import datetime, date, time, timedelta
from lxml import etree

from odoo.api import call_kw, Environment
import logging
_logger = logging.getLogger(__name__)



class ValidationElement(models.Model):
    _name = 'validation.element'
    _order = 'sequence asc'
    _description = '''
        This is a model that will hold the list of required approval by users
        and the state of each element in the path 
        User 1 (done) --->   User 2 (done)  --->  User 3 (not yet)
        - the original method won't be called unless the User 3 validate it
    '''

    user_id = fields.Many2one('res.users', string='User', required=True)
    sequence = fields.Integer(string='Sequence')
    done = fields.Boolean(string='Validated', default=False)
    validation_transition_id = fields.Many2one('validation.transition', ondelete='cascade')


    @api.multi
    def get_json_data(self):
        result = []
        for rec in self:
            result.append({'id':rec.id,'user_id':{'id':rec.user_id.id,'name':rec.user_id.name},'done':rec.done,'sequence':rec.sequence})
        return result


class ValidationTransition(models.Model):
    _name = 'validation.transition'
    _description = '''
        This is a model that represents a transition between 
        two state and the action (method) that needs to be called 
        to trigger the transition'''

    name = fields.Char('Name', help='Description of the action to trigger')
    action_name = fields.Char('Action to trigger', help='Actual name of the method that will be called')
    type = fields.Char('Action type')

    # list of required validation in order to trigger a transition 
    validation_element_ids = fields.One2many('validation.element', 'validation_transition_id')
    
    # state from which this transition can be triggered
    validation_state_id = fields.Many2one('validation.state', ondelete='cascade')

    @api.multi
    def get_json_data(self):
        result = []
        for rec in self:
            result.append({
                'id':rec.id,
                'name':rec.name,
                'action_name':rec.action_name,
                'type':rec.type,
                'validation_element_ids':rec.validation_element_ids.get_json_data(),
            })
        return result


class ValidationStates(models.Model):
    _name = 'validation.state'
    _description = '''
        This model represent the state for each model
    '''


    name = fields.Char(string='Name')
    technical_name = fields.Char(string='Technical name')
    workflow_id = fields.Many2one('workflow.workflow')

    # main object to manage transition from each state
    transition_manager_id = fields.Many2one('transition.manager', ondelete='cascade')

    # outgoing workflow transition 
    validation_transition_ids = fields.One2many('validation.transition', 'validation_state_id')

    
    @api.multi
    def get_json_data(self):
        result = []
        for rec in self:
            result.append({
                'id':rec.id,
                'name':rec.name,
                'technical_name':rec.technical_name,
                'validation_transition_ids':rec.validation_transition_ids.get_json_data(),
            })
        return result


class ValidationStack(models.Model):
    _name ='transition.manager'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    done = fields.Boolean(string='Validated', default=False)
    workflow_id = fields.Many2one('workflow.workflow')
    validation_state_ids = fields.One2many('validation.state', 'transition_manager_id')    


    @api.multi
    def get_current_validation_state(self, state):
        self.ensure_one()
        res = self.validation_state_ids.filtered(lambda r: r.technical_name == state)
        if len(res) > 1:
            raise ValidationError('Found more than one validation state with the same technical name')
        else:
            return res

    def trigger_transition(self, state, action_name):
        # print('###### validation states for model ',self.validation_state_ids)
        validation_state = self.validation_state_ids.search([('technical_name','=',state)],limit=1)
        # print("VALIDATION STATE ",validation_state.name)
        transition_id = validation_state.validation_transition_ids.search([('action_name','=',action_name)],limit=1)
        # print("TRANSITION ID ",transition_id.name)
        validation_element = transition_id.validation_element_ids
        # for element in validation_element:
        #     print('##### VALIDATION ELEMENT NAME ',element.user_id.name)
        
        res = self.env['validation.element'].search([('validation_transition_id','=',transition_id.id)])
        print("FOUND ELEMENT  ",res)
        for item in res:
            print("FOUND ELEMENT [%s]  DONE %s"%(item.id,item.done))

        if all(validation_element.mapped('done')):
            print('##### ALL element are done',validation_element)
            return True
        else:
            next_element_to_validate = False
            for rec in validation_element.sorted(key=lambda r: r.sequence):
                print('###### FIRST ELEMENT ',rec.user_id.name)
                if not rec.done:
                    next_element_to_validate = rec
                    break
            print('###### THE NEXT ELEMENT IS ',next_element_to_validate.user_id.name)
            if next_element_to_validate and next_element_to_validate.user_id.id == self.env.user.id:
                next_element_to_validate.done = True
                model = self._context.get('model',False)
                model = self.env['ir.model'].search([('model','=',model)])
                ids = self._context.get('ids',False)

                # check if there is still a next step and create an activity depending on the result
                for rec in validation_element:
                    if not rec.done:
                        self.env['mail.activity'].create({
                            'activity_type_id': 4, # To-Do
                            'note': 'Validate this document',
                            'user_id': rec.user_id.id,
                            'res_id': ids[0],
                            'res_model_id': model.id,#self.env.ref('workflow.model_transition_manager').id,
                        })
                        break
            else:
                pass
                raise Warning('you are not allowed to performe this action yet !')

                # if rec.user_id.id == self.env.user.id:
                #     print('##### Setting element to done CONTEXT',self._context) 
                #     model = self._context.get('model',False)
                #     model = self.env['ir.model'].search([('model','=',model)])
                #     ids = self._context.get('ids',False)

                #     self.env['mail.activity'].create({
                #         'activity_type_id': 4, # To-Do
                #         'note': 'Validation the current sale order',
                #         'user_id': self.env.user.id,
                #         'res_id': ids[0],
                #         'res_model_id': model.id,#self.env.ref('workflow.model_transition_manager').id,
                #     })
                #     print('####### UPDATING THE PATH ')
                #     rec.done = True
            if all(validation_element.mapped('done')):
                print('##### Now All Element Are Done') 
                return True
            else:
                return False




    @api.multi
    def get_json_data(self):
        result = []
        for rec in self:
            result.append({
                'id':rec.id,
                'validation_state_ids':rec.get_current_validation_state().get_json_data(),
            })
        return result


    @api.multi
    def get_current_path_data(self, state):
        self.ensure_one()
        
        return {
            'id':self.id,
            'validation_state_ids':self.get_current_validation_state(state).get_json_data()
        }


    @api.multi
    def generate_validation_states(self):
        for rec in self:
            if rec.workflow_id:
                cmd = []
                for state in rec.workflow_id.state_ids:
                    transition_element = []
                    for transition in state.out_transition_ids:
                        validation_element = []
                        for item in transition.user_validation_ids.sorted(key=lambda r: r.sequence):
                            validation_element.append((0, 0, {
                                'sequence':item.sequence,
                                'user_id': item.user_id.id,
                                }))
                        transition_element.append((0, 0, {
                            'name': transition.name,
                            'action_name': transition.action_id.name,
                            'type': transition.action_id.type,
                            'validation_element_ids': validation_element,
                            }))
                    cmd.append((0, 0, {
                        'name': state.name, 
                        'technical_name': state.technical_name,
                        'workflow_id': rec.workflow_id.id,
                        'validation_transition_ids':transition_element,
                        }))
                rec.update({'validation_state_ids':cmd})

    def create(self, vals):
        res = super(ValidationStack, self).create(vals)
        res.generate_validation_states()
        return res


class WorkflowModel(models.Model):
    _name = 'workflow.model'



    name = fields.Char('Name')
    # TO-DO delete the record and it's related objects when deleting 
    # the record that inherit from workflow.model
    transition_manager_id = fields.Many2one('transition.manager', string='Transition manager')
    

    
    @api.multi
    def get_workflow_data(self):
        print('##### RPC CALL ',len(self.transition_manager_id))
        '''
            return data for javascript widget.
        '''
        if self.transition_manager_id:
            return self.transition_manager_id.get_current_path_data(self.state)
        else:
            return []



    @api.model
    def _get_workflow_config(self):
        model_name = self._name
        model_id = self.env[model_name]
        workflow_id = self.env['workflow.workflow'].search([('model_id','=',model_name)])
        if not workflow_id:
            raise ValidationError('No workflow configuration is associated to this model')
        return workflow_id

    @api.multi 
    def check_transition(self, method, args, kwargs):
        '''
            check if it's allowed to move the state to the next one 
            (all steps are valide)
        '''
        if len(self) == 1:
            state = self.state
            action_name = method
            return self.transition_manager_id.with_context(model=self._name,ids=self.ids).trigger_transition(state,action_name)
        else:
            return False





    @api.model
    def trigger_transition(self, model, method, args, kwargs):
        allowed = False
        if len(args):
            ids = args[0] if isinstance(args[0], list) else []
            record = self.env[model].browse(ids)
            allowed = record.check_transition(method, args, kwargs)
            if allowed:
                print('###### ALLOWED')
                return call_kw(self.env[model], method, args, kwargs)
            else:
                print('###### NOT ALLOWED YET')
                return True    
        else:
            return call_kw(self.env[model], method, args, kwargs)



    @api.model
    def create_transition_manager(self):
        workflow_id = self._get_workflow_config()
        print('##### CREATING NEW RECORD ',self._name)
        
        vals = {
            'workflow_id':workflow_id.id,
            'name':workflow_id.name
        }
        record_id = self.env['transition.manager'].create(vals)
        return record_id




    @api.model
    def create(self, vals):
        vals['transition_manager_id'] = self.create_transition_manager().id
        return super(WorkflowModel, self).create(vals)


    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(WorkflowModel, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type in ['tree', 'form']:
            self._get_workflow_config()
        return res

    


    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(WorkflowModel, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        
        model = self._name
        model_obj = self.env[model]

        def _add_field_def_to_view(resource, field_name, field_node):
            resource['fields'].update(model_obj.fields_get(allfields=[field_name]))
            setup_modifiers(field_node, resource['fields'][field_name])
        arch = etree.XML(res['arch'])
        if view_type == 'form':

            # Get Header Element
            header_el = arch.xpath("//form/header")
            header_el = header_el[0] if header_el else False
            
            # Create State Element If not Exists
            if header_el is not False:
                state_el = etree.Element('field')
                state_el.set('name', 'transition_manager_id')
                state_el.set('widget', 'ValidationPath')
                _add_field_def_to_view(res, 'transition_manager_id', state_el)
                header_el.insert(len(header_el)-1,state_el)#append(state_el)
        res['arch'] = etree.tostring(arch, encoding="utf-8")
        return res