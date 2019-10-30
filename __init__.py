# -*- coding: utf-8 -*-
import re
from . import models
from . import controllers

import itertools
import logging
import sys
import threading
import time
import odoo
import odoo.modules.db
import odoo.modules.graph
import odoo.modules.migration
import odoo.modules.registry
import odoo.tools as tools
from odoo import api, SUPERUSER_ID

from odoo import api, modules
from odoo.models import BaseModel, check_pg_name
from odoo.tools import OrderedSet, LastOrderedSet
from odoo.modules.module import adapt_version, initialize_sys_path, load_openerp_module
from odoo.modules.loading import load_module_graph, load_marked_modules, _check_module_names
_logger = logging.getLogger(__name__)
_test_logger = logging.getLogger('odoo.tests')

# Backup original function for any later use
_build_model_old = BaseModel._build_model

# Backup load_modules function 
load_modules_old = modules.load_modules

regex = r"^_unknown$|odoo\.workflo.+|res\..+|ir\..+" + \
        "|bus\..+|base\..+|base\_.+|^base$"


def load_modules_patched(db, force_demo=False, status=None, update_module=False):
    print('###### CUSTOM LOAD_MODULES')
    initialize_sys_path()

    force = []
    if force_demo:
        force.append('demo')

    models_to_check = set()

    cr = db.cursor()
    try:
        if not odoo.modules.db.is_initialized(cr):
            _logger.info("init db")
            odoo.modules.db.initialize(cr)
            update_module = True # process auto-installed modules
            tools.config["init"]["all"] = 1
            tools.config['update']['all'] = 1
            if not tools.config['without_demo']:
                tools.config["demo"]['all'] = 1

        # This is a brand new registry, just created in
        # odoo.modules.registry.Registry.new().
        registry = odoo.registry(cr.dbname)

        if 'base' in tools.config['update'] or 'all' in tools.config['update']:
            cr.execute("update ir_module_module set state=%s where name=%s and state=%s", ('to upgrade', 'base', 'installed'))

        # STEP 1: LOAD BASE (must be done before module dependencies can be computed for later steps)
        graph = odoo.modules.graph.Graph()
        graph.add_module(cr, 'base', force)
        if not graph:
            _logger.critical('module base cannot be loaded! (hint: verify addons-path)')
            raise ImportError('Module `base` cannot be loaded! (hint: verify addons-path)')

        # processed_modules: for cleanup step after install
        # loaded_modules: to avoid double loading
        report = registry._assertion_report
        loaded_modules, processed_modules = load_module_graph(
            cr, graph, status, perform_checks=update_module,
            report=report, models_to_check=models_to_check)

        load_lang = tools.config.pop('load_language')
        if load_lang or update_module:
            # some base models are used below, so make sure they are set up
            registry.setup_models(cr)

        if load_lang:
            for lang in load_lang.split(','):
                tools.load_language(cr, lang)

        # STEP 2: Mark other modules to be loaded/updated
        if update_module:
            env = api.Environment(cr, SUPERUSER_ID, {})
            Module = env['ir.module.module']
            _logger.info('updating modules list')
            Module.update_list()

            _check_module_names(cr, itertools.chain(tools.config['init'], tools.config['update']))

            module_names = [k for k, v in tools.config['init'].items() if v]
            if module_names:
                modules = Module.search([('state', '=', 'uninstalled'), ('name', 'in', module_names)])
                if modules:
                    modules.button_install()

            module_names = [k for k, v in tools.config['update'].items() if v]
            if module_names:
                modules = Module.search([('state', '=', 'installed'), ('name', 'in', module_names)])
                if modules:
                    modules.button_upgrade()

            cr.execute("update ir_module_module set state=%s where name=%s", ('installed', 'base'))
            Module.invalidate_cache(['state'])


        # STEP 3: Load marked modules (skipping base which was done in STEP 1)
        # IMPORTANT: this is done in two parts, first loading all installed or
        #            partially installed modules (i.e. installed/to upgrade), to
        #            offer a consistent system to the second part: installing
        #            newly selected modules.
        #            We include the modules 'to remove' in the first step, because
        #            they are part of the "currently installed" modules. They will
        #            be dropped in STEP 6 later, before restarting the loading
        #            process.
        # IMPORTANT 2: We have to loop here until all relevant modules have been
        #              processed, because in some rare cases the dependencies have
        #              changed, and modules that depend on an uninstalled module
        #              will not be processed on the first pass.
        #              It's especially useful for migrations.
        previously_processed = -1
        while previously_processed < len(processed_modules):
            previously_processed = len(processed_modules)
            processed_modules += load_marked_modules(cr, graph,
                ['installed', 'to upgrade', 'to remove'],
                force, status, report, loaded_modules, update_module, models_to_check)
            if update_module:
                processed_modules += load_marked_modules(cr, graph,
                    ['to install'], force, status, report,
                    loaded_modules, update_module, models_to_check)

        registry.loaded = True
        registry.setup_models(cr)

        # STEP 3.5: execute migration end-scripts
        migrations = odoo.modules.migration.MigrationManager(cr, graph)
        for package in graph:
            migrations.migrate_module(package, 'end')

        # STEP 4: Finish and cleanup installations
        if processed_modules:
            env = api.Environment(cr, SUPERUSER_ID, {})
            cr.execute("""select model,name from ir_model where id NOT IN (select distinct model_id from ir_model_access)""")
            for (model, name) in cr.fetchall():
                if model in registry and not registry[model]._abstract and not registry[model]._transient:
                    _logger.warning('The model %s has no access rules, consider adding one. E.g. access_%s,access_%s,model_%s,base.group_user,1,0,0,0',
                        model, model.replace('.', '_'), model.replace('.', '_'), model.replace('.', '_'))

            # Temporary warning while we remove access rights on osv_memory objects, as they have
            # been replaced by owner-only access rights
            cr.execute("""select distinct mod.model, mod.name from ir_model_access acc, ir_model mod where acc.model_id = mod.id""")
            for (model, name) in cr.fetchall():
                if model in registry and registry[model]._transient:
                    _logger.warning('The transient model %s (%s) should not have explicit access rules!', model, name)

            cr.execute("SELECT model from ir_model")
            for (model,) in cr.fetchall():
                if model in registry:
                    env[model]._check_removed_columns(log=True)
                elif _logger.isEnabledFor(logging.INFO):    # more an info that a warning...
                    _logger.warning("Model %s is declared but cannot be loaded! (Perhaps a module was partially removed or renamed)", model)

            # Cleanup orphan records
            env['ir.model.data']._process_end(processed_modules)

        for kind in ('init', 'demo', 'update'):
            tools.config[kind] = {}

        cr.commit()

        # STEP 5: Uninstall modules to remove
        if update_module:
            # Remove records referenced from ir_model_data for modules to be
            # removed (and removed the references from ir_model_data).
            cr.execute("SELECT name, id FROM ir_module_module WHERE state=%s", ('to remove',))
            modules_to_remove = dict(cr.fetchall())
            print('######### CUSTOM MODULES TO REMOVE ',modules_to_remove)
            if modules_to_remove:
                env = api.Environment(cr, SUPERUSER_ID, {})
                pkgs = reversed([p for p in graph if p.name in modules_to_remove])
                for pkg in pkgs:
                    uninstall_hook = pkg.info.get('uninstall_hook')
                    if uninstall_hook:
                        py_module = sys.modules['odoo.addons.%s' % (pkg.name,)]
                        getattr(py_module, uninstall_hook)(cr, registry)

                Module = env['ir.module.module']
                Module.browse(modules_to_remove.values()).module_uninstall()
                # Recursive reload, should only happen once, because there should be no
                # modules to remove next time
                cr.commit()
                _logger.info('Reloading registry once more after uninstalling modules')
                api.Environment.reset()
                registry = odoo.modules.registry.Registry.new(
                    cr.dbname, force_demo, status, update_module
                )
                registry.check_tables_exist(cr)
                cr.commit()
                return registry

        # STEP 5.5: Verify extended fields on every model
        # This will fix the schema of all models in a situation such as:
        #   - module A is loaded and defines model M;
        #   - module B is installed/upgraded and extends model M;
        #   - module C is loaded and extends model M;
        #   - module B and C depend on A but not on each other;
        # The changes introduced by module C are not taken into account by the upgrade of B.
        if models_to_check:
            registry.init_models(cr, list(models_to_check), {'models_to_check': True})

        # STEP 6: verify custom views on every model
        if update_module:
            env = api.Environment(cr, SUPERUSER_ID, {})
            View = env['ir.ui.view']
            for model in registry:
                try:
                    View._validate_custom_views(model)
                except Exception as e:
                    _logger.warning('invalid custom view(s) for model %s: %s', model, tools.ustr(e))

        if report.failures:
            _logger.error('At least one test failed when loading the modules.')
        else:
            _logger.info('Modules loaded.')

        # STEP 8: call _register_hook on every model
        env = api.Environment(cr, SUPERUSER_ID, {})
        for model in env.values():
            model._register_hook()

        # STEP 9: save installed/updated modules for post-install tests
        registry.updated_modules += processed_modules
        cr.commit()

    finally:
        cr.close()

  

