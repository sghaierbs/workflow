# -*- coding: utf8 -*-
{
    'name': "Workflow Editor",
    'version': '11.0',
    'author': "Ben Selma Sghaier",
    'category': "Extra",
    'summary': "Workflow Editor",
    'depends': ['base','mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/assets.xml',
        'views/workflow_view.xml',
        'views/workflow_model_view.xml',
    ],
    'demo': [],
    'qweb': ['static/src/xml/validation_path.xml'],
    'installable': True,
}