from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PayrollProvisionType(models.Model):
    """Una prestación social y las tres cuentas por las que se mueve.

    Existe para que las cuentas no vivan en el código. Son de la localización
    colombiana, cambian de plan contable a plan contable y de compañía a
    compañía, y ninguna de las tres es adivinable desde fuera.
    """

    _name = "payroll.provision.type"
    _description = "Tipo de prestación social"
    _order = "sequence, name"

    name = fields.Char(string="Prestación", required=True, translate=True)
    code = fields.Char(
        string="Código",
        required=True,
        help="Identificador corto, para reconocerlo en informes y secuencias.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    provision_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de provisión",
        required=True,
        domain="[('reconcile', '=', True), ('company_ids', 'in', company_id)]",
        help="Donde se acumula mes a mes lo provisionado. En el plan colombiano "
        "es una cuenta del grupo 26.\n\n"
        "Tiene que permitir conciliación: es lo que deja el saldo de cada "
        "empleado realmente en cero en lugar de en un cero de suma.",
    )
    payable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta por pagar",
        required=True,
        domain="[('company_ids', 'in', company_id)]",
        help="Adonde se traslada lo acumulado al llegar el corte, a la espera "
        "del pago. Grupo 25 en el plan colombiano.",
    )
    expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de gasto para diferencias",
        required=True,
        domain="[('company_ids', 'in', company_id)]",
        help="Adonde va la diferencia cuando lo que se paga no coincide con lo "
        "provisionado. Ocurre con los cambios de salario a mitad de periodo.",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )

    cutoff_months = fields.Char(
        string="Meses de corte",
        default="12",
        required=True,
        help="Meses en los que toca liquidar, separados por comas.\n\n"
        "La prima son dos cortes al año: «6, 12». Cesantías, intereses y "
        "vacaciones cierran a fin de año: «12».\n\n"
        "Solo sirve de aviso: si se liquida fuera de esos meses el sistema lo "
        "señala, pero no lo impide — un retiro a mitad de año hay que poder "
        "liquidarlo igual.",
    )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Ya existe una prestación con ese código en esta compañía.",
        ),
    ]

    @api.constrains("cutoff_months")
    def _check_cutoff_months(self):
        for tipo in self:
            for trozo in (tipo.cutoff_months or "").split(","):
                trozo = trozo.strip()
                if not trozo:
                    continue
                if not trozo.isdigit() or not 1 <= int(trozo) <= 12:
                    raise ValidationError(
                        _(
                            "«%s» no es un mes válido en «Meses de corte». "
                            "Se esperan números del 1 al 12 separados por comas.",
                            trozo,
                        )
                    )

    @api.constrains("provision_account_id", "payable_account_id")
    def _check_accounts_differ(self):
        for tipo in self:
            if tipo.provision_account_id == tipo.payable_account_id:
                raise ValidationError(
                    _(
                        "La cuenta de provisión y la de por pagar no pueden ser "
                        "la misma: el traslado no movería nada."
                    )
                )

    def _cutoff_month_list(self):
        self.ensure_one()
        return [
            int(x.strip())
            for x in (self.cutoff_months or "").split(",")
            if x.strip().isdigit()
        ]
