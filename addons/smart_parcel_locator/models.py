import os
import requests
from odoo import models, fields
from odoo.exceptions import UserError

FASTAPI_INTERNAL_URL = os.getenv("FASTAPI_URL", "http://locator_fastapi:8000")
FASTAPI_PUBLIC_URL = os.getenv("FASTAPI_PUBLIC_URL", "http://63.187.131.29:8000")


class SmartParcel(models.Model):
    _name = 'smart.parcel'
    _description = 'Paczka z lokalizatorem BLE (InPost PUDO)'
    _table = 'packages'
    _rec_name = 'package_code'

    package_code = fields.Char(string='Numer przesyłki InPost', required=True)
    mac_address = fields.Char(string='Adres MAC lokalizatora', required=False)
    direction = fields.Selection([
        ('INBOUND', 'Odbiór przez klienta'),
        ('OUTBOUND', 'Nadanie dla kuriera'),
    ], string='Typ procesu', default='INBOUND', required=True)
    status = fields.Selection([
        ('IDLE', 'W magazynie'),
        ('LOCATING', 'Szukanie BLE'),
        ('FOUND', 'Znaleziono'),
        ('DELIVERED', 'Wydano'),
    ], string='Status BLE / Magazyn', default='IDLE', required=True)

    inpost_pudo_status = fields.Selection([
        ('confirmed', 'Do nadania (InPost)'),
        ('dispatched_by_sender', 'Nadana w punkcie'),
        ('ready_to_pickup', 'Do odbioru w punkcie'),
        ('collected_from_sender', 'Odebrana przez kuriera'),
        ('delivered', 'Wydana klientowi'),
    ], string='Status logistyczny InPost PUDO', default='confirmed')
    inpost_api_status = fields.Char(string='Status surowy InPost API')
    inpost_shipment_id = fields.Integer(string='ID InPost Sandbox')
    parcel_size = fields.Char(string='Gabaryt')
    recipient_phone = fields.Char(string='Telefon odbiorcy')
    pickup_code = fields.Char(string='Kod odbioru (PIN)')
    battery_level = fields.Integer(string='Bateria (%)', default=100)
    last_seen = fields.Datetime(string='Ostatnia aktywność')

    _sql_constraints = [
        ('code_unique', 'unique(package_code)', 'Kod paczki musi być unikalny!'),
    ]

    def action_open_simulate_wizard(self):
        return {
            'name': 'Symuluj nadanie paczki (InPost -> Do odbioru)',
            'type': 'ir.actions.act_window',
            'res_model': 'smart.parcel.simulate.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_client_pass(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f"{FASTAPI_PUBLIC_URL}/api/inpost/client-pass/{self.package_code}",
            'target': 'new',
        }


class SmartParcelSimulateWizard(models.TransientModel):
    _name = 'smart.parcel.simulate.wizard'
    _description = 'Kreator symulacji nadania paczki InPost -> Do odbioru'

    recipient_phone = fields.Char(string='Telefon odbiorcy', default='500600700', required=True)
    size_template = fields.Selection([
        ('small', 'Gabaryt A (Mały)'),
        ('medium', 'Gabaryt B (Średni)'),
        ('large', 'Gabaryt C (Duży)'),
    ], string='Gabaryt InPost', default='medium', required=True)
    target_point = fields.Char(string='Kod punktu InPost', default='KRA01M', required=True)
    mac_address = fields.Char(
        string='Adres MAC lokalizatora (opcjonalnie)',
        help='Wpisz MAC tagu XIAO, aby od razu sparować paczkę i móc pokazać odbiór przez klienta.'
    )

    def action_run_simulation(self):
        self.ensure_one()
        payload = {
            'recipient_phone': self.recipient_phone,
            'size_template': self.size_template,
            'target_point': self.target_point,
            'mac_address': self.mac_address or None,
        }
        try:
            resp = requests.post(
                f"{FASTAPI_INTERNAL_URL}/api/inpost/simulate-ready-for-pickup",
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise UserError(f"Nie udało się połączyć z backendem FastAPI: {exc}")

        if resp.status_code not in (200, 201):
            raise UserError(f"Błąd symulacji InPost Sandbox (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        return {
            'name': 'Zasymulowana paczka (Gotowa do odbioru)',
            'type': 'ir.actions.act_window',
            'res_model': 'smart.parcel',
            'res_id': data['id'],
            'view_mode': 'form',
            'target': 'current',
        }
