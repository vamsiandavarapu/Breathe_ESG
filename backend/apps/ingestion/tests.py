from django.test import TestCase
from apps.tenants.models import Tenant
from apps.ingestion.parsers.sap_parser import parse_sap_csv

class SAPParserTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Corporate Tenant",
            slug="test-corporate-tenant",
            industry="Manufacturing"
        )

    def test_parse_valid_idoc_xml(self):
        # A standard SAP IDoc XML structure
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <IDOC>
            <E1EDK01>
                <BUKRS>HO01</BUKRS>
                <BLDAT>2026-05-29</BLDAT>
            </E1EDK01>
            <E1EDP01>
                <WERKS>PL01</WERKS>
                <MATNR>DIESEL</MATNR>
                <MENGE>1500.00</MENGE>
                <MEINS>L</MEINS>
                <WRBTR>135000.00</WRBTR>
                <TXZ01>Diesel fuel for generators</TXZ01>
            </E1EDP01>
            <E1EDP01>
                <WERKS>PL02</WERKS>
                <MATNR>PETROL</MATNR>
                <MENGE>500.00</MENGE>
                <MEINS>L</MEINS>
                <WRBTR>50000.00</WRBTR>
                <TXZ01>Petrol for company cars</TXZ01>
            </E1EDP01>
        </IDOC>
        """
        
        results = parse_sap_csv(xml_content, self.tenant)
        
        # Verify both items parsed
        self.assertEqual(len(results), 2)
        
        # Verify first item (Diesel)
        diesel_row = results[0]
        self.assertEqual(diesel_row['parse_status'], 'OK')
        self.assertEqual(diesel_row['scope'], 'SCOPE_1')
        self.assertEqual(diesel_row['category'], 'STATIONARY_COMBUSTION')
        self.assertEqual(diesel_row['quantity'], 1500.0)
        self.assertEqual(diesel_row['unit'], 'LITRE')
        self.assertEqual(diesel_row['location'], 'Mumbai - Andheri Factory')
        self.assertGreater(diesel_row['co2e_kg'], 0)

        # Verify second item (Petrol)
        petrol_row = results[1]
        self.assertEqual(petrol_row['parse_status'], 'OK')
        self.assertEqual(petrol_row['scope'], 'SCOPE_1')
        self.assertEqual(petrol_row['category'], 'MOBILE_COMBUSTION')
        self.assertEqual(petrol_row['quantity'], 500.0)
        self.assertEqual(petrol_row['unit'], 'LITRE')
        self.assertEqual(petrol_row['location'], 'Pune - Hinjewadi Facility')
        self.assertGreater(petrol_row['co2e_kg'], 0)

    def test_parse_invalid_xml_structure(self):
        # Malformed XML
        xml_content = "<IDOC><E1EDP01><MENGE>100</MENGE>"
        with self.assertRaises(ValueError):
            parse_sap_csv(xml_content, self.tenant)

    def test_parse_idoc_missing_fields_warning(self):
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <IDOC>
            <E1EDP01>
                <!-- Missing quantity and date -->
                <WERKS>PL01</WERKS>
                <MATNR>DIESEL</MATNR>
                <MEINS>L</MEINS>
            </E1EDP01>
        </IDOC>
        """
        results = parse_sap_csv(xml_content, self.tenant)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['parse_status'], 'FAILED')
        self.assertIn("Missing required fields", results[0]['parse_errors'][0])
