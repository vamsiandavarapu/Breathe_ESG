"""
Core emission data models.

The architecture has two layers:
1. RawRecord  — immutable snapshot of exactly what came in from the source.
                Never edited. This is your audit proof.
2. EmissionRecord — normalized, enriched, editable version derived from RawRecord.
                    Analysts can correct values here. The original is always preserved above.

This split is critical: if an auditor asks "what did the SAP system actually send you?",
you can show them RawRecord. If they ask "what did you report?", you show EmissionRecord.
"""
from django.db import models
from django.contrib.auth.models import User
from apps.tenants.models import Tenant
import decimal


class IngestionJob(models.Model):
    """
    Tracks a single upload/import event.
    When an analyst uploads a SAP file, one IngestionJob is created.
    All records parsed from that file point back to this job.
    """
    SOURCE_CHOICES = [
        ('SAP_FUEL', 'SAP - Fuel & Procurement'),
        ('UTILITY_ELECTRICITY', 'Utility Portal - Electricity'),
        ('TRAVEL_CORPORATE', 'Corporate Travel (Concur/Navan)'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('DONE', 'Done'),
        ('FAILED', 'Failed'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_jobs')
    source_type = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    file_name = models.CharField(max_length=500)
    file_path = models.CharField(max_length=1000, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_rows = models.IntegerField(default=0)
    success_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    suspicious_rows = models.IntegerField(default=0)
    error_summary = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_source_type_display()} | {self.file_name} | {self.uploaded_at.date()}"


class RawRecord(models.Model):
    """
    IMMUTABLE. Never edit this after creation.

    This stores the exact data from the source file, row by row.
    raw_data is a JSON blob of the original row — whatever columns came in.

    Why immutable? Because audit standards (GHG Protocol, ISO 14064) require you to
    prove what data you received vs what you reported. If you need to correct something,
    you correct the EmissionRecord and log it in AuditLog.
    """
    PARSE_STATUS_CHOICES = [
        ('OK', 'Parsed Successfully'),
        ('FAILED', 'Parse Failed'),
        ('SUSPICIOUS', 'Suspicious Value'),
    ]

    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='raw_records')
    row_number = models.IntegerField(help_text="Line number in the original file")
    raw_data = models.JSONField(help_text="Exact original row as received — never modified")
    parse_status = models.CharField(max_length=20, choices=PARSE_STATUS_CHOICES, default='OK')
    parse_errors = models.JSONField(default=list, help_text="List of error messages if parsing had issues")
    created_at = models.DateTimeField(auto_now_add=True)  # When we received it

    class Meta:
        ordering = ['job', 'row_number']

    def __str__(self):
        return f"Row {self.row_number} of Job {self.job_id} [{self.parse_status}]"


class EmissionRecord(models.Model):
    """
    The normalized, analyst-facing emission record.

    This is what analysts review, approve, and what goes to auditors.
    All values here are in STANDARD UNITS (kWh, litres, km, nights).
    CO2e is always in kg.

    Traceability chain: EmissionRecord → RawRecord → IngestionJob → Tenant
    """
    SCOPE_CHOICES = [
        ('SCOPE_1', 'Scope 1 - Direct Emissions'),
        ('SCOPE_2', 'Scope 2 - Purchased Electricity'),
        ('SCOPE_3', 'Scope 3 - Value Chain'),
    ]
    CATEGORY_CHOICES = [
        # Scope 1
        ('STATIONARY_COMBUSTION', 'Stationary Combustion (boilers, generators)'),
        ('MOBILE_COMBUSTION', 'Mobile Combustion (company vehicles)'),
        # Scope 2
        ('PURCHASED_ELECTRICITY', 'Purchased Electricity'),
        # Scope 3
        ('BUSINESS_TRAVEL_AIR', 'Business Travel - Air'),
        ('BUSINESS_TRAVEL_HOTEL', 'Business Travel - Hotel'),
        ('BUSINESS_TRAVEL_GROUND', 'Business Travel - Ground Transport'),
        ('PURCHASED_GOODS', 'Purchased Goods & Services'),
    ]
    UNIT_CHOICES = [
        ('LITRE', 'Litres'),
        ('KG', 'Kilograms'),
        ('M3', 'Cubic Metres'),
        ('KWH', 'Kilowatt Hours'),
        ('MWH', 'Megawatt Hours'),
        ('KM', 'Kilometres'),
        ('NIGHT', 'Hotel Nights'),
    ]
    REVIEW_STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('FLAGGED', 'Flagged for Review'),
        ('REJECTED', 'Rejected'),
    ]

    # ── Traceability ──────────────────────────────────────────────
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='emission_records')
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name='emission_record', null=True, blank=True)
    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='emission_records')

    # ── Classification ────────────────────────────────────────────
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    source_type = models.CharField(max_length=30, choices=IngestionJob.SOURCE_CHOICES)

    # ── What was measured ─────────────────────────────────────────
    activity_description = models.CharField(max_length=500, help_text="Human-readable: 'Diesel - Plant PL01 Mumbai'")
    activity_date = models.DateField(help_text="Date of activity (not billing date)")
    location = models.CharField(max_length=255, blank=True, help_text="Plant, site, or city")

    # ── Normalized quantity ───────────────────────────────────────
    # These are ALWAYS in standard units after normalization
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)

    # Keep original values for traceability — what did SAP actually say?
    quantity_original = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    unit_original = models.CharField(max_length=50, blank=True, help_text="Original unit from source, e.g. 'GAL', 'M3', 'KWH'")

    # ── Emission calculation ──────────────────────────────────────
    emission_factor = models.DecimalField(max_digits=12, decimal_places=6, help_text="kgCO2e per unit")
    emission_factor_source = models.CharField(max_length=100, default='DEFRA 2024', help_text="Which factor database we used")
    co2e_kg = models.DecimalField(max_digits=15, decimal_places=4, help_text="Total kgCO2e = quantity × emission_factor")

    # ── Review workflow ───────────────────────────────────────────
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='PENDING')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_records')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True, help_text="Analyst notes on this record")

    # ── Suspicious flag ───────────────────────────────────────────
    is_suspicious = models.BooleanField(default=False)
    suspicious_reason = models.TextField(blank=True)

    # ── Audit lock ────────────────────────────────────────────────
    is_locked = models.BooleanField(default=False, help_text="True once approved for audit — cannot be changed")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_records')

    # ── Edit tracking ─────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='edited_records')

    class Meta:
        ordering = ['-activity_date', 'scope']

    def __str__(self):
        return f"{self.get_scope_display()} | {self.activity_description} | {self.co2e_kg:.2f} kgCO2e"

    @property
    def co2e_tonnes(self):
        """Convenience: CO2e in metric tonnes (divide by 1000)."""
        return self.co2e_kg / decimal.Decimal('1000')


class AuditLog(models.Model):
    """
    Append-only log of every action on an EmissionRecord.
    This is the audit trail — proves who did what and when.
    Nobody can delete from this table.
    """
    ACTION_CHOICES = [
        ('CREATED', 'Record Created'),
        ('EDITED', 'Record Edited'),
        ('APPROVED', 'Record Approved'),
        ('FLAGGED', 'Record Flagged'),
        ('REJECTED', 'Record Rejected'),
        ('LOCKED', 'Record Locked for Audit'),
        ('NOTE_ADDED', 'Note Added'),
    ]

    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    changes = models.JSONField(default=dict, help_text="{'field': ['old_value', 'new_value']}")
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.action} on Record {self.record_id} by {self.user} at {self.timestamp}"
