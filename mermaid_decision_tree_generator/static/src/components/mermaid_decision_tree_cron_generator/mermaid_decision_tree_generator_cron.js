/** @odoo-module **/

import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from '@web/session';
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

class KnapsackCronFlowchart extends Component {
    static template = "mermaid_decision_tree_generator.KnapsackCronFlowchartTemplate";

    setup() {
        this.orm = useService("orm");

        this.state = useState({ loading: true, error: false });

        onWillStart(async () => {
            // Get context from environment
            const context = this.props.action.context;

            if (context.log_id) {
                const log = await this.orm.read(
                    "knapsack.assignment.log",
                    [context.log_id],
                    ["cron_mermaid_flowchart"]
                );
                this.flowchart = log[0].cron_mermaid_flowchart;
            } else {
                console.error("log_id not found in context");
                this.state.error = true;
            }
        });

        onMounted(async () => {
            if (this.state.error) return;

            try {
                if (!window.mermaid) {
                    await loadJS("/mermaid_decision_tree_generator/static/src/js/mermaid.min.js");
                }

                window.mermaid.initialize({
                    startOnLoad: false,
                    securityLevel: 'loose'
                });

                if (this.flowchart) {
                    const { svg } = await window.mermaid.render('flowchart', this.flowchart);
                    this.state.loading = false;
                    const container = document.getElementById('flowchart-container');
                    container.innerHTML = svg;
                }
            } catch (error) {
                console.error('Mermaid error:', error);
                this.state.loading = false;
                this.state.error = true;
            }
        });
    }
}

registry.category("actions").add("knapsack_flowchart_cron", KnapsackCronFlowchart);