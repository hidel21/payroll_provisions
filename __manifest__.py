{
    "name": "Payroll Provisions - Intelli Next",
    "summary": "Liquidación de prestaciones sociales: traslado de la provisión a por pagar",
    "description": """
Liquidación de prestaciones sociales
====================================

Cuando llega el corte de una prestación —prima en junio y diciembre, cesantías
e intereses a fin de año, vacaciones al cierre— hay que sacar lo provisionado de
la cuenta de provisión y pasarlo a la de por pagar, empleado por empleado.

Hasta ahora eso se hacía a mano: descargar el libro mayor, filtrar cada persona,
sumar su acumulado y escribir el asiento. Con diez personas ya costaba una
mañana.

Qué hace
--------

* Propone el acumulado de cada empleado hasta la fecha de corte, leyéndolo de la
  contabilidad y no de la nómina.
* Deja corregir el importe a pagar cuando no coincide con lo provisionado, y
  manda la diferencia a la cuenta de gasto.
* Genera **un solo asiento** con el traslado de todos los empleados.
* Concilia los apuntes de la provisión, de modo que el saldo de cada persona
  quede realmente en cero y no en un cero aparente.

Por qué un módulo aparte
------------------------

No toca el circuito de la nómina. Es deliberado: confirmar un recibo ya
contabilizado vuelve a crear su asiento sin comprobar si ya existía, así que
cualquier automatización que pase por ahí duplica la contabilidad del mes.
Este módulo genera su propio asiento y no reabre nada.
""",
    "author": "Hidelberg Martinez",
    "website": "https://intelli-next.com",
    "category": "Human Resources/Payroll",
    "version": "18.0.1.1.0",
    "license": "LGPL-3",
    "depends": ["account", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/payroll_provision_type_views.xml",
        "views/payroll_provision_settlement_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