print('####### MONKY PATCHED load_modules function',modules.load_modules)
modules.load_modules = load_modules_patched


def update_workflow(self):
    """
    Updates Odoo model and registry to apply new workflow changes.
    :return:
    """
    wkf_obj = self.env['workflow.workflow'].sudo()
    t_models = [model.model for model in wkf_obj.search([]).mapped('model_id')]
    # Update
    self.env.cr.commit()
    api.Environment.reset()
    reg = modules.registry.Registry.new(self.env.cr.dbname, update_module=True)
    reg.init_models(self.env.cr, t_models, {})
    self.env.cr.commit()
    # Reload client
    return {
        'type': 'ir.actions.client',
        'tag': 'reload',
    }

def inherit_workflow_manager(cr, model):
    """
    This method inherits new workflow engine
    if assigned for current model.

    :param cr: Database cursor
    :param model: Current model instance
    :return: List of inherited models
    """

    # Variables
    model_name = model._name
    is_transient = model._transient
    is_abstract = model._abstract
    parents = model._inherit
    parents = [parents] if isinstance(parents, str) else (parents or [])
    if isinstance(model_name, str):
        # Check model
        if not re.match(regex, model_name) and not is_transient and not is_abstract:
            # Validate that workflow table created in database
            sql = """SELECT EXISTS (
                     SELECT 1 FROM information_schema.tables 
                     WHERE table_schema = 'public' 
                     AND table_name = 'workflow_workflow');
                  """
            cr.execute(sql)
            res = cr.dictfetchall()
            res = res and res[0] or {}
            if res.get('exists', False):
                # Check for model's workflow
                sql = """SELECT * FROM workflow_workflow wkf, ir_model im 
                         WHERE wkf.model_id = im.id 
                         AND im.model = '%s';""" % model_name
                cr.execute(sql)
                for rec in cr.dictfetchall():
                    # Apply inheritance
                    print('##### model_name ',model_name)
                    if rec.get('model', False) == model_name:
                        if 'workflow.model' not in parents:
                            
                            # if hasattr(model, 'state'):
                            #     delattr(model, 'state')
                            parents.insert(0, 'workflow.model')
                            print('##### INSERTED PARENT ',parents)
                        elif 'workflow.model' in parents:
                            pass
                        if rec.get('mail_thread_add', False):
                            if 'mail.thread' not in parents:
                                parents.append('mail.thread')
                            if 'ir.needaction_mixin' not in parents:
                                parents.append('ir.needaction_mixin')
    return parents

