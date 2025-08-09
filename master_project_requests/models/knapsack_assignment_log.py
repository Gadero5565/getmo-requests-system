import json
import ast
from odoo import models, fields, api


class KnapsackLog(models.Model):
    _name = 'knapsack.assignment.log'
    _description = 'Knapsack Algorithm Assignment Log'

    request_id = fields.Many2one(
        'getmo.request.request',
        string='Request',
        readonly=True
    )
    request_type_id = fields.Many2one(
        'getmo.request.type',
        string='Request Type',
        readonly=True
    )
    estimated_duration = fields.Float(
        string='Estimated Duration (hours)',
        readonly=True
    )
    available_employee_ids = fields.Many2many(
        'hr.employee',
        string='Available Employees',
        readonly=True
    )
    employee_workloads = fields.Text(
        string='Employee Workloads',
        help='Stores employee workloads in format {employee_id: workload}',
        readonly=True
    )
    decision_steps = fields.Text(
        string='Decision Steps',
        help='Stores algorithm decision logic in structured format',
        readonly=True
    )
    selected_employee_id = fields.Many2one(
        'hr.employee',
        string='Selected Employee',
        readonly=True
    )
    assignment_reason = fields.Text(
        string='Assignment Reason',
        readonly=True
    )
    no_assignment_reason = fields.Text(
        string='No Assignment Reason',
        readonly=True
    )
    log_date = fields.Datetime(
        string='Log Date',
        default=fields.Datetime.now,
        readonly=True
    )
    knapsack_decision_tree = fields.Text(
        string='Decision Tree',
        readonly=True
    )
    mermaid_flowchart = fields.Text(
        string='Mermaid Flowchart',
        compute='_compute_mermaid_flowchart',
        store=True
    )
    cron_mermaid_flowchart = fields.Text(
        string='Cron Mermaid Flowchart',
        help='Mermaid flowchart showing the complete cron assignment process including priority sorting'
    )

    @api.depends('decision_steps')
    def _compute_mermaid_flowchart(self):
        for log in self:
            if not log.decision_steps:
                log.mermaid_flowchart = "flowchart TD \n    A[No decision steps logged]"
                continue

            # Parse decision_steps (handle both JSON and Python string formats)
            try:
                steps = json.loads(log.decision_steps)
            except:
                try:
                    steps = ast.literal_eval(log.decision_steps)
                except:
                    steps = []

            flowchart = ["flowchart TD"]
            node_id = 0

            # START Node
            start_id = f"N{node_id}"
            flowchart.append(f"    {start_id}[START]")
            node_id += 1

            # Request Type Node
            type_id = f"N{node_id}"
            type_label = (
                f"Request Type: {log.request_type_id.name} \n"
                f"({log.estimated_duration:.2f} hours)"
            )
            flowchart.append(f"    {type_id}[\"{type_label}\"]")
            flowchart.append(f"    {start_id} --> {type_id}")
            node_id += 1

            # Available Employees Node
            emp_count = len(steps)
            emp_id = f"N{node_id}"
            emp_label = f"Available Employees: {emp_count}"
            flowchart.append(f"    {emp_id}[\"{emp_label}\"]")
            flowchart.append(f"    {type_id} --> {emp_id}")
            node_id += 1

            # Current Workloads Node
            workload_id = f"N{node_id}"
            flowchart.append(f"    {workload_id}[\"Current Workloads\"]")
            flowchart.append(f"    {emp_id} --> {workload_id}")
            node_id += 1

            # Employee Workload Sub-nodes
            workload_nodes = []
            for step in steps:
                w_id = f"N{node_id}"
                label = (
                    f"{step['employee_name']}: "
                    f"{step['current_workload']:.2f}/{step['daily_capacity']:.2f}h\n"
                    f"Remaining: {step['remaining_capacity']:.2f}h"
                )
                flowchart.append(f"    {w_id}[\"{label}\"]")
                flowchart.append(f"    {workload_id} --> {w_id}")
                workload_nodes.append(w_id)
                node_id += 1

            # Evaluation Criteria Node
            eval_id = f"N{node_id}"
            flowchart.append(f"    {eval_id}[\"Evaluation Criteria\"]")
            flowchart.append(f"    {emp_id} --> {eval_id}")
            node_id += 1

            # Condition Nodes
            cond_id = f"N{node_id}"
            cond_label = (
                f"Can handle request?\n"
                f"capacity ≥ {log.estimated_duration:.2f}h"
            )
            flowchart.append(f"    {cond_id}{{\"{cond_label}\"}}")
            flowchart.append(f"    {eval_id} --> {cond_id}")
            node_id += 1

            rule_id = f"N{node_id}"
            rule_label = "Select employee with \nMAX remaining capacity"
            flowchart.append(f"    {rule_id}[\"{rule_label}\"]")
            flowchart.append(f"    {cond_id} --> |Yes| {rule_id}")
            node_id += 1

            # Employee Evaluation Nodes
            eval_nodes = []
            for step in steps:
                e_id = f"N{node_id}"
                status = "Capable" if step['can_handle'] else "Incapable"
                details = f"{step['employee_name']}: {step['remaining_capacity']:.2f}h → {status}"

                if "New best" in step.get('reason', ''):
                    details += " → New best"
                elif "Tied" in step.get('reason', ''):
                    details += " → Tied"

                flowchart.append(f"    {e_id}[\"{details}\"]")
                flowchart.append(f"    {rule_id} --> {e_id}")
                eval_nodes.append(e_id)
                node_id += 1

            # Decision Node
            decision_id = f"N{node_id}"
            flowchart.append(f"    {decision_id}[\"Decision\"]")
            flowchart.append(f"    {eval_id} --> {decision_id}")
            node_id += 1

            # Tie Break Logic (if applicable)
            if log.assignment_reason and (
                    "multiple" in log.assignment_reason.lower() or "tied" in log.assignment_reason.lower()):
                tie_id = f"N{node_id}"
                tie_label = "Multiple employees with\nsame max capacity"
                flowchart.append(f"    {tie_id}[\"{tie_label}\"]")
                flowchart.append(f"    {decision_id} --> {tie_id}")
                node_id += 1

                rule2_id = f"N{node_id}"
                rule2_label = "Algorithm selects\nfirst encountered"
                flowchart.append(f"    {rule2_id}[\"{rule2_label}\"]")
                flowchart.append(f"    {tie_id} --> {rule2_id}")
                decision_ptr = rule2_id
                node_id += 1
            else:
                decision_ptr = decision_id

            # Result Node
            result_id = f"N{node_id}"
            if log.selected_employee_id:
                result_label = f"RESULT: Assigned to\n {log.selected_employee_id.name}"
            else:
                result_label = "RESULT: Not assigned"

            flowchart.append(f"    {result_id}[\"{result_label}\"]")
            flowchart.append(f"    {decision_ptr} --> {result_id}")

            log.mermaid_flowchart = "\n".join(flowchart)
