from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from apps.emissions.models import EmissionRecord, AuditLog


class ReviewActionView(APIView):
    """Single endpoint for approve / flag / reject actions."""
    
    def post(self, request, record_id):
        action = request.data.get('action')  # APPROVED, FLAGGED, REJECTED
        note = request.data.get('note', '')
        
        if action not in ('APPROVED', 'FLAGGED', 'REJECTED'):
            return Response({'error': 'action must be APPROVED, FLAGGED, or REJECTED'}, status=400)
        
        try:
            record = EmissionRecord.objects.get(id=record_id)
        except EmissionRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
        
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
    """Bulk approve/flag multiple records at once."""
    
    def post(self, request):
        record_ids = request.data.get('record_ids', [])
        action = request.data.get('action')
        note = request.data.get('note', '')
        
        if not record_ids or action not in ('APPROVED', 'FLAGGED', 'REJECTED'):
            return Response({'error': 'record_ids and valid action required'}, status=400)
        
        updated = 0
        for rid in record_ids:
            try:
                record = EmissionRecord.objects.get(id=rid, is_locked=False)
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
                AuditLog.objects.create(record=record, user=request.user, action=action,
                                        changes={'review_status': [old, action]}, note=note)
                updated += 1
            except EmissionRecord.DoesNotExist:
                pass
        
        return Response({'updated': updated})


class AuditLogView(APIView):
    def get(self, request, record_id):
        logs = AuditLog.objects.filter(record_id=record_id).order_by('timestamp')
        return Response([{
            'action': l.action,
            'action_label': l.get_action_display(),
            'user': l.user.username if l.user else 'System',
            'changes': l.changes,
            'note': l.note,
            'timestamp': l.timestamp.isoformat(),
        } for l in logs])