# Monkey Patched _build_model method
@classmethod
def _build_model_new(cls, pool, cr):
    """ Instantiate a given model in the registry.

        This method creates or extends a "registry" class for the given model.
        This "registry" class carries inferred model metadata, and inherits (in
        the Python sense) from all classes that define the model, and possibly
        other registry classes.

    """

    # Keep links to non-inherited constraints in cls; this is useful for
    # instance when exporting translations
    cls._local_constraints = cls.__dict__.get('_constraints', [])
    cls._local_sql_constraints = cls.__dict__.get('_sql_constraints', [])

    # determine inherited models
    parents = inherit_workflow_manager(cr, cls)
    parents = [parents] if isinstance(parents, str) else (parents or [])

    # determine the model's name
    name = cls._name or (len(parents) == 1 and parents[0]) or cls.__name__

    # all models except 'base' implicitly inherit from 'base'
    if name != 'base':
        parents = list(parents) + ['base']

    # create or retrieve the model's class
    if name in parents:
        if name not in pool:
            raise TypeError("Model %r does not exist in registry." % name)
        ModelClass = pool[name]
        ModelClass._build_model_check_base(cls)
        check_parent = ModelClass._build_model_check_parent
    else:
        ModelClass = type(name, (BaseModel,), {
            '_name': name,
            '_register': False,
            '_original_module': cls._module,
            '_inherit_children': OrderedSet(),  # names of children models
            '_inherits_children': set(),  # names of children models
            '_fields': {},  # populated in _setup_base()
        })
        check_parent = cls._build_model_check_parent

    # determine all the classes the model should inherit from
    bases = LastOrderedSet([cls])
    for parent in parents:
        if parent not in pool:
            raise TypeError("Model %r inherits from non-existing model %r." % (name, parent))
        parent_class = pool[parent]
        if parent == name:
            for base in parent_class.__bases__:
                bases.add(base)
        else:
            check_parent(cls, parent_class)
            bases.add(parent_class)
            parent_class._inherit_children.add(name)
    ModelClass.__bases__ = tuple(bases)

    # determine the attributes of the model's class
    ModelClass._build_model_attributes(pool)

    check_pg_name(ModelClass._table)

    # Transience
    if ModelClass._transient:
        assert ModelClass._log_access, \
            "TransientModels must have log_access turned on, " \
            "in order to implement their access rights policy"

    # link the class to the registry, and update the registry
    ModelClass.pool = pool
    pool[name] = ModelClass

    # backward compatibility: instantiate the model, and initialize it
    model = object.__new__(ModelClass)
    model.__init__(pool, cr)

    return ModelClass

BaseModel._build_model = _build_model_new

