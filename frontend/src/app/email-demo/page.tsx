'use client';

import { useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import apiClient from '@/lib/api';
import { newRequestId } from '@/lib/browserIds';

export default function EmailDemo() {
  const [file, setFile] = useState<File | null>(null);
  const [requestId, setRequestId] = useState('');
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!file) return;
    setBusy(true); setResult(''); setError('');
    try {
      const body = new FormData(); body.set('request_id', requestId); body.set('message', file);
      const response = await apiClient.post('/careers-demo/email/ingest', body, { headers: { 'Content-Type': 'multipart/form-data' } });
      setResult(response.data.status === 'ACCEPTED' ? 'Đã tiếp nhận email giả vào hàng đợi xử lý CV demo.' : `Cần kiểm tra thủ công: ${response.data.reason}`);
    } catch (err: any) { setError(err.response?.data?.detail || 'Không thể tiếp nhận email demo.'); }
    finally { setBusy(false); }
  };
  return <Box><Typography variant="h1" sx={{ fontSize: 28, mb: 2 }}>Tiếp nhận email offline — DEMO</Typography>
    <Stack spacing={2} sx={{ maxWidth: 700 }}>
      <Alert severity="warning">Chỉ dùng tệp EML tổng hợp; không kết nối Gmail, không có quét mã độc và không sử dụng dữ liệu thật.</Alert>
      <Typography>Tải một email giả với đúng một mã vị trí trong tiêu đề và một CV tổng hợp đính kèm. HR cần quyền trên vị trí; vị trí cần OPEN, còn hạn và rubric được duyệt.</Typography>
      <label>Chọn email giả (.eml) <input type="file" accept=".eml,message/rfc822" onChange={e => { setFile(e.target.files?.[0] || null); setRequestId(newRequestId() || ''); setResult(''); setError(''); }} /></label>
      <Button variant="contained" disabled={!file || busy} onClick={submit}>Tiếp nhận demo</Button>
      {result && <Alert severity="info">{result}</Alert>}{error && <Alert severity="error">{error}</Alert>}
    </Stack>
  </Box>;
}
