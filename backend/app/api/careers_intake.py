"""Gated synthetic-only intake over real DB/Storage/clamd (not production)."""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import FileValidationError
from app.db.database import SessionLocal
from app.services.document_processor import document_processor
from app.services.careers_storage import destination, store as _store
from app.services.malware_scan import ScanVerdict, scan_bytes
from app.services.talent_pool import create_consent

router = APIRouter()
# Phiên bản thông báo consent được ghi vào bảng bằng chứng. Đổi số này khi câu
# chữ trên form đổi nghĩa — nhờ vậy về sau tra được ứng viên đã đồng ý với bản
# nào, chứ không phải "đồng ý" chung chung.
CONSENT_NOTICE = 'careers-apply-retention-12m-v1'
# Hồ sơ được lưu 12 tháng kể từ lúc nộp, để dùng cho các nhu cầu tuyển dụng sau.
# Đây là con số đã cam kết với ứng viên bằng câu chữ trên form; sửa một bên mà
# không sửa bên kia là nói một đằng làm một nẻo.
RETENTION_DAYS = 365


def _fingerprint(request_id, position_id, name, email, phone, filename, data, pool_token):
    payload = json.dumps([str(request_id), str(position_id), name, email, phone, filename,
                          hashlib.sha256(data).hexdigest(), pool_token], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@router.post('/jobs/{position_id}/apply', status_code=202)
async def apply(position_id: UUID, request_id: UUID = Form(...), name: str = Form(...),
                email: str = Form(...), phone: str = Form(''), cv: UploadFile = File(...),
                pool_opt_in: bool = Form(False), pool_token: str = Form('')):
    if not settings.PUBLIC_CAREERS_ENABLED or not settings.PUBLIC_CAREERS_TEST_INTAKE_ENABLED:
        raise HTTPException(404, 'Không khả dụng')
    # Không chặn cứng khi thiếu socket. Quyết định có nhận tệp chưa quét hay
    # không nằm ở điều kiện cờ bên dưới, cùng một chỗ với bước quét — nếu tách
    # làm hai nơi, có ngày một bên đổi mà bên kia không.
    # Lưu ý về hai cờ khác nhau ở đây, vì dễ nhầm khi đọc lướt:
    #
    #  * BẰNG CHỨNG consent (`talent_pool_consents`) được ghi cho MỌI hồ sơ —
    #    câu đồng ý trên form đã gộp việc đồng ý nộp và đồng ý lưu 12 tháng, và
    #    nộp hồ sơ là đã đồng ý. Ghi bằng chứng là việc của DB, không phụ thuộc
    #    `TALENT_POOL_STORAGE_READY`.
    #  * LỰA CHỌN tái sử dụng hồ sơ cho vị trí khác (`pool_opt_in`) mới cần
    #    Storage/Rediscovery sẵn sàng, vì nó mở đường HR tìm lại hồ sơ.
    #
    # Nếu gắn chặn 503 vào *bằng chứng consent* thì khi cờ tắt, mọi hồ sơ đều bị
    # từ chối — một câu đồng ý bắt buộc làm sập cả form. Đó là lý do điều kiện
    # dưới đây chỉ xét `pool_opt_in`.
    if pool_opt_in and not settings.TALENT_POOL_STORAGE_READY:
        raise HTTPException(503, 'Talent Pool chưa sẵn sàng')
    name, phone = name.strip(), phone.strip()
    try:
        # `check_deliverability=False`: không gọi DNS từ đường nộp hồ sơ. Vừa
        # chậm, vừa để lộ việc hệ thống đi hỏi bản ghi MX của tên miền ứng viên.
        #
        # `test_environment=True` KHÔNG phải "chế độ thử nghiệm còn sót lại", và
        # cũng không nới lỏng việc kiểm email thật. Nó chỉ cho phép các **miền
        # dành riêng** (`.test`, `.example`, `.invalid`, `.localhost`) — những
        # miền mà email-validator từ chối ở chế độ thường. Cần nó vì bộ test
        # tích hợp và các tài khoản mẫu dùng `@example.test`; bỏ đi thì chúng
        # nhận 400 thay vì đi tiếp. Email thật (`@gmail.com`…) vẫn được kiểm
        # đúng như cũ ở cả hai chế độ.
        email = validate_email(email.strip(), check_deliverability=False,
                               test_environment=True).normalized.lower()
    except EmailNotValidError:
        raise HTTPException(400, 'Địa chỉ email không hợp lệ') from None
    if not name or len(name) > 200 or len(phone) > 50 or len(email) > 254:
        raise HTTPException(400, 'Thông tin ứng viên không hợp lệ')
    if (pool_opt_in and not re.fullmatch(r'[0-9a-f]{64}', pool_token)) or (not pool_opt_in and pool_token):
        raise HTTPException(400, 'Mã rút lựa chọn không hợp lệ')
    filename = os.path.basename((cv.filename or '').replace('\\', '/'))[:200]
    data = await cv.read(settings.MAX_FILE_SIZE_BYTES + 1)
    if not data or len(data) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(400, 'CV không hợp lệ hoặc quá lớn')
    # Antivirus always runs before ZIP/PDF validation or extraction. Scanner
    # errors/limits/timeouts fail closed, not clean.
    verdict = await run_in_threadpool(scan_bytes, data, socket_path=settings.CLAMAV_UNIX_SOCKET,
                                      max_bytes=settings.MAX_FILE_SIZE_BYTES)
    # Ba kết cục, cố ý khác nhau:
    #   CLEAN       -> nhận, ghi scan_state='SCANNED'
    #   INFECTED    -> từ chối. Tệp bẩn thì luôn chặn, kể cả ở chế độ thử nghiệm.
    #   UNAVAILABLE -> máy quét chết/cấu hình sai. Mặc định vẫn từ chối (503) —
    #                  fail-closed là hành vi production. Nhận vào hàng chờ chỉ
    #                  khi bật cờ thử nghiệm rõ ràng, và khi đó bản ghi phải mang
    #                  dấu 'chưa quét' để HR nhìn thấy.
    # Cùng khuôn với jd_import.py; khác một điểm: ở đó cờ được kiểm vì tệp không
    # được lưu, còn ở đây tệp được lưu nên cái giá của việc nhận bừa cao hơn —
    # vì vậy cờ cũng phải kèm dấu vết trên bản ghi, không chỉ một câu cảnh báo.
    if verdict == ScanVerdict.INFECTED:
        raise HTTPException(400, 'Không thể tiếp nhận tệp')
    unscanned = verdict != ScanVerdict.CLEAN
    if unscanned and not settings.PUBLIC_CAREERS_UNSCANNED_FILES_ENABLED:
        raise HTTPException(503, 'Dịch vụ kiểm tra tệp chưa sẵn sàng')
    try:
        mime = await document_processor.validate_file(data, filename, cv.content_type or '')
    except FileValidationError:
        raise HTTPException(400, 'CV không hợp lệ hoặc quá lớn') from None
    digest = _fingerprint(request_id, position_id, name, email, phone, filename, data, pool_token)
    ext = '.pdf' if mime == 'application/pdf' else '.docx'
    path = f'careers/{position_id}/{uuid4()}{ext}'
    pos, req = str(position_id), str(request_id)
    try:
        backend, bucket, identity = destination()
    except ValueError:
        raise HTTPException(503, 'Storage chưa sẵn sàng') from None
    return await run_in_threadpool(_commit_intake, pos, req, digest, path, name, email, phone,
                                   filename, data, mime, cv.content_type, pool_opt_in, pool_token,
                                   backend, bucket, identity, 'CAREERS', unscanned)


def _commit_intake(pos, req, digest, path, name, email, phone, filename, data, mime, declared_type, pool_opt_in, pool_token, backend, bucket, identity, source="CAREERS", unscanned=False):
    if source not in ("CAREERS", "EMAIL_TEST"):
        raise ValueError("Invalid intake source")
    # Persist the intended path before external I/O. Stale STAGING receipts are
    # a durable reconciliation queue, not proof that an object exists.
    db = SessionLocal()
    try:
        if not db.execute(text('SELECT 1 FROM app_private.positions WHERE position_id=:id'), {'id': pos}).first():
            raise HTTPException(404, 'Vị trí không còn nhận hồ sơ')
        db.execute(text("""INSERT INTO app_private.careers_intake_receipts(request_id,position_id,fingerprint,storage_path,state,storage_backend,storage_bucket,storage_identity)
            VALUES (:req,:pos,:digest,:path,'STAGING',:backend,:bucket,:identity) ON CONFLICT (request_id) DO NOTHING"""),
            {'req': req, 'pos': pos, 'digest': digest, 'path': path, 'backend': backend, 'bucket': bucket, 'identity': identity})
        db.commit()
        receipt = db.execute(text("""SELECT position_id,fingerprint,storage_path,state,storage_backend,storage_bucket,storage_identity FROM app_private.careers_intake_receipts
            WHERE request_id=:req FOR UPDATE"""), {'req': req}).mappings().one()
        if str(receipt['position_id']) != pos or receipt['fingerprint'] != digest:
            raise HTTPException(409, 'Mã yêu cầu đã được sử dụng cho nội dung khác')
        if receipt['state'] == 'COMMITTED':
            return {'message': 'Hồ sơ đã được tiếp nhận.'}
        if receipt['state'] == 'ABANDONED':
            raise HTTPException(410, 'Yêu cầu đã hết hạn, vui lòng tạo yêu cầu mới')
        if (receipt['storage_backend'], receipt['storage_bucket'], receipt['storage_identity']) != (backend, bucket, identity):
            raise HTTPException(503, 'Cấu hình Storage đã thay đổi; cần đối soát')
        locked = db.execute(text('SELECT 1 FROM app_private.positions WHERE position_id=:id FOR UPDATE'), {'id': pos}).first()
        current = db.execute(text("SELECT status, application_deadline_at > clock_timestamp() AS eligible FROM app_private.positions WHERE position_id=:id"), {'id': pos}).mappings().first() if locked else None
        if not current or current['status'] != 'OPEN' or not current['eligible']:
            raise HTTPException(404, 'Vị trí không còn nhận hồ sơ')
        approved = db.execute(text("""SELECT 1 FROM app_private.criteria_versions c WHERE c.position_id=:pos AND c.status='APPROVED'
            AND c.jd_version_id=(SELECT jd_version_id FROM app_private.jd_versions WHERE position_id=:pos ORDER BY version_number DESC LIMIT 1)"""), {'pos': pos}).first()
        if not approved:
            raise HTTPException(409, 'Vị trí chưa sẵn sàng nhận hồ sơ')
        if db.execute(text("""SELECT 1 FROM app_private.operations WHERE position_id=:pos AND capability IN
            ('CV_PROCESSING','ASSESSMENT','RANKING') AND status IN ('PENDING','PROCESSING')"""), {'pos': pos}).first():
            raise HTTPException(409, 'Vị trí đang xử lý, vui lòng thử lại sau')
        try:
            _store(backend, bucket, identity, receipt['storage_path'], data, mime)
        except Exception:
            # Do not delete on uncertain upload/commit outcome; the committed
            # receipt permits explicit reconciliation or identical retry.
            raise HTTPException(503, 'Storage chưa sẵn sàng, vui lòng thử lại') from None
        operation = db.execute(text("""INSERT INTO app_private.operations(position_id,capability,status,idempotency_key,requested_by)
            VALUES (:pos,'CV_PROCESSING','PENDING',:key,NULL) RETURNING operation_id"""), {'pos': pos, 'key': f'intake:{source}:{req}'}).scalar_one()
        batch = db.execute(text("""INSERT INTO app_private.cv_batches(position_id,operation_id,intake_source,status,total_files,total_size_bytes,uploaded_by)
            VALUES (:pos,:op,:source,'PROCESSING',1,:size,NULL) RETURNING batch_id"""), {'pos': pos, 'op': operation, 'size': len(data), 'source': source}).scalar_one()
        application = db.execute(text("""INSERT INTO app_private.applications(position_id,source_code,created_by)
            VALUES (:pos,:source,NULL) RETURNING application_id"""), {'pos': pos, 'source': source}).scalar_one()
        db.execute(text("INSERT INTO app_private.application_identities(application_id,display_name,email,phone) VALUES (:app,:name,:email,:phone)"),
                   {'app': application, 'name': name, 'email': email, 'phone': phone or None})
        document = db.execute(text("""INSERT INTO app_private.application_documents(application_id,document_type,bucket,storage_path,original_filename,mime_type,size_bytes,file_processing_status,scan_state)
            VALUES (:app,'CV',:bucket,:path,:name,:mime,:size,'RECEIVED',:scan_state) RETURNING document_id"""),
            {'app': application, 'bucket': receipt['storage_bucket'], 'path': receipt['storage_path'], 'name': filename, 'mime': mime, 'size': len(data),
             'scan_state': 'UNSCANNED' if unscanned else 'SCANNED'}).scalar_one()
        db.execute(text("INSERT INTO app_private.document_processing_runs(document_id,operation_id,extraction_type,status) VALUES (:doc,:op,'INITIAL_EXTRACTION','PENDING')"), {'doc': document, 'op': operation})
        db.execute(text("""INSERT INTO app_private.cv_batch_items(batch_id,original_filename,declared_mime_type,detected_mime_type,size_bytes,validation_result,application_id)
            VALUES (:batch,:name,:declared,:mime,:size,'ACCEPTED',:app)"""), {'batch': batch, 'name': filename, 'declared': declared_type, 'mime': mime, 'size': len(data), 'app': application})
        # Bằng chứng consent: chỉ ghi cho hồ sơ **ứng viên tự nộp** qua form
        # công khai, không phụ thuộc việc có tick chọn Talent Pool.
        #
        # Câu đồng ý trên form đã gộp hai việc (đồng ý nộp + đồng ý lưu 12
        # tháng), và gửi form là đã tick câu đó. Bản ghi này trả lời được "ứng
        # viên đồng ý với bản thông báo nào, đến khi nào thì xoá".
        #
        # KHÔNG ghi cho `source='EMAIL_TEST'`: hồ sơ đó được nhập từ hộp thư,
        # ứng viên chưa từng thấy form và chưa từng đồng ý điều gì. Ghi một dòng
        # "đã đồng ý" cho họ là tạo bằng chứng không có thật — tệ hơn nhiều so
        # với việc không có bằng chứng, vì nó nói dối đúng chỗ cần trung thực.
        #
        # Token rút chỉ tồn tại khi ứng viên chọn tham gia Talent Pool — nó là
        # công cụ rút KHỎI danh sách tái sử dụng, không phải điều kiện để lưu
        # hồ sơ. Máy chủ tự sinh token ngẫu nhiên khi không có (không bao giờ
        # trả token đó ra ngoài), để mỗi dòng consent giữ được tính duy nhất.
        if source == 'CAREERS':
            expiry = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
            create_consent(db, application_id=str(application), notice_version=CONSENT_NOTICE,
                           consent_expires_at=expiry, retention_expires_at=expiry,
                           withdrawal_token=pool_token or None)
        db.execute(text("""UPDATE app_private.careers_intake_receipts SET state='COMMITTED',application_id=:app,updated_at=clock_timestamp() WHERE request_id=:req"""), {'app': application, 'req': req})
        db.execute(text("""INSERT INTO app_private.audit_events(action_type,object_type,object_id,position_id,outcome,metadata)
            VALUES ('CAREERS_TEST_APPLY','APPLICATION',:app,:pos,'SUCCESS',jsonb_build_object('source',CAST(:source AS text)))"""), {'app': application, 'pos': pos, 'source': source})
        if unscanned:
            # Một dòng audit riêng, không nhồi vào dòng trên: câu hỏi "hồ sơ nào
            # vào hệ thống lúc máy quét chết" phải tra được bằng action_type,
            # không phải bằng cách đọc JSON của mọi lần nhận hồ sơ.
            db.execute(text("""INSERT INTO app_private.audit_events(action_type,object_type,object_id,position_id,outcome,metadata)
                VALUES ('CAREERS_UNSCANNED_FILE_ACCEPTED','APPLICATION',:app,:pos,'SUCCESS',
                        jsonb_build_object('source',CAST(:source AS text),'document_id',CAST(:doc AS text),'reason','SCANNER_UNAVAILABLE'))"""),
                {'app': application, 'pos': pos, 'source': source, 'doc': str(document)})
        db.commit()
        return {'message': 'Hồ sơ đã được tiếp nhận.'}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Yêu cầu hoặc mã rút lựa chọn đã được sử dụng') from None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
