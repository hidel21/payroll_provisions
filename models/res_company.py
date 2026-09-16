from odoo import fields, models


class ResCompany(models.Model):
    """Quién responde en contabilidad de las prestaciones de esta compañía.

    Liquidar pasó a ser un acto de nómina, y está bien que lo sea: la prestación
    nace ahí. Pero el asiento que genera mueve saldos de pasivo y concilia
    apuntes, y de eso responde contabilidad. Sin este campo, quien liquida y
    quien responde del resultado no se enteran el uno del otro hasta el cierre.

    No es un permiso ni un visto bueno: es a quién se avisa. Se deja
    configurable y por compañía porque no tiene por qué ser la misma persona en
    todas.
    """

    _inherit = "res.company"

    provision_manager_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable contable de prestaciones",
        help="Se le avisa cada vez que se contabiliza una liquidación de "
        "prestaciones de esta compañía, con el detalle de lo trasladado.\n\n"
        "Déjelo vacío si no quiere que se avise a nadie.",
    )
