# Liquidación de prestaciones sociales

Al llegar el corte de una prestación hay que sacar lo provisionado de la cuenta
de provisión y pasarlo a la de por pagar, empleado por empleado. Este módulo lo
hace en una pantalla, y además concilia.

## Por qué

De las cuatro prestaciones colombianas, solo dos tenían mecanismo en el recibo
de nómina:

| Prestación | Provisiona | Traslada 26 → 25 |
|---|---|---|
| Prima | `PRIMSERV` | `PROVPRIMAAC` + `NETO_PRIMA` |
| Vacaciones | `VACACION` | `VACACIONESDISFRUTADAS_MANUAL`, usado una vez |
| Cesantías | `CESANTIA` | — |
| Intereses de cesantías | `INTECESA` | — |

Las cuatro provisionan cada mes. Cesantías e intereses no tenían forma de
trasladarse, y se liquidan al 31 de diciembre. Eso se hacía a mano: descargar el
libro mayor, filtrar cada persona, sumar su acumulado y escribir el asiento.

## Cómo se usa

`Contabilidad → Contabilidad → Prestaciones sociales`

1. **Configuración de prestaciones** — una vez, por prestación y compañía: la
   cuenta de provisión, la de por pagar, la de gasto para diferencias, el diario
   y los meses de corte.
2. **Liquidaciones** — se elige prestación y fecha de corte, se pulsa *Cargar
   empleados*, se revisan los importes y se contabiliza.

## Decisiones de diseño

**El acumulado se lee de la contabilidad, no de la nómina.** Hay apuntes en esas
cuentas desde enero de 2022, en 92 fechas y por vías ajenas al diario de nómina.
Calcularlo desde los recibos daría de menos.

**Solo se toman apuntes sin conciliar.** Los conciliados pertenecen a una
liquidación anterior; volver a tomarlos los pagaría dos veces.

**Tres líneas por empleado, no tres globales.** Así cada persona queda cuadrada
por sí sola, que es lo que permite cruzar su provisión sin arrastrar los
importes de los demás.

**Concilia al trasladar.** Sin eso el saldo quedaría en cero por suma pero cada
apunte seguiría abierto, y en dos cortes nadie sabría qué queda pendiente de
quién.

**No toca el circuito de la nómina.** `om_hr_payroll_account` crea el asiento
del recibo sin comprobar si ya existe, así que cualquier automatización que pase
por confirmar un recibo duplica la contabilidad del mes. Este módulo genera su
propio asiento y no reabre nada.

**Por tercero y no por empleado.** Así está la contabilidad, y hay contactos
compartidos por dos fichas de empleado. El empleado se muestra como dato
informativo.

## Dos avisos que no bloquean

**Fuera del calendario** — si la fecha de corte cae en un mes que no es de
liquidación. No se impide: un retiro a mitad de año hay que poder liquidarlo.

**Ya se traslada por la nómina** — si hay débitos en la cuenta de provisión o
recibos con una regla que la debita, aunque estén en borrador. Es el caso de la
prima en junio de 2026: diez recibos con el traslado calculado y sin
contabilizar.

## Qué no hace todavía

El cruce de la cuenta 25 contra el pago. Hoy sigue siendo manual, y son varias
formas de pago —banco, Binance— con ritmos distintos. La recomendación es
apoyarse en la conciliación bancaria de Odoo en lugar de reimplementarla, y
añadir un botón que registre el pago de varios empleados desde la propia
liquidación.

## Permisos

`Contabilidad / Administrador`. Mueve saldos entre cuentas de pasivo, así que se
acota a quien ya puede tocar asientos.
