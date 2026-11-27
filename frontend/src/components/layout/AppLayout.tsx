'use client';

import { useI18n } from '@/i18n/I18nProvider';

import * as React from 'react';
import { Alert, Box, Button, CircularProgress } from '@mui/material';
import { useRouter, usePathname } from 'next/navigation';
import { useState, useEffect, useRef } from 'react';
import Sidebar from './Sidebar';
import Header, { APPBAR_HEIGHT } from './Header';
import { dashboardApi } from '@/lib/api';
import { getCurrentUser } from '@/lib/meCache';
import { runWhenIdle } from '@/lib/idle';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  // Phạm vi xác thực: đổi vị trí mới có thể đổi quyền (vai trò gắn theo vị trí),
  // còn chuyển giữa các hồ sơ trong cùng một vị trí thì không. `pathname` có cả
  // mã hồ sơ, nên dùng nó làm khoá khiến mỗi lần bấm `n` lại hỏi `auth/me` (và
  // cả badge work-queue) sau khi bản dùng chung 30 giây hết hạn.
  const authScope = pathname.replace(/^(\/positions\/[^/]+).*$/, '$1');
  const [isLoading, setIsLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [systemRoles, setSystemRoles] = useState<string[]>([]);
  const [canAccessRubrics, setCanAccessRubrics] = useState(false);
  const [profile, setProfile] = useState<{ display_name?: string; email?: string } | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // Số việc đang chờ cho badge trên header. Lấy từ work-queue sẵn có, không thêm
  // endpoint; trang dashboard tự tải dữ liệu của nó nên không cần badge ở đó.
  const [workCount, setWorkCount] = useState<number | null>(null);
  const workQueueFetchedAt = useRef(0);
  // Màn hình đã hỏi badge lần cuối. Chuyển giữa các hồ sơ trong cùng danh sách
  // chỉ đổi id cuối đường dẫn: quyền và phạm vi badge y nguyên, nên hỏi lại chỉ
  // tốn một request (đo ở `tests/profile-transition-requests.cjs`: ở lại 32 giây
  // rồi bấm `n` từng tải lại badge). Đổi màn hình thật thì vẫn hỏi lại.
  const badgeScreenRef = useRef<string | null>(null);

  useEffect(() => {
    if (['/', '/bootstrap', '/change-password', '/careers-demo', '/careers', '/pool-withdraw', '/demo'].includes(pathname)) { setIsLoading(false); setAuthenticated(false); return; }
    let active = true;
    const checkAuth = async () => {
      const token = localStorage.getItem('hra_access_token');
      if (!token) { router.replace('/'); return; }
      try {
        if (!authenticated) setIsLoading(true);
        // Dùng bản dùng chung: trang hồ sơ cũng hỏi đúng câu này trong cùng
        // một lần chuyển, nên hai request thay vì một (xem `lib/meCache.ts`).
        const me = await getCurrentUser();
        if (active && me.must_change_password) {
          setAuthenticated(false); router.replace('/change-password'); return;
        }
        if (active) { setProfile(me); setSystemRoles(me.system_roles || []); setCanAccessRubrics((me.system_roles || []).some((r: string) => ['ADMIN', 'HR_LEAD', 'HR_RECRUITER'].includes(r)) || (me.position_assignments || []).some((p: { position_role: string }) => ['HR_RECRUITER', 'HR_LEAD'].includes(p.position_role))); setAuthenticated(true); setAuthError(null); }
      } catch (err: any) {
        if (active && err.response?.status !== 401) {
          setAuthenticated(false);
          setAuthError(err.response?.status === 403 ? (err.response?.data?.detail || t("Tài khoản không có quyền truy cập."))
            : t("Không thể kết nối máy chủ để xác thực. Vui lòng kiểm tra kết nối và thử lại."));
        }
      } finally { if (active) setIsLoading(false); }
    };
    checkAuth();
    return () => { active = false; };
    // Revalidate on navigation but do not include authenticated (would cause a loop).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authScope, router, attempt]);

  // Đổi trang là lúc hợp lý để cập nhật badge; giãn cách 30 giây để việc đi lại
  // giữa các màn không nhân thành một loạt truy vấn tổng hợp.
  useEffect(() => {
    if (!authenticated) { setWorkCount(null); return; }
    if (pathname === '/dashboard') return;
    // Bỏ id hồ sơ ở cuối đường dẫn — `n` đổi hồ sơ chứ không đổi màn hình.
    const badgeScreen = pathname.replace(/^(.*\/applicants)\/[^/]+$/, '$1');
    if (badgeScreenRef.current === badgeScreen) return;
    if (Date.now() - workQueueFetchedAt.current < 30_000) return;
    badgeScreenRef.current = badgeScreen;
    workQueueFetchedAt.current = Date.now();
    // Badge là phụ trợ: để trình duyệt rảnh rồi mới hỏi, không tranh với dữ liệu
    // của màn hình vừa mở.
    const cancel = runWhenIdle(() => dashboardApi.getWorkQueue()
      .then(response => setWorkCount(response.data?.items?.length ?? 0))
      .catch(() => { /* badge là phụ trợ; lỗi mạng không được chặn màn hình */ }));
    return cancel;
    // pathname nằm trong deps vì effect đọc nó (bỏ qua /dashboard, và ý đồ là
    // cập nhật badge khi đổi trang). Thiếu nó thì comment nói một đằng, code
    // làm một nẻo: badge không bao giờ cập nhật khi điều hướng.
  }, [authenticated, authScope, pathname]);

  if (['/', '/bootstrap', '/change-password', '/careers-demo', '/careers', '/pool-withdraw', '/demo'].includes(pathname)) return <>{children}</>;
  if (isLoading || (!authenticated && !authError)) return (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', bgcolor: '#F8FAFC' }}>
      <CircularProgress color="secondary" aria-label={t("Đang xác thực")} />
    </Box>
  );
  if (authError) return (
    <Box sx={{ maxWidth: 560, mx: 'auto', mt: 8, p: 2 }}>
      <Alert severity="error" action={<Button color="inherit" onClick={() => setAttempt(n => n + 1)}>{t("Thử lại")}</Button>}>
        {t(authError)}
      </Alert>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* Keyboard users used to tab through the whole sidebar and the language
          switcher before reaching the page — eleven stops on every profile they
          opened. The skip link is the first thing focusable, so one Tab lands on
          content instead. */}
      <Box
        component="a"
        href="#main-content"
        data-testid="skip-to-content"
        sx={{
          position: 'absolute',
          left: 8,
          top: -60,
          zIndex: theme => theme.zIndex.tooltip + 1,
          backgroundColor: '#0A2B57',
          color: '#fff',
          px: 2,
          py: 1,
          borderRadius: 1,
          fontWeight: 700,
          transition: 'top .15s',
          '&:focus': { top: 8, outline: '2px solid #fff', outlineOffset: 2 },
        }}
      >
        {t("Tới nội dung chính")}
      </Box>
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} isAdmin={systemRoles.includes('ADMIN')} canAccessRubrics={canAccessRubrics} />
      <Header onOpenMenu={() => setMobileOpen(true)} profile={profile} workCount={workCount} />
      {/* tabIndex={-1} lets the skip link move focus here; it stays out of the
          normal tab order so it is not an extra stop. */}
      <Box component="main" id="main-content" tabIndex={-1} sx={{ flexGrow: 1, minWidth: 0, backgroundColor: '#F8FAFC', minHeight: '100vh', '&:focus': { outline: 'none' } }}>
        <Box sx={{ mt: `${APPBAR_HEIGHT}px`, p: { xs: 2, sm: 3, lg: 4 } }}>{children}</Box>
      </Box>
    </Box>
  );
}
