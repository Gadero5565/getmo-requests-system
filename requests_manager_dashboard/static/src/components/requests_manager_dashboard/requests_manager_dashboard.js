/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class RequestsManagerDashboard extends Component {
    static template = "dashboard_manager_requests.RequestsManagerDashboard";

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            data: null,
            error: null
        });

        onWillStart(async () => {
            try {
                this.state.data = await this.rpc("/api/managers/dashboard", {});
                this.state.loading = false;
            } catch (error) {
                this.state.error = error;
                this.state.loading = false;
            }
        });
    }

    openRequest(requestId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'request.request',
            res_id: requestId,
            views: [[false, 'form']],
            target: 'current'
        });
    }
}

registry.category("actions").add("requests_manager_dashboard", RequestsManagerDashboard);