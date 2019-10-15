odoo.define('workflow.path_widget', function(require) {
    "use strict";


    var Widget = require('web.Widget');
    var core = require('web.core');
    var registry = require('web.field_registry');
    var rpc = require('web.rpc')

    var Qweb = core.qweb;
    var _t = core._t;

    console.log('#### FILE LOADED')


    var PathWidget = Widget.extend({
	    cssLibs: [],
	    jsLibs: [],
	    // events: {
	    //     'keydown': '_onKeydown',
	    // },
	    // custom_events: {
	    //     navigation_move: '_onNavigationMove',
	    // },


	    resetOnAnyFieldChange: true,


	    init: function (parent, name, record, options) {
	        this._super(parent);
	        options = options || {};
            console.log('######## CALL TO INIT function parent ',parent)
            console.log('######## CALL TO INIT function name ',name)
            console.log('######## CALL TO INIT function record ',record)
            console.log('######## CALL TO INIT function options ',options)

            // 'name' is the field name displayed by this widget
            this.name = name;

            // the datapoint fetched from the model
            this.record = record;

            // the 'field' property is a description of all the various field properties,
            // such as the type, the comodel (relation), ...
            this.field = record.fields[name];

            // this property tracks the current (parsed if needed) value of the field.
            // Note that we don't use an event system anymore, using this.get('value')
            // is no longer valid.
            this.value = record.data[name];

            // the 'viewType' is the type of the view in which the field widget is
            // instantiated. For standalone widgets, a 'default' viewType is set.
            this.viewType = options.viewType || 'default';


            // this is the res_id for the record in database.  Obviously, it is
            // readonly.  Also, when the user is creating a new record, there is
            // no res_id.  When the record will be created, the field widget will
            // be destroyed (when the form view switches to readonly mode) and a new
            // widget with a res_id in mode readonly will be created.
            this.res_id = record.res_id;

            // useful mostly to trigger rpcs on the correct model
            this.model = record.model;


	    },
	    willStart: function(){
            console.log('##### CALL WILLSTART METHODE',this);
            var self = this;
            return $.when(
                rpc.query({
                    args: [[this.res_id],{}],
                    model: this.model,
                    method: 'get_workflow_data',
                }).then(function(result){
                    console.log('##### RESULTS ', result)
                    // self.validation_state_ids = result['validation_state_ids']
                    // console.log('#### VALIDATION STATE IDS ',self.validation_state_ids)
                    // self.validation_transition_ids =  self.validation_state_ids[0]['validation_transition_ids']
                    // self.validation_element_ids = self.validation_transition_ids[0]['validation_element_ids']
                    // // self._render()
                    // console.log('### Result of call back',self.validation_element_ids)
                })
            );
        },
	    start: function(){
	    	console.log('##### CALL TO START METHODE')
	    	this._super(parent);
		},
        /**
         * @override
         */
        isSet: function () {
            return true;
        },
        getFocusableElement: function () {
            return $();
        },

	});

	registry.add('control_path_widget', PathWidget)
});
