odoo.define('workflow.widget', function(require) {
    "use strict";

    var AbstractField = require('web.AbstractField');
    var Widget = require('web.Widget');
    var core = require('web.core');
    var registry = require('web.field_registry');
    var rpc = require('web.rpc')

    var Qweb = core.qweb;
    var _t = core._t;


    var ValidationPath = AbstractField.extend({
        tagName: 'div',
        template:'ValidationPath',
        custom_events: _.extend({}, AbstractField.prototype.custom_events, {
            add_record: '_onAddRecord',
        }),

        // We need to trigger the reset on every changes to be aware of the parent changes
        // and then evaluate the 'column_invisible' modifier in case a evaluated value
        // changed.
        resetOnAnyFieldChange: true,

        /**
         * useSubview is used in form view to load view of the related model of the x2many field
         */
        useSubview: true,

        /**
         * @override
         */
        init: function (parent, name, record, options) {
            var self = this;
            this._super.apply(this, arguments);
            this.validation_state_ids = [];
            this.validation_transition_ids = [];
            this.validation_element_ids = [];
            this.data = [];
        },
        willStart: function(){
            var self = this;
            return $.when(
                rpc.query({
                    args: [[this.res_id],{}],
                    model: this.model,
                    method: 'get_workflow_data',
                }).then(function(result){
                    self.data = result;
                    self.validation_state_ids = result['validation_state_ids']
                    if(self.validation_state_ids && self.validation_state_ids.length)
                        self.validation_transition_ids =  self.validation_state_ids[0]['validation_transition_ids']
                    if(self.validation_transition_ids && self.validation_transition_ids.length)
                        self.validation_element_ids = self.validation_transition_ids[0]['validation_element_ids']
                })
            );
        },

        /**
         * @override
         */
        start: function () {
            this._super(parent);
            // this.data = ['sghaier','ben', 'selma'];
        },

        /**
         * @override
         */
        isSet: function () {
            return true;
        },

        renderElement: function () {
            var $el;
            if (this.template) {
                $el = $(core.qweb.render(this.template, {widget: this}).trim());
            } else {
                $el = this._make_descriptive();
            }
            this.replaceElement($el);
        },


        // _render: function () {
        //     console.log('#### rendering the template ',this.data)
            
        //     this.$el.html(Qweb.render(this.template, {widget:this,data:this.data}));
        //     // var self = this
        //     // console.log('##### RENDER ',self.data)
        //     // return this._super.apply(this, arguments).then(function () {
        //     //     var values = self.data;
        //     //     var helpdesk_dashboard = QWeb.render(self.template, {
        //     //         widget: self,
        //     //         dataset: {'sghaier':'PPPPP','ben':'lkjlk', 'selma':'lkcd'},
        //     //     });
        //     //     self.$el.prepend(helpdesk_dashboard);
        //     // });
        // },

        /**
         * @override
         * @param {Object} record
         * @param {OdooEvent} [ev] an event that triggered the reset action
         * @param {Boolean} [fieldChanged] if true, the widget field has changed
         * @returns {Deferred}
         */
        reset: function (record, ev, fieldChanged) {
            return this._super.apply(this, arguments);
        },

    
    });


    //registry.add('path_widget', PathWidget)

    // core.form_widget_registry.add('ValidationPath', ValidationPath);
    // return {ValidationPath:ValidationPath};
    registry.add('ValidationPath', ValidationPath);
});