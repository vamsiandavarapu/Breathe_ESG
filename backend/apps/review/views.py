from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from apps.tenants.models import verify_tenant_access
from apps.emissions.models import EmissionRecord, AuditLog


class ReviewActionView(APIView):
    """Single endpoint for approve / flag / reject actions with tenant & RBAC enforcement."""
    
    def post(self, request, record_id):
        action = request.data.get('action')  # APPROVED, FLAGGED, REJECTED
        note = request.data.get('note', '')
        
        if action not in ('APPROVED', 'FLAGGED', 'REJECTED'):
            return Response({'error': 'action must be APPROVED, FLAGGED, or REJECTED'}, status=400)
        
        try:
            record = EmissionRecord.objects.get(id=record_id)
        except EmissionRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        # Verify tenant access and mutating permissions (admin or analyst role required)
        is_allowed, membership_or_err = verify_tenant_access(
            request.user, record.tenant_id, allowed_roles=['admin', 'analyst']
        )
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)
        
        if record.is_locked:
            return Response({'error': 'Record is locked for audit — cannot change'}, status=403)
        
        old_status = record.review_status
        record.review_status = action
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.review_note = note
        
        if action == 'APPROVED':
            record.is_locked = True
            record.locked_at = timezone.now()
            record.locked_by = request.user
        
        record.save()
        
        AuditLog.objects.create(
            record=record,
            user=request.user,
            action=action,
            changes={'review_status': [old_status, action]},
            note=note,
        )
        
        return Response({'status': 'ok', 'review_status': action, 'is_locked': record.is_locked})


class BulkReviewView(APIView):
    """Bulk approve/flag multiple records at once with tenant & RBAC enforcement."""
    
    def post(self, request):
        record_ids = request.data.get('record_ids', [])
        action = request.data.get('action')
        note = request.data.get('note', '')
        
        if not record_ids or action not in ('APPROVED', 'FLAGGED', 'REJECTED'):
            return Response({'error': 'record_ids and valid action required'}, status=400)
        
        # Load records to verify their tenants
        records = EmissionRecord.objects.filter(id__in=record_ids)
        if not records.exists():
            return Response({'updated': 0})
            
        # Extract unique tenant IDs of all requested records
        tenant_ids = set(records.values_list('tenant_id', flat=True))
        
        # Verify user has mutating access to all unique tenants in this batch
        for t_id in tenant_ids:
            is_allowed, membership_or_err = verify_tenant_access(
                request.user, t_id, allowed_roles=['admin', 'analyst']
            )
            if not is_allowed:
                return Response({'error': f"Unauthorized bulk action: {membership_or_err}"}, status=403)
        
        updated = 0
        for record in records:
            if record.is_locked:
                continue
                
            old = record.review_status
            record.review_status = action
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            record.review_note = note
            
            if action == 'APPROVED':
                record.is_locked = True
                record.locked_at = timezone.now()
                record.locked_by = request.user
                
            record.save()
            
            AuditLog.objects.create(
                record=record,
                user=request.user,
                action=action,
                changes={'review_status': [old, action]},
                note=note
            )
            updated += 1
        
        return Response({'updated': updated})


class AuditLogView(APIView):
    """View the audit trail of a single record, enforced by tenant isolation."""
    
    def get(self, request, record_id):
        try:
            record = EmissionRecord.objects.get(id=record_id)
        except EmissionRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        # Verify tenant access (viewers are allowed to view audit logs)
        is_allowed, membership_or_err = verify_tenant_access(request.user, record.tenant_id)
        if not is_allowed:
            return Response({'error': membership_or_err}, status=403)
            
        logs = AuditLog.objects.filter(record_id=record_id).order_by('timestamp')
        return Response([{
            'action': l.action,
            'action_label': l.get_action_display(),
            'user': l.user.username if l.user else 'System',
            'changes': l.changes,
            'note': l.note,
            'timestamp': l.timestamp.isoformat(),
        } for l in logs])

