import time
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import numpy as np


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

    @api.model
    def cron_assign_unassigned_requests_pso(self):
        start = time.process_time()
        unassigned = self.search([
            ('assigned_to_id', '=', False),
            ('stage_id.stage_type', '=', 'draft')
        ])
        if not unassigned:
            return

        all_employee_ids = set()
        for req in unassigned:
            all_employee_ids |= set(req.type_id.responsible_employees_ids.ids)

        all_employees = self.env['hr.employee'].search([
            ('id', 'in', list(all_employee_ids)),
            ('daily_capacity', '>', 0)
        ])
        n_employees = len(all_employees)
        if n_employees == 0:
            raise UserError("No employees available for assignment.")

        employee_map = {i + 1: emp.id for i, emp in enumerate(all_employees)}
        inv_employee_map = {v: k for k, v in employee_map.items()}

        remaining_capacities = np.array([emp.daily_capacity - emp.current_workload for emp in all_employees])

        priority_levels = ['3', '2', '1', '0']
        assigned_count = 0
        assigned_stage = self.env['getmo.request.type.stage'].search([('stage_type', '=', 'assigned')], limit=1)
        steps = ""

        for prio in priority_levels:
            group_requests = unassigned.filtered(lambda r: r.priority == prio)
            if not group_requests:
                continue

            requests = group_requests
            n_requests = len(requests)

            steps += f"Processing priority {prio} with {n_requests} requests\n"

            request_durations = np.array([req.estimated_duration for req in requests])
            request_priorities = np.ones(n_requests)  # All same priority in group

            possible_assignments = []
            for req in requests:
                poss_emps = req.type_id.responsible_employees_ids
                poss_indices = [inv_employee_map.get(emp.id) for emp in poss_emps if emp.id in inv_employee_map]
                possible_assignments.append(set(poss_indices))

            # PSO parameters
            num_particles = min(50, n_requests * 5)  # Scale with problem size
            max_iterations = 100
            inertia_weight = 0.5
            cognitive_weight = 1.5
            social_weight = 1.5
            max_velocity = n_employees / 2.0

            # Initialize particles: positions [0, n_employees + 1), velocities
            positions = np.random.uniform(0, n_employees + 1, size=(num_particles, n_requests))
            velocities = np.random.uniform(-max_velocity, max_velocity, size=(num_particles, n_requests))

            personal_best_positions = positions.copy()
            personal_best_scores = np.full(num_particles, -np.inf)

            global_best_position = None
            global_best_score = -np.inf

            # Fitness function
            def fitness(position):
                assignments = np.floor(position).astype(int)
                assignments = np.clip(assignments, 0, n_employees)

                total_value = 0.0
                used_capacities = np.zeros(n_employees + 1)
                penalty = 0.0

                for req_idx, emp_idx in enumerate(assignments):
                    if emp_idx == 0:
                        continue
                    if emp_idx not in possible_assignments[req_idx]:
                        penalty += 10000.0  # Constraint violation penalty
                        continue
                    used_capacities[emp_idx] += request_durations[req_idx]
                    total_value += request_priorities[req_idx]

                for emp_idx in range(1, n_employees + 1):
                    excess = used_capacities[emp_idx] - remaining_capacities[emp_idx - 1]
                    if excess > 0:
                        penalty += excess * 1000.0  # Capacity violation penalty

                return total_value - penalty

            # Initialize bests
            for p_idx in range(num_particles):
                score = fitness(positions[p_idx])
                personal_best_scores[p_idx] = score
                if score > global_best_score:
                    global_best_score = score
                    global_best_position = positions[p_idx].copy()

            # PSO loop
            for iteration in range(max_iterations):
                for p_idx in range(num_particles):
                    r1 = np.random.uniform(0, 1, n_requests)
                    r2 = np.random.uniform(0, 1, n_requests)

                    velocities[p_idx] = (
                            inertia_weight * velocities[p_idx] +
                            cognitive_weight * r1 * (personal_best_positions[p_idx] - positions[p_idx]) +
                            social_weight * r2 * (global_best_position - positions[p_idx])
                    )

                    velocities[p_idx] = np.clip(velocities[p_idx], -max_velocity, max_velocity)

                    positions[p_idx] += velocities[p_idx]
                    positions[p_idx] = np.clip(positions[p_idx], 0, n_employees + 1)

                    score = fitness(positions[p_idx])
                    if score > personal_best_scores[p_idx]:
                        personal_best_scores[p_idx] = score
                        personal_best_positions[p_idx] = positions[p_idx].copy()

                    if score > global_best_score:
                        global_best_score = score
                        global_best_position = positions[p_idx].copy()

            # Apply best assignment
            best_assignments = np.floor(global_best_position).astype(int)
            best_assignments = np.clip(best_assignments, 0, n_employees)

            # Create list of assignments (no need to sort since same priority)
            assignment_list = []
            for req_idx, emp_idx in enumerate(best_assignments):
                if emp_idx == 0:
                    continue
                assignment_list.append((req_idx, emp_idx))

            # Assign, updating capacities
            for req_idx, emp_idx in assignment_list:
                if emp_idx not in possible_assignments[req_idx]:
                    continue
                if request_durations[req_idx] > remaining_capacities[emp_idx - 1]:
                    continue  # Skip if would overload
                emp = all_employees[emp_idx - 1]
                requests[req_idx].assigned_to_id = emp
                requests[req_idx].date_assigned = fields.Datetime.now()
                if assigned_stage:
                    requests[req_idx].stage_id = assigned_stage
                remaining_capacities[emp_idx - 1] -= request_durations[req_idx]
                assigned_count += 1

            # Greedy assignment for remaining unassigned requests in this group
            remaining_requests = [req for req in requests if not req.assigned_to_id]
            for req in remaining_requests:
                possible_emps = req.type_id.responsible_employees_ids & all_employees
                possible_emps = possible_emps.filtered(
                    lambda e: e.daily_capacity - e.current_workload >= req.estimated_duration)
                if not possible_emps:
                    continue
                # Choose the employee with the most remaining capacity
                emp = max(possible_emps, key=lambda e: e.daily_capacity - e.current_workload)
                req.assigned_to_id = emp
                req.date_assigned = fields.Datetime.now()
                if assigned_stage:
                    req.stage_id = assigned_stage
                # Update remaining_capacities
                emp_idx = inv_employee_map[emp.id]
                remaining_capacities[emp_idx - 1] -= req.estimated_duration
                assigned_count += 1

        # Log the algorithm execution
        steps += f"PSO executed for {len(unassigned)} unassigned requests.\n"
        steps += f"Number of employees: {n_employees}\n"
        steps += f"Assigned {assigned_count} requests.\n"
        steps += "Key parameters:\n"
        steps += f"- Particles: variable per group, Iterations: {max_iterations}\n"
        steps += f"- Inertia: {inertia_weight}, Cognitive: {cognitive_weight}, Social: {social_weight}\n"
        steps += "Request details affecting decision:\n"
        for req in unassigned:
            steps += f"- Req {req.name}: Duration {req.estimated_duration}, Priority {req.priority}\n"
        steps += "Employee capacities after assignment:\n"
        for emp in all_employees:
            steps += f"- {emp.name}: Remaining {emp.daily_capacity - emp.current_workload}/{emp.daily_capacity}\n"

        mermaid = """
                flowchart TD
                    A[Start PSO Cron] --> B[Collect Unassigned Requests]
                    B --> C[Prepare Employees and Capacities]
                    C --> D{For Each Priority Level}
                    D --> E[Collect Group Requests]
                    E --> F[Prepare Group Data]
                    F --> G[Initialize Particles and Velocities]
                    G --> H[Evaluate Initial Fitness]
                    H --> I[Update Personal and Global Bests]
                    I --> J{Iteration < Max?}
                    J -->|Yes| K[Update Velocities]
                    K --> L[Update Positions]
                    L --> M[Evaluate Fitness]
                    M --> N[Update Bests]
                    N --> J
                    J -->|No| O[Apply Best Assignments]
                    O --> P[Greedy Assignment for Remaining in Group]
                    P --> D
                    D -->|Done| Q[Log Steps and Decisions]
                    Q --> R[End]
                """
        self.env['getmo.algorithm.log'].create({
            'steps': steps,
            'mermaid_flow': mermaid
        })
        end = time.process_time()
        workloads = {emp.id: emp.current_workload for emp in all_employees}
        emp_capacities = {emp.id: emp.daily_capacity for emp in all_employees}
        feasibility_rate = self._compute_feasibility_rate(all_employees, workloads, emp_capacities)
        print(f"Total runtime of PSO Cron Assign {end - start} ms")
        print(f"Knapsack Assign feasibility_rate {feasibility_rate}")

    # Optimized metric calculations
    def _compute_feasibility_rate(self, employees, workloads, capacities):
        valid_count = 0
        for emp in employees:
            if workloads.get(emp.id, 0) <= capacities.get(emp.id, 0):
                valid_count += 1
        return (valid_count / len(employees)) * 100 if employees else 100.0
