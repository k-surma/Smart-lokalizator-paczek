from odoo import models, fields


class SmartParcel(models.Model):
    _name = 'smart.parcel'
    _table = 'packages'
    _description = 'Paczka BLE'
    _rec_name = 'package_code'
    _order = 'id desc'

    package_code = fields.Char(string='Kod paczki', required=True)
    mac_address = fields.Char(string='Adres MAC (BLE)', required=True)
    status = fields.Selection([
        ('IDLE', 'W magazynie (IDLE)'),
        ('LOCATING', 'Szukanie (LOCATING)'),
        ('FOUND', 'Znaleziono (FOUND)'),
    ], string='Status', default='IDLE', required=True)
    battery_level = fields.Integer(string='Poziom baterii (%)', default=100)
    last_seen = fields.Datetime(
        string='Ostatnia aktywność',
        default=fields.Datetime.now,
    )

    _sql_constraints = [
        ('mac_unique', 'unique(mac_address)', 'Ten adres MAC jest już przypisany do innej paczki!'),
        ('code_unique', 'unique(package_code)', 'Paczka o tym kodzie już istnieje!'),
    ]