import time
from odoo import models, fields, api
from collections import deque
import copy

MERMAID_TABU = """
graph TD
    A[Start]
    A --> B[Initialize solution with greedy]
    B --> C{Stopping criterion?}
    C -->|No| D[Generate neighbors]
    D --> E[Select best non-tabu neighbor or aspiration]
    E --> F[Update current solution]
    F --> G[Update tabu list]
    G --> H[Update best solution if better]
    H --> C
    C -->|Yes| I[End with best solution]
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

    @api.model
    def cron_assign_unassigned_requests_tabu(self):
        start = time.process_time()
        unassigned = self.search([
            ('assigned_to_id', '=', False),
            ('stage_id.stage_type', 'not in', ['done', 'refused'])
        ])
        if not unassigned:
            return
        all_employees = self.env['hr.employee'].search([('daily_capacity', '>', 0)])
        assignment = self._run_tabu_search(unassigned, all_employees)
        for req_id, emp_id in assignment.items():
            if emp_id:
                self.browse(req_id).assigned_to_id = self.env['hr.employee'].browse(emp_id)
                self.browse(req_id).date_assigned = fields.Datetime.now()
        end = time.process_time()
        workloads = {emp.id: emp.current_workload for emp in all_employees}
        emp_capacities = {emp.id: emp.daily_capacity for emp in all_employees}
        feasibility_rate = self._compute_feasibility_rate(all_employees, workloads, emp_capacities)
        print(f"Total runtime of Tabu Search Cron Assign {end - start} ms")
        print(f"Knapsack Assign feasibility_rate {feasibility_rate}")

    def _run_tabu_search(self, unassigned, employees):
        steps = []
        steps.append("Starting Tabu Search for assignment")

        # Prepare data
        req_list = sorted(unassigned, key=lambda r: int(r.priority or '0'), reverse=True)
        req_dict = {
            r.id: {
                'duration': r.estimated_duration,
                'priority': int(r.priority or '0'),
                'eligible': set(r.type_id.responsible_employees_ids.ids)
            } for r in req_list
        }
        emp_remaining_orig = {
            e.id: e.daily_capacity - e.current_workload
            for e in employees if e.daily_capacity - e.current_workload > 0
        }
        req_ids = list(req_dict.keys())
        emp_ids = list(emp_remaining_orig.keys())

        steps.append(f"Data prepared: {len(req_ids)} unassigned requests, {len(emp_ids)} eligible employees")

        # Use large base for priority weighting to enforce strict priority order
        N = len(req_ids) + 1

        def compute_score(assignment):
            return sum(N ** req_dict[rid]['priority'] for rid, eid in assignment.items() if eid)

        # Simulate remaining for a given assignment
        def get_sim_remaining(assignment):
            sim_rem = copy.deepcopy(emp_remaining_orig)
            for rid, eid in assignment.items():
                if eid:
                    sim_rem[eid] -= req_dict[rid]['duration']
            return sim_rem

        # Initial greedy solution: assign to employee with max remaining capacity (least loaded)
        current_assignment = {rid: None for rid in req_ids}
        sim_remaining = copy.deepcopy(emp_remaining_orig)
        for rid in sorted(req_ids, key=lambda rid: req_dict[rid]['priority'], reverse=True):
            candidates = [eid for eid in req_dict[rid]['eligible'] if
                          eid in sim_remaining and sim_remaining[eid] >= req_dict[rid]['duration']]
            if candidates:
                best_eid = max(candidates, key=lambda eid: sim_remaining[eid])
                current_assignment[rid] = best_eid
                sim_remaining[best_eid] -= req_dict[rid]['duration']
                emp_name = self.env['hr.employee'].browse(best_eid).name
                steps.append(
                    f"Greedy assign: Request {rid} to Employee {emp_name} (id {best_eid}, remaining {sim_remaining[best_eid]})")

        current_score = compute_score(current_assignment)
        best_assignment = copy.deepcopy(current_assignment)
        best_score = current_score
        steps.append(
            f"Initial score: {best_score} (assigned: {sum(1 for v in current_assignment.values() if v)} requests)")

        # Tabu list: requests that cannot be moved (deque of request ids)
        tabu = deque(maxlen=max(5, len(req_ids) // 5))  # Adaptive size

        max_iterations = 200
        stagnation_limit = 30
        stagnation_counter = 0

        for iteration in range(max_iterations):
            steps.append(f"Iteration {iteration + 1}")
            neighbors = []

            # Generate neighbors: assign unassigned, move assigned, swap two assigned, unassign
            current_sim_rem = get_sim_remaining(current_assignment)

            # 1. Assign unassigned to eligible emp if fits
            for rid in req_ids:
                if current_assignment[rid] is not None:
                    continue
                for eid in req_dict[rid]['eligible']:
                    if eid in current_sim_rem and current_sim_rem[eid] >= req_dict[rid]['duration']:
                        new_assign = copy.deepcopy(current_assignment)
                        new_assign[rid] = eid
                        new_score = compute_score(new_assign)
                        neighbors.append((new_assign, new_score, ('assign', rid, eid)))

            # 2. Move assigned to new emp if fits (including check for tabu later)
            for rid in req_ids:
                if current_assignment[rid] is None:
                    continue
                old_eid = current_assignment[rid]
                for new_eid in req_dict[rid]['eligible']:
                    if new_eid == old_eid:
                        continue
                    if new_eid in current_sim_rem and current_sim_rem[new_eid] >= req_dict[rid]['duration']:
                        new_assign = copy.deepcopy(current_assignment)
                        new_assign[rid] = new_eid
                        new_score = compute_score(new_assign)
                        neighbors.append((new_assign, new_score, ('move', rid, old_eid, new_eid)))

            # 3. Swap two assigned requests if both eligible and fit
            assigned_reqs = [rid for rid in req_ids if current_assignment[rid] is not None]
            for i in range(len(assigned_reqs)):
                rid1 = assigned_reqs[i]
                eid1 = current_assignment[rid1]
                for j in range(i + 1, len(assigned_reqs)):
                    rid2 = assigned_reqs[j]
                    eid2 = current_assignment[rid2]
                    if eid1 == eid2:
                        continue
                    # Check if cross-eligible
                    if eid2 in req_dict[rid1]['eligible'] and eid1 in req_dict[rid2]['eligible']:
                        # Check fit after swap
                        rem1_after = current_sim_rem[eid1] + req_dict[rid1]['duration'] - req_dict[rid2]['duration']
                        rem2_after = current_sim_rem[eid2] + req_dict[rid2]['duration'] - req_dict[rid1]['duration']
                        if rem1_after >= 0 and rem2_after >= 0:
                            new_assign = copy.deepcopy(current_assignment)
                            new_assign[rid1] = eid2
                            new_assign[rid2] = eid1
                            new_score = compute_score(new_assign)
                            neighbors.append((new_assign, new_score, ('swap', rid1, rid2, eid1, eid2)))

            # 4. Unassign assigned
            for rid in req_ids:
                if current_assignment[rid] is None:
                    continue
                new_assign = copy.deepcopy(current_assignment)
                new_assign[rid] = None
                new_score = compute_score(new_assign)
                neighbors.append((new_assign, new_score, ('unassign', rid)))

            if not neighbors:
                steps.append("No neighbors found, stopping")
                break

            # Select best neighbor
            neighbors.sort(key=lambda x: x[1], reverse=True)
            selected_neighbor = None
            selected_move = None
            for neigh_assign, neigh_score, move in neighbors:
                # Check if tabu
                is_tabu = False
                if move[0] in ('assign', 'move', 'unassign'):
                    if move[1] in tabu:
                        is_tabu = True
                elif move[0] == 'swap':
                    if move[1] in tabu or move[2] in tabu:
                        is_tabu = True
                # Aspiration: if better than best, ignore tabu
                if is_tabu and neigh_score <= best_score:
                    continue
                selected_neighbor = neigh_assign
                selected_move = move
                break

            if selected_neighbor is None:
                steps.append("No valid non-tabu neighbor, stopping")
                break

            # Update current
            current_assignment = selected_neighbor
            current_score = neigh_score
            steps.append(f"Selected move: {selected_move} New score: {current_score}")

            # Update tabu: add moved requests
            if selected_move[0] in ('assign', 'move', 'unassign'):
                tabu.append(selected_move[1])
            elif selected_move[0] == 'swap':
                tabu.append(selected_move[1])
                tabu.append(selected_move[2])

            # Update best
            if current_score > best_score:
                best_assignment = copy.deepcopy(current_assignment)
                best_score = current_score
                stagnation_counter = 0
                steps.append(f"New best score: {best_score}")
            else:
                stagnation_counter += 1

            if stagnation_counter >= stagnation_limit:
                steps.append(f"Stagnation limit reached ({stagnation_limit})")
                break

        steps.append(f"Tabu Search completed. Final best score: {best_score}")

        # Create log
        self.env['getmo.algorithm.log'].create({
            'steps': "\n".join(steps),
            'mermaid_flow': MERMAID_TABU,
        })

        return best_assignment

    # Optimized metric calculations
    def _compute_feasibility_rate(self, employees, workloads, capacities):
        valid_count = 0
        for emp in employees:
            if workloads.get(emp.id, 0) <= capacities.get(emp.id, 0):
                valid_count += 1
        return (valid_count / len(employees)) * 100 if employees else 100.0
