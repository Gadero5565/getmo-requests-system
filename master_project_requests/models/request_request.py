from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import base64
import logging
_logger = logging.getLogger(__name__)


class Request(models.Model):
    _name = 'getmo.request.request'
    _description = 'Employees Requests'
    _inherit = ['mail.thread']
    _order = 'id desc'

    def _get_default_stage_id(self):
        return self.env["getmo.request.type.stage"].search([], limit=1).id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        stage_ids = self.env["getmo.request.type.stage"].search([])
        return stage_ids

    name = fields.Char('Name')
    request_text = fields.Html(translate=True, required=True,)
    type_id = fields.Many2one(
        'getmo.request.type', 'Type', ondelete='restrict',
        required=True, index=True, tracking=True,
        help="Type of request")
    genre_id = fields.Many2one(
        'getmo.request.genre', related='type_id.genre_id',
        store=True, index=True, readonly=True,
        help="Genre of request")
    category_id = fields.Many2one(
        'getmo.request.category', 'Category', index=True,
        required=True, ondelete="restrict", tracking=True,
        help="Category of request")
    stage_id = fields.Many2one(
        comodel_name="getmo.request.type.stage",
        string="Stage",
        group_expand="_read_group_stage_ids",
        default=_get_default_stage_id,
        tracking=True,
        ondelete="restrict",
        index=True,
        copy=False,
    )
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Very High')], string="Priority")
    employee_id = fields.Many2one(
        'hr.employee', 'Employee',
        default=lambda self: self.env.user.employee_id,
        readonly=True,
        states={'new': [('readonly', False)]}
    )
    assigned_to_id = fields.Many2one(
        'hr.employee', 'Assigned To',
        tracking=True,
    )
    estimated_duration = fields.Float(
        string='Estimated Duration (hours)',
        readonly=True,
        states={'new': [('readonly', False)]}
    )
    date_request = fields.Datetime(
        'Request Date',
        default=fields.Datetime.now,
        readonly=True
    )
    date_assigned = fields.Datetime('Assigned Date', readonly=True)
    date_closed = fields.Datetime('Closed Date', readonly=True)
    result_text = fields.Html(
        'Result',
    )
    user_can_edit_fields = fields.Boolean(
        string="User Can Edit Fields",
        compute="_compute_user_can_edit_fields",
        store=False,
    )
    result_type = fields.Selection(related="type_id.result_type", store=True)
    requests_result_attachments = fields.Many2many('ir.attachment', 'request_result_attachment_rel', string='Result Attachments')
    can_manager_assign = fields.Boolean("Can Manager Assign? ", compute="_compute_can_manager_assign")
    description = fields.Text(related="type_id.description")
    help_html = fields.Html(related="type_id.help_html")

    # Attachments
    attachment_setting_state = fields.Selection(related="type_id.attachment_setting_state", store=True)
    requests_attachments = fields.Many2many('ir.attachment', 'request_attachment_rel', string='Request Attachments')
    single_attachment_file = fields.Binary('Attachment')
    file_name = fields.Char(string="File Name")

    # Stages
    is_stage_done = fields.Boolean(compute='_compute_is_stage_done', store=True)
    stage_name = fields.Char(compute='_compute_stage_name', store=True)

    # Report
    report_needed = fields.Boolean(related="type_id.report_needed", store=True)
    report_attachment_file = fields.Binary(string="Report Attachment File", attachment=True, store=True, readonly=True)
    report_template = fields.Html('Report Template', compute='_compute_report_template', store=True, readonly=False)

    # Filters
    specialist_technician_filter = fields.Char(compute='_compute_specialist_technician_filter',
                                               search='_search_specialist_technician_filter')

    # Override Methods
    def write(self, vals):
        # Prevent manual changes to the name if it follows the sequence pattern
        if 'name' in vals and self.type_id.sequence_id:
            current_prefix = self.type_id.sequence_id.prefix
            if self.name.startswith(current_prefix):
                del vals['name']
        # Stage transition validation
        if 'stage_id' in vals:
            new_stage = self.env['getmo.request.type.stage'].browse(vals['stage_id'])
            # Check if moving to in_progress without assigned_to
            if new_stage.stage_type in ['assigned', 'in_progress', 'done']:
                for record in self:
                    if not record.assigned_to_id:
                        raise UserError(_('Cannot move to %s stage without assigning an owner!', new_stage.stage_type))
        return super(Request, self).write(vals)

    def _get_open_request_count(self, employee_id):
        closed_stages = self.env['getmo.request.type.stage'].search([
            ('stage_type', 'in', ['done', 'refused'])
        ])
        return self.env['getmo.request.request'].search_count([
            ('assigned_to_id', '=', employee_id),
            ('stage_id', 'not in', closed_stages.ids)
        ])

    @api.model
    def create(self, vals):
        # Set estimated duration from type
        if 'type_id' in vals:
            request_type = self.env['getmo.request.type'].browse(vals['type_id'])
            vals['estimated_duration'] = request_type.estimated_duration
            _logger.debug("Request Type '%s' selected with estimated duration: %.2f hours",
                          request_type.name, request_type.estimated_duration)
            if request_type.sequence_id:
                vals['name'] = request_type.sequence_id.next_by_id()

        # Prepare log values early so we can capture all data
        log_vals = {
            'request_type_id': vals.get('type_id'),
            'estimated_duration': vals.get('estimated_duration', 0),
            'log_date': fields.Datetime.now(),
        }

        # Knapsack-based assignment
        if not vals.get('assigned_to_id') and 'type_id' in vals:
            request_type = self.env['getmo.request.type'].browse(vals['type_id'])
            employees = request_type.responsible_employees_ids

            if employees:
                _logger.debug("Available employees for assignment (%d): %s",
                              len(employees),
                              ", ".join(emp.name for emp in employees))

                # Get current workload for all employees
                workloads = {
                    emp.id: emp.current_workload
                    for emp in employees
                }
                employees_workloads = {
                    emp.name: emp.current_workload
                    for emp in employees

                }
                log_vals.update({
                    'available_employee_ids': [(6, 0, employees.ids)],
                    'employee_workloads': employees_workloads,
                })

                # Initialize decision tree
                decision_tree = ["START", "│"]
                decision_tree.append(
                    f"├── Request Type: {request_type.name} ({request_type.estimated_duration:.2f} hours)")
                decision_tree.append("│")

                # List available employees
                decision_tree.append(f"├── Available Employees ({len(employees)}):")
                for emp in employees:
                    decision_tree.append(f"│   - {emp.name}")
                decision_tree.append("│")

                # Show workloads
                decision_tree.append("├── Current Workloads:")
                for emp in employees:
                    workload = workloads.get(emp.id, 0)
                    remaining = emp.daily_capacity - workload
                    decision_tree.append(
                        f"│   - {emp.name}: {workload:.2f}/{emp.daily_capacity}h "
                        f"(Remaining: {remaining:.2f}h)"
                    )
                decision_tree.append("│")

                # Evaluation criteria
                decision_tree.append("├── Evaluation Criteria:")
                decision_tree.append(
                    f"│   - Can handle request (remaining capacity ≥ {request_type.estimated_duration:.2f}h)?"
                )
                decision_tree.append("│   - Among capable employees, select one with MAX remaining capacity")
                decision_tree.append("│")
                decision_tree.append("├── Employee Evaluation:")

                # Knapsack assignment logic
                best_employee = None
                best_remaining_capacity = float('-inf')
                tie_candidates = []
                decision_steps = []

                for emp in employees:
                    remaining_capacity = emp.daily_capacity - workloads.get(emp.id, 0)
                    step_data = {
                        'employee_id': emp.id,
                        'employee_name': emp.name,
                        'current_workload': workloads.get(emp.id, 0),
                        'daily_capacity': emp.daily_capacity,
                        'remaining_capacity': remaining_capacity,
                        'can_handle': remaining_capacity >= request_type.estimated_duration,
                        'is_selected': False,
                        'reason': ''
                    }

                    status = f"{emp.name}: {remaining_capacity:.2f}h remaining → "

                    if remaining_capacity >= request_type.estimated_duration:
                        status += "Capable"
                        step_data['can_handle'] = True

                        if remaining_capacity > best_remaining_capacity:
                            best_remaining_capacity = remaining_capacity
                            best_employee = emp
                            status += " → New best candidate"
                            step_data.update({
                                'is_selected': True,
                                'reason': 'Highest remaining capacity'
                            })
                            tie_candidates = [emp]
                        elif remaining_capacity == best_remaining_capacity:
                            tie_candidates.append(emp)
                            status += " → Tied with current best"
                            step_data['reason'] = 'Tied with current best'
                        else:
                            status += " → Not selected (lower than best)"
                            step_data['reason'] = 'Available but not optimal'
                    else:
                        status += "Incapable"
                        step_data['reason'] = 'Insufficient capacity'

                    decision_tree.append(f"│   - {status}")
                    decision_steps.append(step_data)

                # Decision explanation
                decision_tree.append("│")
                decision_tree.append("├── Decision:")
                if best_employee:
                    if len(tie_candidates) > 1:
                        decision_tree.append(
                            f"│   - Multiple employees with same max capacity ({best_remaining_capacity:.2f}h)"
                        )
                        decision_tree.append(
                            f"│   - Algorithm selects first encountered: {best_employee.name}"
                        )
                        log_vals['assignment_reason'] = (
                            f"Selected {best_employee.name} (first of {len(tie_candidates)} candidates "
                            f"with {best_remaining_capacity:.2f}h remaining capacity)"
                        )
                    else:
                        decision_tree.append(
                            f"│   - Single best candidate: {best_employee.name} "
                            f"({best_remaining_capacity:.2f}h)"
                        )
                        log_vals['assignment_reason'] = (
                            f"Selected {best_employee.name} with highest remaining capacity "
                            f"({best_remaining_capacity:.2f}h)"
                        )
                else:
                    min_required = min(
                        emp.daily_capacity - workloads[emp.id]
                        for emp in employees
                    )
                    decision_tree.append(
                        f"│   - No employee can handle the request "
                        f"(requires {request_type.estimated_duration:.2f}h, "
                        f"max available: {min_required:.2f}h)"
                    )
                    no_assignment_reason = (
                        f"No suitable employee found. Request requires "
                        f"{request_type.estimated_duration:.2f}h, maximum available: "
                        f"{min_required:.2f}h"
                    )
                    log_vals['no_assignment_reason'] = no_assignment_reason

                # Final result
                decision_tree.append("│")
                if best_employee:
                    decision_tree.append(
                        f"└── RESULT: Assigned to {best_employee.name}"
                    )
                    vals['assigned_to_id'] = best_employee.id
                    vals['date_assigned'] = fields.Datetime.now()
                    log_vals.update({
                        'selected_employee_id': best_employee.id,
                    })
                    _logger.info(
                        "Assigned to %s (Remaining Capacity: %.2fh | "
                        "Workload: %.2f/%.2fh)",
                        best_employee.name,
                        best_remaining_capacity,
                        workloads[best_employee.id],
                        best_employee.daily_capacity
                    )
                else:
                    decision_tree.append("└── RESULT: Not assigned")
                    if 'category_id' in vals:
                        request_category = self.env['getmo.request.category'].browse(vals['category_id'])
                        user_to_notify = request_category.category_manager_id.user_id.partner_id
                    else:
                        user_to_notify = self.env.user.partner_id

                    base_msg = f"No suitable employee found!"
                    title = f"Request {vals.get('name', 'New')} Have not been Assigned!"
                    bus_message = {
                        "type": 'info',
                        "message": base_msg,
                        "title": title,
                        "sticky": True,
                    }
                    self._notify_function_logic(bus_message, user_to_notify)
                    _logger.warning(
                        "No suitable employee found! Request duration %.2fh exceeds "
                        "all available capacities (Min required: %.2fh)",
                        request_type.estimated_duration,
                        min_required
                    )

                # Add decision tree to log
                log_vals['knapsack_decision_tree'] = "\n".join(decision_tree)
                log_vals['decision_steps'] = decision_steps

        # Create the request first to get the ID
        request = super(Request, self).create(vals)

        # Add the request ID to log values and create the log
        if 'type_id' in vals:  # Only log if we processed the knapsack logic
            log_vals['request_id'] = request.id
            self.env['knapsack.assignment.log'].create(log_vals)

        return request

    # Methods can be used for intelligent scheduling
    # 1- First-Come, First-Served (FCFS)
    # def create(self, vals):
    #     # ... existing sequence logic ...
    #     if not vals.get('assigned_to_id') and 'type_id' in vals:
    #         request_type = self.env['request.type'].browse(vals['type_id'])
    #         employees = request_type.responsible_employees_ids
    #         if employees:
    #             # Get employee who was assigned their last task longest ago
    #             oldest_assignment = self.env['request.request'].search(
    #                 [('assigned_to_id', 'in', employees.ids)],
    #                 order='date_assigned asc',
    #                 limit=1
    #             )
    #             vals['assigned_to_id'] = oldest_assignment.assigned_to_id.id
    #     # ... rest of create ...
    # 2- Shortest Job First (SJF)
    # First add avg_duration to hr.employee
    #     class HrEmployee(models.Model):
    #         _inherit = 'hr.employee'
    #
    #         avg_request_duration = fields.Float(
    #             'Avg. Duration (hours)',
    #             compute='_compute_avg_duration'
    #         )
    #
    #         def _compute_avg_duration(self):
    #             for emp in self:
    #                 requests = self.env['request.request'].search([
    #                     ('assigned_to_id', '=', emp.id),
    #                     ('date_closed', '!=', False)
    #                 ])
    #                 total_hours = 0
    #                 for r in requests:
    #                     total_hours += (r.date_closed - r.date_assigned).total_seconds() / 3600
    #                 emp.avg_request_duration = total_hours / len(requests) if requests else 0
    #
    #     # Then in request creation:
    #     vals['assigned_to_id'] = min(
    #         employees,
    #         key=lambda e: e.avg_request_duration
    #     ).id

    #  Custom Methods
    # Used This For Knowing when stage is dene
    @api.depends('stage_id.stage_type')
    def _compute_is_stage_done(self):
        for request in self:
            if request.stage_id.stage_type == 'done':
                request.is_stage_done = True
            request.is_stage_done = False

    # Used This For Showing / Hiding Fields Depending on stage
    @api.depends('stage_id.stage_type')
    def _compute_stage_name(self):
        for request in self:
            request.stage_name = request.stage_id.stage_type

    # Used This For User not editing fields result
    def _compute_user_can_edit_fields(self):
        for rec in self:
            rec.user_can_edit_fields = self.env.user.has_group(
                'master_project_requests.group_request_manager') or self.env.user.has_group(
                'master_project_requests.group_request_service_admin') or self.env.user.has_group(
                'master_project_requests.group_request_technician_specialist')

    # Used This For Assign Method
    @api.depends('category_id', 'category_id.category_manager_id')
    def _compute_can_manager_assign(self):
        for rec in self:
            current_user_id = self.env.user.id
            current_employee = self.env['hr.employee'].search([('user_id', '=', current_user_id)])
            if rec.category_id and rec.category_id.category_manager_id == current_employee:
                rec.can_manager_assign = True
            else:
                rec.can_manager_assign = False

    # Used This For Domain in Assigned Employee
    @api.onchange('type_id')
    def _onchange_type_id(self):
        for rec in self:
            if rec.type_id:
                return {'domain': {'assigned_to_id': [('id', 'in', rec.type_id.responsible_employees_ids.ids)]}}
            else:
                return {'domain': {'assigned_to_id': []}}

    # Buttons And Logic
    def action_to_do_progress(self):
        self.ensure_one()
        assigned_stage = self.env['getmo.request.type.stage'].search([('stage_type', '=', 'assigned')], limit=1)
        if assigned_stage:
            self.stage_id = assigned_stage

    def action_start_progress(self):
        self.ensure_one()
        if not self.assigned_to_id:
            raise UserError("You must assign the request to a service manager first.")
        in_progress_stage = self.env['getmo.request.type.stage'].search([('stage_type', '=', 'in_progress')], limit=1)
        if in_progress_stage:
            self.stage_id = in_progress_stage
            self.date_assigned = fields.Datetime.now()

    def action_done(self):
        self.ensure_one()
        if not self.result_text:
            raise UserError("You must provide a result before marking the request as done.")
        done_stage = self.env['getmo.request.type.stage'].search([('stage_type', '=', 'done')], limit=1)
        if done_stage:
            self.stage_id = done_stage
            self.date_closed = fields.Datetime.now()

    def action_refuse(self):
        self.ensure_one()
        canceled_stage = self.env['getmo.request.type.stage'].search([('stage_type', '=', 'refused')], limit=1)
        if canceled_stage:
            self.stage_id = canceled_stage

    def action_notify_manager_check(self):
        self.ensure_one()

        if self.category_id:
            user_to_notify = self.category_id.category_manager_id.user_id.partner_id
        else:
            user_to_notify = self.assigned_to_id.parent_id.user_id.partner_id

        base_msg = f"Request with sequence {self.name} has been processed and waiting for approval!."
        title = f"Request Have been Processed!"
        bus_message = {
            "type": 'info',
            "message": base_msg,
            "title": title,
            "sticky": True,
        }
        self._notify_function_logic(bus_message, user_to_notify)

    def _notify_function_logic(self, bus_message, user_to_notify):
        notifications = [[partner, "web.notify", [bus_message]] for partner in user_to_notify]
        self.env["bus.bus"]._sendmany(notifications)

    # Filter Methods
    def _compute_specialist_technician_filter(self):
        for rec in self:
            rec.specialist_technician_filter = "Requests Specialist Technician Filter"

    def _search_specialist_technician_filter(self, operator, value):
        current_user = self.env.user
        current_employee = self.env['hr.employee'].search([('user_id', '=', current_user.id),], limit=1)
        if current_user.has_group('master_project_requests.group_request_technician_specialist'):
            requests_types = self.env['getmo.request.type'].search([('responsible_employees_ids', 'in', current_employee.id)])
            requests = self.env['getmo.request.request'].search([('type_id', 'in', requests_types.ids)])
            return [('id', 'in', requests.ids)]
        else:
            return [('id', 'in', [])]

    # Report Logic
    @api.depends('date_request', 'type_id', 'genre_id', 'category_id', 'name', 'request_text', 'employee_id')
    def _compute_report_template(self):
        for request in self:
            # Humanize the employee name
            employee_name = request.employee_id.name if request.employee_id else "Unknown"

            # Create the HTML template
            template = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px;">Request Report</h2>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <tr>
                        <td style="width: 30%; padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">Request Date:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{request.date_request or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">Request Type:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{request.type_id.name or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">Request Genre:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{request.genre_id.name or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">Request Category:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{request.category_id.name or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">Request Name:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{request.name or 'N/A'}</td>
                    </tr>
                </table>

                <div style="margin-top: 20px;">
                    <h3 style="color: #2c3e50;">Request from {employee_name}:</h3>
                    <div style="background: #f9f9f9; padding: 15px; border-radius: 4px; border-left: 4px solid #3498db;">
                        {request.request_text or 'No request text provided'}
                    </div>
                </div>
            </div>
            """
            request.report_template = template

    def get_request_as_pdf(self):
        self.ensure_one()
        self._compute_report_template()
        pdf = self.env['ir.actions.report']._render_qweb_pdf("master_project_requests.employee_request_report", self.id)

        b64_pdf = base64.b64encode(pdf[0])

        # save pdf as attachment
        sql_statement = "SELECT id FROM ir_attachment WHERE res_model = 'getmo.request.request' and res_field = 'report_attachment_file' and res_id = {} order by create_date desc FETCH FIRST ROW ONLY;".format(
            self.id)
        self._cr.execute(sql_statement)
        pdf_id = self._cr.fetchall()
        if pdf_id:
            sql_statement = "DELETE FROM ir_attachment WHERE id = {};".format(pdf_id[0][0])
            self._cr.execute(sql_statement)

        return self.env['ir.attachment'].sudo().create({
            'name': self.type_id.name,
            'type': 'binary',
            'datas': b64_pdf,
            'res_model': 'getmo.request.request',
            'res_field': 'report_attachment_file',
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
