"""
Ingestion views — file upload endpoint and job status.
"""
import json
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone

from apps.emissions.models import IngestionJob, RawRecord, EmissionRecord, AuditLog
from apps.tenants.models import Tenant, verify_tenant_access
from .parsers.sap_parser import parse_sap_csv
from .parsers.utility_parser import parse_utility_csv
from .parsers.travel_parser import parse_travel_csv


PARSER_MAP = {
    'SAP_FUEL': parse_sap_csv,
    'UTILITY_ELECTRICITY': parse_utility_csv,
    'TRAVEL_CORPORATE': parse_travel_csv,
}


class UploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        tenant_id = request.data.get('tenant_id')
        source_type = request.data.get('source_type')
        uploaded_file = request.FILES.get('file')

        if not all([tenant_id, source_type, uploaded_file]):
            return Response({'error': 'tenant_id, source_type, and file are required'}, status=400)

        # Enforce multi-tenancy verification & RBAC (admin/analyst required to upload data)
        is_allowed, membership_or_err = verify_tenant_access(
            request.user, tenant_id, allowed_roles=['admin', 'analyst']
        )
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)

        if source_type not in PARSER_MAP:
            return Response({'error': f'Unknown source_type: {source_type}'}, status=400)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=404)

        # Create ingestion job
        job = IngestionJob.objects.create(
            tenant=tenant,
            source_type=source_type,
            file_name=uploaded_file.name,
            uploaded_by=request.user,
            status='PROCESSING',
        )

        try:
            content = uploaded_file.read().decode('utf-8', errors='replace')
            parser = PARSER_MAP[source_type]
            parsed_rows = parser(content, tenant)

            success = failed = suspicious = 0

            for row_data in parsed_rows:
                raw = RawRecord.objects.create(
                    job=job,
                    row_number=row_data['row_number'],
                    raw_data=row_data['raw_data'],
                    parse_status=row_data['parse_status'],
                    parse_errors=row_data['parse_errors'],
                )

                if row_data['parse_status'] == 'FAILED':
                    failed += 1
                    continue

                # Create EmissionRecord for OK and SUSPICIOUS rows
                try:
                    record = EmissionRecord.objects.create(
                        tenant=tenant,
                        raw_record=raw,
                        job=job,
                        scope=row_data.get('scope', 'SCOPE_3'),
                        category=row_data.get('category', 'PURCHASED_GOODS'),
                        source_type=source_type,
                        activity_description=row_data.get('activity_description', ''),
                        activity_date=row_data.get('activity_date'),
                        location=row_data.get('location', ''),
                        quantity=row_data.get('quantity', 0),
                        unit=row_data.get('unit', 'LITRE'),
                        quantity_original=row_data.get('quantity_original'),
                        unit_original=row_data.get('unit_original', ''),
                        emission_factor=row_data.get('emission_factor', 0),
                        emission_factor_source=row_data.get('emission_factor_source', 'DEFRA 2024'),
                        co2e_kg=row_data.get('co2e_kg', 0),
                        is_suspicious=row_data.get('is_suspicious', False),
                        suspicious_reason=row_data.get('suspicious_reason', ''),
                        review_status='PENDING',
                    )
                    AuditLog.objects.create(
                        record=record,
                        user=request.user,
                        action='CREATED',
                        changes={},
                        note=f'Ingested from {uploaded_file.name}',
                    )
                    if row_data['parse_status'] == 'SUSPICIOUS':
                        suspicious += 1
                    else:
                        success += 1
                except Exception as e:
                    failed += 1
                    raw.parse_status = 'FAILED'
                    raw.parse_errors.append(f'EmissionRecord creation failed: {str(e)}')
                    raw.save()

            job.status = 'DONE'
            job.total_rows = len(parsed_rows)
            job.success_rows = success
            job.failed_rows = failed
            job.suspicious_rows = suspicious
            job.save()

            return Response({
                'job_id': job.id,
                'status': 'DONE',
                'total_rows': len(parsed_rows),
                'success_rows': success,
                'failed_rows': failed,
                'suspicious_rows': suspicious,
            })

        except Exception as e:
            job.status = 'FAILED'
            job.error_summary = [str(e)]
            job.save()
            return Response({'error': str(e)}, status=500)


class JobListView(APIView):
    """Retrieves past ingestion jobs for a tenant with full security validation."""
    
    def get(self, request):
        tenant_id = request.query_params.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id is required'}, status=400)
            
        # Verify tenant access (viewers are allowed to see history)
        is_allowed, membership_or_err = verify_tenant_access(request.user, tenant_id)
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)
            
        jobs = IngestionJob.objects.filter(tenant_id=tenant_id).select_related('uploaded_by').order_by('-uploaded_at')
        return Response([{
            'id': j.id,
            'source_type': j.source_type,
            'source_type_label': j.get_source_type_display(),
            'file_name': j.file_name,
            'uploaded_by': j.uploaded_by.username if j.uploaded_by else 'System',
            'uploaded_at': j.uploaded_at.isoformat(),
            'status': j.status,
            'total_rows': j.total_rows,
            'success_rows': j.success_rows,
            'failed_rows': j.failed_rows,
            'suspicious_rows': j.suspicious_rows,
            'error_summary': j.error_summary,
        } for j in jobs])


