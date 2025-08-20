import time
from odoo import models, fields, api

MERMAID_FLOW_TEMPLATE = """
flowchart TD
    Start[Start Assignment Process] --> Fetch[Fetch Unassigned Requests]
    Fetch --> Sort["Sort Requests:\nPriority Descending\nDate Ascending"]
    Sort --> Precompute[Precompute Employee Workloads]
    Precompute --> Loop[Loop Requests]
    Loop --> Candidates["For Request {request_name}:\nFind Candidates"]
    Candidates --> BestFit["Select Best Fit Employee\n({best_employee})"]
    BestFit --> Assign["Assign Request\nUpdate Workload"]
    Assign --> Next[Next Request]
    Metrics --> End[End]
    """


class Request(models.Model):
    _inherit = 'getmo.request.request'

    @api.model
    def create(self, vals):
        # Existing sequence logic
        if 'type_id' in vals:
            request_type = self.env['getmo.request.type'].browse(vals['type_id'])
            if request_type.sequence_id:
                vals['name'] = request_type.sequence_id.next_by_id()
        return super(Request, self).create(vals)

    def _cron_assign_unassigned_requests(self):
        start_time = time.process_time()
        log_steps = ["Starting request assignment process"]

        # 1. Fetch stage and requests in single query
        assigned_stage = self.env['getmo.request.type.stage'].search(
            [('stage_type', '=', 'assigned')], limit=1)
        if not assigned_stage:
            return

        unassigned_requests = self.search([
            ('assigned_to_id', '=', False),
            ('stage_id.stage_type', '=', 'draft')
        ])
        log_steps.append(f"Found {len(unassigned_requests)} unassigned requests")

        if not unassigned_requests:
            return

        # 2. Precompute all data upfront
        all_employees = self.env['hr.employee'].search([])
        workloads = {emp.id: emp.current_workload for emp in all_employees}
        emp_capacities = {emp.id: emp.daily_capacity for emp in all_employees}

        # 3. Sort requests using efficient tuple comparison
        sorted_requests = unassigned_requests.sorted(
            key=lambda r: (-int(r.priority or '0'), r.date_request))
        log_steps.append("Sorted requests by priority and date:")
        log_steps.extend([f"   - {r.name} (Priority: {r.priority})" for r in sorted_requests])

        assignment_count = 0  # Track successful assignments

        for request in sorted_requests:
            step_log = [f"\nProcessing request: {request.name}"]
            candidates = []

            # 5. Check each responsible employee
            for emp in request.type_id.responsible_employees_ids:
                emp_workload = workloads.get(emp.id, 0)
                emp_capacity = emp_capacities.get(emp.id, 0)
                remaining_capacity = emp_capacity - emp_workload
                can_handle = remaining_capacity >= request.estimated_duration

                candidate_status = (
                    f"   - {emp.name}: "
                    f"Workload {emp_workload:.1f}/{emp_capacity:.1f}h, "
                    f"Remaining {remaining_capacity:.1f}h, "
                    f"Can handle: {'y' if can_handle else 'x'}"
                )
                step_log.append(candidate_status)

                if can_handle:
                    candidates.append((emp, remaining_capacity))

            if not candidates:
                step_log.append("No suitable candidates found")
                log_steps.extend(step_log)
                continue

            # 6. Select best candidate (min remaining capacity)
            best_emp, best_capacity = min(candidates, key=lambda x: (x[1], x[0].id))
            workloads[best_emp.id] += request.estimated_duration

            step_log.append(
                f"Assigned to {best_emp.name} "
                f"(Remaining capacity: {best_capacity - request.estimated_duration:.1f}h)"
            )
            log_steps.extend(step_log)

            # Write assignment immediately
            request.write({
                'assigned_to_id': best_emp.id,
                'date_assigned': fields.Datetime.now(),
            })
            assignment_count += 1

        # 7. Log assignment count
        log_steps.append(f"\nSuccessfully assigned {assignment_count} requests")

        # 8. Calculate metrics
        feasibility_rate = self._compute_feasibility_rate(all_employees, workloads, emp_capacities)
        end_time = time.process_time()
        exec_time = end_time - start_time
        log_steps.extend([
            f"\nFinal Metrics:",
            f"   - Feasibility Rate: {feasibility_rate:.2f}%",
            f"   - Execution Time: {exec_time:.2f}ms"
        ])

        # 9. Create log record
        mermaid_flow = MERMAID_FLOW_TEMPLATE.format(
            request_name=sorted_requests[0].name if sorted_requests else "N/A",
            best_employee=best_emp.name if assignment_count else "None",
            feasibility=feasibility_rate
        )

        self.env['getmo.algorithm.log'].create({
            'name': f"Knapsack Assignment {fields.Datetime.now()}",
            'steps': "\n".join(log_steps),
            'mermaid_flow': mermaid_flow
        })
        print(f"Total runtime of Greedy Knapsack Assign {exec_time:.2f} ms")
        print(f"Knapsack Assign feasibility_rate {feasibility_rate:.2f}%")

    # Optimized metric calculations
    def _compute_feasibility_rate(self, employees, workloads, capacities):
        valid_count = 0
        for emp in employees:
            if workloads.get(emp.id, 0) <= capacities.get(emp.id, 0):
                valid_count += 1
        return (valid_count / len(employees)) * 100 if employees else 100.0
