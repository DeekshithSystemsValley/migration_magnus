# -*- coding: utf-8 -*-
# © 2016-17 Eficent Business and IT Consulting Services S.L.
# © 2016 Serpent Consulting Services Pvt. Ltd.
# © 2018 Magnus Group B.V.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo.tools.translate import _
from odoo import api, fields, models
from odoo.exceptions import UserError
from datetime import datetime, timedelta

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    user_id = fields.Many2one(
        'res.users',
        string='Timesheet Users'
    )
    wip_percentage=fields.Float("WIP percentage")


    @api.multi
    @api.constrains('operating_unit_id', 'analytic_account_id','user_id')
    def _check_analytic_operating_unit(self):
        for rec in self.filtered('user_id'):
            if not rec.operating_unit_id == \
                                    rec.user_id._get_operating_unit_id():
                raise UserError(_('The Operating Unit in the'
                                  ' Move Line must be the '
                                  'Operating Unit in the department'
                                  ' of the user/employee'))
        super(AccountMoveLine, self - self.filtered('user_id'))._check_analytic_operating_unit()

    @api.onchange('analytic_account_id', 'user_id')
    @api.multi
    def onchange_operating_unit(self):
        super(AccountMoveLine, self).onchange_operating_unit()
        if self.user_id:
            self.operating_unit_id = \
                self.user_id._get_operating_unit_id()

class AccountMove(models.Model):
    _inherit = "account.move"

    # override post(), when first post, nothing extra. When move.name exists,
    # it cannot be first posting. Then 'OU-balancing' lines are unlinked.
    is_wip_move=fields.Boolean("Is WIP move")
    wip_percentage=fields.Integer("WIP percentage")
    @api.multi
    def post(self):
        for move in self:
            if not move.company_id.ou_is_self_balanced or not move.name:
                continue
            for line in move.line_ids:
                if line.name == 'OU-Balancing':
                    line.with_context(wip=True).unlink()
        res = super(AccountMove, self).post()
        return res

    @api.multi
    def wip_move_create(self, wip_journal, name, ar_account_id, ref=None):
        self.ensure_one()
        move_date = datetime.strptime(self.date, "%Y-%m-%d")
        last_day_month_before = (move_date - timedelta(days=move_date.day)).strftime("%Y-%m-%d")
        default = {
            'name': name,
            'ref':  ref if ref else 'WIP Invoicing Posting',
            'journal_id': wip_journal.id,
            'date': last_day_month_before,
            'narration': 'WIP Invoicing Posting',
            'to_be_reversed': True,
        }
        wip_move = self.copy(default)
        mls = wip_move.line_ids
        ## we filter all BS lines out of all move lines. And also all "null" lines because of reconcile problem
        # All filtered out lines are unlinked. All will be kept unchanged and copied with reversing debit/credit
        # and replace P/L account by wip-account.
        ids = []
        ids.append(self.env.ref('account.data_account_type_other_income').id)
        ids.append(self.env.ref('account.data_account_type_revenue').id)
        ids.append(self.env.ref('account.data_account_type_depreciation').id)
        ids.append(self.env.ref('account.data_account_type_expenses').id)
        ids.append(self.env.ref('account.data_account_type_direct_costs').id)
        # Balance Sheet lines
        bs_move_lines = mls.filtered(lambda r: r.account_id.user_type_id.id not in ids)
        # lines with both debit and credit equals 0
        null_lines = mls.filtered(lambda r: r.credit + r.debit == 0.0)
        # leaving only not-null Profit and Loss lines
        pl_move_lines = mls - bs_move_lines - null_lines
        bs_move_lines.unlink()
        null_lines.unlink()
        default = {
            'account_id': wip_journal.default_credit_account_id.id
        }
        for line in pl_move_lines:
            wip_line = line.copy(default)
            if line.credit != 0:
                wip_line.credit = line.debit
                wip_line.debit = line.credit
            else:
                wip_line.debit = line.credit
                wip_line.credit = line.debit
        return wip_move


