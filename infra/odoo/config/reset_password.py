import odoo
from odoo.api import Environment
from odoo.tools.config import config

# Initialize Odoo
config.parse_config([
    '-c', '/etc/odoo/odoo.conf',
    '-d', 'estacion_h2o',
    '--no-http',
    '--stop-after-init'
])

# Registry is already initialized
registry = odoo.registry('estacion_h2o')
with registry.cursor() as cr:
    env = Environment(cr, odoo.SUPERUSER_ID, {})
    user = env['res.users'].browse(1)
    print(f"Current user: {user.login}")
    print(f"Current password hash: {user.password[:50]}...")
    user.write({'password': 'admin'})
    cr.commit()
    print("Password updated to 'admin'")
    # Verify
    updated = env['res.users'].browse(1)
    print(f"New password hash: {updated.password[:50]}...")