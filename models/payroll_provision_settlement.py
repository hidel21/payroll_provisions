import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PayrollProvisionSettlement(models.Model):
    """Traslado de lo provisionado a la cuenta por pagar, en el corte.

    El acumulado se lee de la **contabilidad**, no de la nómina. Es a propósito:
    en esta base hay apuntes en esas cuentas desde 2022 y por vías distintas del
    diario de nómina, así que calcularlo desde los recibos daría de menos.
    """

    _name = "payroll.provision.settlement"
    _description = "Liquidación de prestaciones sociales"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_cut desc, id desc"

    name = fields.Char(
        string="Referencia", required=True, copy=False, readonly=True, default="/"
    )
    type_id = fields.Many2one(
        comodel_name="payroll.provision.type",
        string="Prestación",
        required=True,
        readonly=False,
        states={"posted": [("readonly", True)], "cancel": [("readonly", True)]},
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    date_cut = fields.Date(
        string="Fecha de corte",
        required=True,
        tracking=True,
        default=fields.Date.context_today,
        help="Se toma el acumulado de cada empleado hasta esta fecha, incluida.",
    )
    date = fields.Date(
        string="Fecha del asiento",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("posted", "Contabilizada"),
            ("cancel", "Cancelada"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        comodel_name="payroll.provision.settlement.line",
        inverse_name="settlement_id",
        string="Empleados",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento",
        readonly=True,
        copy=False,
    )
    cutoff_warning = fields.Char(compute="_compute_cutoff_warning")

    total_provisioned = fields.Monetary(
        compute="_compute_totals", store=True, string="Total provisionado"
    )
    total_to_pay = fields.Monetary(
        compute="_compute_totals", store=True, string="Total a pagar"
    )
    total_difference = fields.Monetary(
        compute="_compute_totals", store=True, string="Diferencia a gasto"
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "payroll.provision.settlement"
                ) or "/"
        return super().create(vals_list)

    @api.depends("line_ids.amount_provisioned", "line_ids.amount_to_pay")
    def _compute_totals(self):
        for liq in self:
            liq.total_provisioned = sum(liq.line_ids.mapped("amount_provisioned"))
            liq.total_to_pay = sum(liq.line_ids.mapped("amount_to_pay"))
            liq.total_difference = liq.total_provisioned - liq.total_to_pay

    @api.depends("type_id", "date_cut")
    def _compute_cutoff_warning(self):
        """Avisa si se liquida fuera del calendario, sin impedirlo.

        Un retiro a mitad de año obliga a liquidar en cualquier mes, así que
        esto informa y no bloquea.
        """
        for liq in self:
            meses = liq.type_id._cutoff_month_list() if liq.type_id else []
            if liq.date_cut and meses and liq.date_cut.month not in meses:
                liq.cutoff_warning = _(
                    "%(prestacion)s se liquida normalmente en el mes %(meses)s, "
                    "y esta fecha de corte cae en el %(mes)s.",
                    prestacion=liq.type_id.name,
                    meses=", ".join(str(m) for m in meses),
                    mes=liq.date_cut.month,
                )
            else:
                liq.cutoff_warning = False

    # ------------------------------------------------------------------
    # Cargar el acumulado
    # ------------------------------------------------------------------

    def action_load_lines(self):
        """Trae el saldo pendiente de cada empleado hasta la fecha de corte.

        Solo se miran apuntes **sin conciliar**: los ya conciliados pertenecen a
        una liquidación anterior y volver a tomarlos los pagaría dos veces.
        """
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Solo se pueden cargar empleados en una liquidación en borrador."))

        self.line_ids.unlink()
        apuntes = self._pending_move_lines()
        if not apuntes:
            raise UserError(
                _(
                    "No hay nada pendiente en la cuenta %(cuenta)s hasta el "
                    "%(fecha)s.\n\nO ya se liquidó, o las provisiones de este "
                    "periodo todavía no se han contabilizado.",
                    cuenta=self.type_id.provision_account_id.display_name,
                    fecha=self.date_cut,
                )
            )

        saldos = {}
        for apunte in apuntes:
            saldos.setdefault(apunte.partner_id, 0.0)
            saldos[apunte.partner_id] += apunte.credit - apunte.debit

        moneda = self.company_id.currency_id
        valores = []
        for partner, saldo in saldos.items():
            if moneda.is_zero(saldo) or saldo < 0:
                # Un saldo negativo o cero no es una prestación por pagar; suele
                # ser un ajuste suelto y se deja fuera para que alguien lo mire.
                continue
            valores.append(
                {
                    "settlement_id": self.id,
                    "partner_id": partner.id,
                    "amount_provisioned": saldo,
                    "amount_to_pay": saldo,
                }
            )

        if not valores:
            raise UserError(
                _("Hay apuntes pendientes, pero ninguno deja saldo a favor del empleado.")
            )

        self.env["payroll.provision.settlement.line"].create(valores)
        self.message_post(
            body=_("Cargados %s empleados con corte al %s.", len(valores), self.date_cut)
        )
        return True

    def _pending_move_lines(self, exclude_move=None):
        """Apuntes de la provisión que aún no se han liquidado.

        ``exclude_move`` deja fuera el asiento de esta misma liquidación. Hace
        falta al conciliar: el débito recién creado cumple todas las condiciones
        de «pendiente» —misma cuenta, mismo tercero, fecha dentro del corte— y
        sin excluirlo se intentaría cruzar consigo mismo.
        """
        self.ensure_one()
        dominio = [
            ("account_id", "=", self.type_id.provision_account_id.id),
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", "<=", self.date_cut),
            ("full_reconcile_id", "=", False),
            ("partner_id", "!=", False),
        ]
        if exclude_move:
            dominio.append(("move_id", "!=", exclude_move.id))
        return self.env["account.move.line"].sudo().search(dominio)

    # ------------------------------------------------------------------
    # Contabilizar
    # ------------------------------------------------------------------

    def action_post(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Esta liquidación ya no está en borrador."))
        if not self.line_ids:
            raise UserError(_("No hay empleados que liquidar."))

        move = self.env["account.move"].create(self._prepare_move())
        move.action_post()
        self.write({"move_id": move.id, "state": "posted"})
        self._reconcile_provision()

        self.message_post(
            body=_(
                "Contabilizada en %(asiento)s: %(n)s empleados, "
                "%(prov)s trasladados y %(dif)s de diferencia a gasto.",
                asiento=move.name,
                n=len(self.line_ids),
                prov=self.total_provisioned,
                dif=self.total_difference,
            )
        )
        return True

    def _prepare_move(self):
        """Un asiento con tres líneas por empleado, cuadradas entre sí.

        Se reparte por empleado y no en tres líneas globales para que cada
        persona quede cuadrada por sí sola: es lo que permite conciliar después
        su provisión sin arrastrar los importes de los demás.
        """
        self.ensure_one()
        tipo = self.type_id
        moneda = self.company_id.currency_id
        commands = []

        for linea in self.line_ids:
            etiqueta = "%s — %s" % (tipo.name, linea.partner_id.display_name)
            commands.append(
                fields.Command.create(
                    {
                        "name": etiqueta,
                        "account_id": tipo.provision_account_id.id,
                        "partner_id": linea.partner_id.id,
                        "debit": linea.amount_provisioned,
                        "credit": 0.0,
                    }
                )
            )
            commands.append(
                fields.Command.create(
                    {
                        "name": etiqueta,
                        "account_id": tipo.payable_account_id.id,
                        "partner_id": linea.partner_id.id,
                        "debit": 0.0,
                        "credit": linea.amount_to_pay,
                    }
                )
            )
            diferencia = linea.amount_provisioned - linea.amount_to_pay
            if not moneda.is_zero(diferencia):
                commands.append(
                    fields.Command.create(
                        {
                            "name": _("Diferencia %s", etiqueta),
                            "account_id": tipo.expense_account_id.id,
                            "partner_id": linea.partner_id.id,
                            "debit": -diferencia if diferencia < 0 else 0.0,
                            "credit": diferencia if diferencia > 0 else 0.0,
                        }
                    )
                )

        return {
            "move_type": "entry",
            "journal_id": tipo.journal_id.id,
            "company_id": self.company_id.id,
            "date": self.date,
            "ref": _("%s — corte %s", tipo.name, self.date_cut),
            "line_ids": commands,
        }

    def _reconcile_protected_partners(self):
        return self.env["res.partner"].browse()

    def _reconcile_provision(self):
        """Cruza el débito nuevo contra las provisiones que lo originaron.

        Sin esto el saldo quedaría en cero por suma pero cada apunte seguiría
        abierto, y en dos cortes nadie sabría qué queda pendiente de quién.
        """
        self.ensure_one()
        cuenta = self.type_id.provision_account_id
        if not cuenta.reconcile:
            self.message_post(
                body=_(
                    "La cuenta %s no permite conciliación, así que el traslado "
                    "quedó contabilizado pero sin cruzar.",
                    cuenta.display_name,
                )
            )
            return

        pendientes = self._pending_move_lines(exclude_move=self.move_id)
        conciliadas = 0
        for linea in self.line_ids:
            # Se descarta lo ya conciliado en cada vuelta y no solo al principio:
            # el conjunto se lee una vez, pero conciliar a un empleado puede
            # cerrar apuntes que la lista todavía daba por abiertos, y pasarle a
            # Odoo un apunte ya cruzado aborta la conciliación entera.
            nuevas = self.move_id.line_ids.filtered(
                lambda l, p=linea.partner_id, c=cuenta: l.account_id == c
                and l.partner_id == p
                and not l.reconciled
            )
            viejas = pendientes.filtered(
                lambda l, p=linea.partner_id: l.partner_id == p and not l.reconciled
            )
            if not nuevas or not viejas:
                continue
            try:
                with self.env.cr.savepoint():
                    (nuevas | viejas).reconcile()
                    conciliadas += 1
            except Exception as error:  # noqa: BLE001
                # Un empleado que no concilie no debe tumbar a los demás: el
                # asiento ya está bien y el cruce se puede rehacer a mano.
                _logger.warning(
                    "payroll_provisions: no se pudo conciliar %s en %s: %s",
                    linea.partner_id.display_name,
                    self.name,
                    error,
                )
                linea.reconcile_error = str(error)[:200]

        _logger.info(
            "payroll_provisions: %s — %s de %s empleados conciliados.",
            self.name,
            conciliadas,
            len(self.line_ids),
        )

    def action_cancel(self):
        self.ensure_one()
        if self.move_id and self.move_id.state == "posted":
            raise UserError(
                _(
                    "El asiento %s ya está contabilizado. Anúlelo o revérselo "
                    "desde contabilidad antes de cancelar la liquidación, para "
                    "que quede rastro de por qué.",
                    self.move_id.name,
                )
            )
        self.state = "cancel"
        return True

    def action_draft(self):
        self.ensure_one()
        if self.move_id:
            raise UserError(
                _("No se puede volver a borrador: ya tiene el asiento %s.", self.move_id.name)
            )
        self.state = "draft"
        return True

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }


class PayrollProvisionSettlementLine(models.Model):
    _name = "payroll.provision.settlement.line"
    _description = "Empleado en una liquidación de prestaciones"
    _order = "partner_id"

    settlement_id = fields.Many2one(
        comodel_name="payroll.provision.settlement",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Tercero",
        required=True,
        help="La contabilidad lleva el tercero, no el empleado. Si dos fichas de "
        "empleado comparten contacto, el saldo es de ese contacto.",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Empleado",
        compute="_compute_employee_id",
        store=True,
    )
    amount_provisioned = fields.Monetary(
        string="Provisionado", required=True, readonly=True
    )
    amount_to_pay = fields.Monetary(string="A pagar", required=True)
    difference = fields.Monetary(compute="_compute_difference", store=True)
    reconcile_error = fields.Char(readonly=True)
    currency_id = fields.Many2one(
        related="settlement_id.currency_id", readonly=True
    )
    company_id = fields.Many2one(
        related="settlement_id.company_id", store=True, readonly=True
    )

    @api.depends("partner_id")
    def _compute_employee_id(self):
        Empleado = self.env["hr.employee"].sudo()
        for linea in self:
            linea.employee_id = Empleado.search(
                [("work_contact_id", "=", linea.partner_id.id)], limit=1
            )

    @api.depends("amount_provisioned", "amount_to_pay")
    def _compute_difference(self):
        for linea in self:
            linea.difference = linea.amount_provisioned - linea.amount_to_pay
